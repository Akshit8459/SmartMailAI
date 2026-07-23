# 📘 SmartMail AI — User Guide

Welcome to **SmartMail AI**! This guide walks you through navigating your inbox, downloading binary attachments, summarizing documents, and managing your emails using natural language AI commands.

---

## 🔑 1. Logging In & Inbox Sync

1. Open **`http://localhost:8000`** in your browser.
2. Click **"Sign in with Google"** (or **"Demo Guest Access"** for instant guest evaluation).
3. Once authenticated, your inbox will load immediately. An animated status badge (`⚡ Syncing your Gmail inbox...`) indicates background synchronization.
4. Messages across `INBOX`, `SENT`, `STARRED`, and `IMPORTANT` will automatically update.

---

## 📄 2. Opening & Downloading Binary Attachments

SmartMail AI serves the exact original binary file bytes (`.pdf`, `.pptx`, `.docx`, images):

1. Select an email containing an attachment (e.g. *`Project Update & Final Report`*).
2. Scroll to the **Attachments** section below the message text.
3. Click **"Open"** or **"Download"** next to `Quarterly_Review.pdf` or `Project_Presentation.pptx`.
4. Your browser will download and open the **original binary file** in its native format.

---

## 🤖 3. Full-Document AI Summarization & Q&A

SmartMail AI analyzes up to 12,000 characters per document across all pages and slides:

1. Open an email with attachments (e.g., *`Quarterly_Review.pptx`*).
2. Click **"🤖 Summarize Email"** or **"🤖 Summarize Thread"** at the top right of the message view.
3. SmartMail AI generates a structured executive summary detailing:
   - **Core Purpose & Overview**
   - **Quantitative Data Comparison Tables**
   - **Key Rules, Milestones & Action Items**
4. Scroll to the **Attachment Q&A box**, type your question (e.g., *"What were the key recommendations?"*), and click **Ask AI**.

---

## 💬 4. Interactive AI Assistant & Natural Language Inbox Control

Open the right-hand **AI Assistant** panel to query your inbox or execute actions:

### **Searching Your Inbox**
- Type: *"What are the key action items from the project update email?"*
- SmartMail AI streams the answer and provides a clickable **"Referenced Email"** citation card.

### **Executing Inbox Actions**
- Type: *"Archive all receipts from last month"* or *"Star urgent emails"*
- SmartMail AI executes the command and displays a status badge:
  > `⚡ SmartMail AI Action Executed: Successfully archived 3 email(s).`

---

## ✉️ 5. Opened Email Actions & Quick Controls

When you click any email row to view its details, full action controls are available in the top toolbar and bottom message card:

1. **Top Action Toolbar**:
   - **`← Back to Inbox`**: Returns to the inbox email list.
   - **`✉️ Mark Unread / Read`**: Manually toggle read/unread status (unread emails auto-mark as read on open).
   - **`⭐ Star / Unstar`**: Toggle star rating.
   - **`📦 Archive`**: Archive email from inbox view.
   - **`🗑️ Delete`**: Move email to trash with confirmation.
   - **`↩️ Reply`**: Open compose prefilled to sender.
   - **`✨ Summarize Email`**: Trigger AI executive summary of email & attachments.

2. **Bottom Action Card & Smart AI Reply**:
   - Quick **Reply**, **Reply All**, and **Forward** buttons.
   - Preset smart chips (`✅ Confirm`, `❌ Decline`, `❓ More Info`) to instantly draft AI responses.

---

## 🎨 6. Theme & Sidebar Customization

- **Mini-Sidebar Mode**: Click the Hamburger Icon (`#toggleSidebar`) to collapse the sidebar into a 4.75rem mini-sidebar with icon-only badges and a compact compose button.
- **Date + Time Display**: Email list rows display full Date and Time (`Jul 23, 04:32 PM`).
- **Live Unread Counter Badge**: Sidebar inbox badge updates automatically after every email action.

---

## ⌨️ 7. Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Ctrl + K` or `Cmd + K` | Focus Search Bar |
| `C` | Open New Email Compose Modal |
| `R` | Reply to Selected Email |
| `E` | Archive Selected Email |
| `S` | Star / Unstar Selected Email |
| `Esc` | Close Modal / Clear Selection |
