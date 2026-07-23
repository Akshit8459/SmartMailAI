# 🤝 Contributing to SmartMail AI

Thank you for your interest in contributing to **SmartMail AI**! We welcome bug reports, feature requests, and pull requests.

---

## 🛠️ How to Contribute

### 1. Reporting Issues
If you encounter a bug or have a feature suggestion:
1. Search existing GitHub Issues to check if it has already been reported.
2. If not, open a new issue using a descriptive title and detailed reproduction steps.

### 2. Local Development Setup
1. Fork and clone the repository:
   ```bash
   git clone https://github.com/your-username/SmartMail-AI.git
   cd SmartMail-AI
   ```
2. Set up a Python 3.12 virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r backend/requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your API credentials.
4. Run the development server:
   ```bash
   python backend/main.py
   ```

### 3. Pull Request Guidelines
1. Create a feature branch off `main` (`git checkout -b feature/amazing-feature`).
2. Ensure code follows PEP 8 standards for Python and ES6 standards for JavaScript.
3. Test your changes thoroughly.
4. Commit your changes with descriptive commit messages.
5. Push to your branch and submit a Pull Request.

---

## 📜 Code of Conduct
Please maintain a respectful, inclusive, and welcoming environment for all contributors.
