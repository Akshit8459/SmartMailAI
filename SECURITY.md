# 🔒 SmartMail AI — Security Policy

This document outlines the security architecture, token encryption, secret management, OAuth scope requirements, and vulnerability reporting process for **SmartMail AI**.

---

## 🔑 1. Google OAuth2 Scopes & Authentication

SmartMail AI requests the minimum necessary Google OAuth2 permissions to function:

| OAuth Scope | Purpose |
| :--- | :--- |
| `https://www.googleapis.com/auth/gmail.readonly` | Read emails and attachments for indexing & summarization. |
| `https://www.googleapis.com/auth/userinfo.email` | Identify authenticated user email address. |

---

## 🔐 2. Token Encryption & Secret Management

- **OAuth Token Encryption**: Access and refresh tokens are encrypted at rest using **Fernet authenticated encryption** (AES-128-CBC with HMAC-SHA256 message authentication) via `security.py` before storage in the SQLite database.
- **Environment Isolation**: Secrets (`SECRET_KEY`, `NVIDIA_API_KEY`, `GOOGLE_CLIENT_SECRET`) are loaded strictly from environment variables via `.env` and are excluded from source control (`.gitignore`, `.dockerignore`).
- **Session Auth**: JWT session tokens signed with `HS256` algorithm and configured with strict expiration timeouts.

---

## 🛡️ 3. Reporting a Vulnerability

If you discover a potential security vulnerability in SmartMail AI, please do not open a public GitHub Issue. Instead, send an email to:

📧 **`security@smartmail-ai.org`** or submit a private security advisory on GitHub.

We will acknowledge receipt within 48 hours and provide regular updates on fix progress.

---

## ⚠️ 4. Production Security Recommendations

When deploying SmartMail AI in production:
1. Enable HTTPS / TLS termination via Nginx or Cloudflare.
2. Store environment secrets in OS-level secret managers (AWS Secrets Manager / Windows Credential Manager).
3. Restrict CORS origins in `config.py` from `*` to specific production domains.
