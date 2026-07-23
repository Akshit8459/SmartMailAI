"""
Smart Inbox Priority Scorer — heuristic engine for ranking emails by importance.
Produces a 0–100 score, a label (HIGH/MEDIUM/LOW), and a human-readable reason.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Dict, Any, List

# ─── Signal weights ────────────────────────────────────────────────────────────
URGENCY_KEYWORDS = [
    "urgent", "asap", "immediately", "action required", "important",
    "deadline", "time-sensitive", "by eod", "by today", "response needed",
    "follow up", "overdue", "reminder", "last chance", "expires",
    "interview", "offer letter", "job offer", "please respond",
]

IMPORTANT_SENDER_PATTERNS = [
    r"@(google|microsoft|apple|amazon|linkedin|github|notion|slack)\.com$",
    r"(hr|recruiting|careers|noreply|no-reply|jobs|offer|payroll)@",
    r"(admin|security|support|billing|finance)@",
]

TRANSACTIONAL_KEYWORDS = [
    "unsubscribe", "newsletter", "digest", "promotion", "sale", "offer",
    "deal", "coupon", "discount", "weekly roundup", "monthly update",
    "notification", "noreply", "do-not-reply",
]


class PriorityScorer:
    """
    Scores an email dict on a 0–100 scale using heuristic signals.
    Higher = more important/urgent.
    """

    def score(self, email: Any) -> Dict[str, Any]:
        """
        Accept either an ORM Email entity or a dict.
        Returns dict with: priority_score (int), priority_label (str), priority_reason (str).
        """
        # Normalise to dict for uniform access
        if hasattr(email, "__dict__"):
            data = {
                "subject": getattr(email, "subject", "") or "",
                "sender_email": getattr(email, "sender_email", "") or "",
                "sender_name": getattr(email, "sender_name", "") or "",
                "snippet": getattr(email, "snippet", "") or "",
                "body_text": getattr(email, "body_text", "") or "",
                "is_unread": getattr(email, "is_unread", False),
                "is_starred": getattr(email, "is_starred", False),
                "is_important": getattr(email, "is_important", False),
                "received_at": getattr(email, "received_at", None),
                "labels": getattr(email, "labels", []) or [],
            }
        else:
            data = email

        score = 0
        reasons: List[str] = []

        subject_lower = data.get("subject", "").lower()
        snippet_lower = data.get("snippet", "").lower()
        body_lower = (data.get("body_text", "") or "")[:500].lower()
        sender_email = data.get("sender_email", "").lower()
        combined_text = f"{subject_lower} {snippet_lower} {body_lower}"

        # ── 1. Starred / Important flags (user-curated) ──────────────────────
        if data.get("is_starred"):
            score += 30
            reasons.append("Starred by you")
        if data.get("is_important"):
            score += 20
            reasons.append("Marked important")

        # ── 2. Urgency keyword signals ────────────────────────────────────────
        matched_urgency = [kw for kw in URGENCY_KEYWORDS if kw in combined_text]
        if matched_urgency:
            urgency_boost = min(35, len(matched_urgency) * 10)
            score += urgency_boost
            reasons.append(f"Contains urgent signals: {', '.join(matched_urgency[:2])}")

        # ── 3. Important sender domain ────────────────────────────────────────
        for pattern in IMPORTANT_SENDER_PATTERNS:
            if re.search(pattern, sender_email, re.IGNORECASE):
                score += 15
                reasons.append(f"Important sender: {data.get('sender_email', '')}")
                break

        # ── 4. Unread status ──────────────────────────────────────────────────
        if data.get("is_unread"):
            score += 10
            reasons.append("Unread")

        # ── 5. Recency bonus (last 24h = max boost, decays over 7 days) ───────
        received_at = data.get("received_at")
        if received_at:
            try:
                if isinstance(received_at, str):
                    received_at = datetime.fromisoformat(received_at)
                now = datetime.now(timezone.utc)
                if received_at.tzinfo is None:
                    received_at = received_at.replace(tzinfo=timezone.utc)
                hours_old = (now - received_at).total_seconds() / 3600
                if hours_old < 2:
                    score += 15
                    reasons.append("Received < 2 hours ago")
                elif hours_old < 24:
                    score += 10
                    reasons.append("Received today")
                elif hours_old < 72:
                    score += 5
                    reasons.append("Received this week")
            except Exception:
                pass

        # ── 6. Transactional / promotional penalty ────────────────────────────
        matched_transactional = [kw for kw in TRANSACTIONAL_KEYWORDS if kw in combined_text]
        if matched_transactional:
            penalty = min(25, len(matched_transactional) * 8)
            score -= penalty
            reasons.append(f"Promotional content detected")

        # Also penalise noreply senders
        if "noreply" in sender_email or "no-reply" in sender_email:
            score -= 10

        # ── 7. Labels signal ──────────────────────────────────────────────────
        labels = data.get("labels", [])
        if isinstance(labels, list):
            if "IMPORTANT" in labels:
                score += 15
            if any(l in labels for l in ["CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"]):
                score -= 15

        # ── Clamp to 0–100 ────────────────────────────────────────────────────
        score = max(0, min(100, score))

        # ── Label ─────────────────────────────────────────────────────────────
        if score >= 65:
            label = "HIGH"
        elif score >= 35:
            label = "MEDIUM"
        else:
            label = "LOW"

        reason = reasons[0] if reasons else "Standard email"

        return {
            "priority_score": score,
            "priority_label": label,
            "priority_reason": reason,
        }

    def score_batch(self, emails: List[Any]) -> List[Dict[str, Any]]:
        """Score and sort a list of emails, highest priority first."""
        scored = []
        for email in emails:
            result = self.score(email)
            scored.append({**self._to_dict(email), **result})
        return sorted(scored, key=lambda x: x["priority_score"], reverse=True)

    def _to_dict(self, email: Any) -> Dict[str, Any]:
        if isinstance(email, dict):
            return email
        return {
            col: getattr(email, col, None)
            for col in [
                "id", "thread_id", "user_id", "sender_name", "sender_email",
                "recipient_list", "subject", "snippet", "body_html", "body_text",
                "received_at", "is_unread", "is_starred", "is_important", "labels",
            ]
        }


priority_scorer = PriorityScorer()
