# Security Policy

## 🛡️ Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| Main    | :white_check_mark: |

---

## 🚨 Reporting a Vulnerability

If you discover a potential security vulnerability in **OpenCode CLI**, please report it responsibly:

1. **Do NOT open a public GitHub issue.**
2. Send an email to the repository owner or submit a private security disclosure on GitHub.
3. Include:
   - Type of issue (e.g., buffer overflow, unauthenticated access, command injection)
   - Full steps or proof-of-concept to reproduce
   - Potential impact of the vulnerability

We will respond to security reports within **48 hours** and provide periodic updates until the issue is resolved.

---

## 🔒 Security Best Practices for Deployment

- **Master Encryption Keys**: Always supply strong, unique secrets for `STORAGE_ENCRYPTION_KEY`, `OMNIROUTE_STORAGE_KEY`, `JWT_SECRET`, and `API_KEY_SECRET`.
- **Never Commit Secrets**: Ensure `.env` and SQLite database files are listed in `.gitignore` and never committed to version control.
- **Reverse Proxy Authentication**: Keep `WEBUI_AUTH="true"` enabled in production deployments.
