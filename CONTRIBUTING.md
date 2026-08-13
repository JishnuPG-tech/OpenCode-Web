# Contributing to OpenCode CLI

Thank you for your interest in contributing to **OpenCode CLI**! We welcome contributions, bug reports, feature requests, and pull requests.

---

## 📋 Table of Contents
1. [Code of Conduct](#code-of-conduct)
2. [How to Contribute](#how-to-contribute)
3. [Development Setup](#development-setup)
4. [Pull Request Process](#pull-request-process)
5. [Coding & Architecture Standards](#coding--architecture-standards)

---

## 📜 Code of Conduct

Please be polite, respectful, and collaborative in all communications.

---

## 🤝 How to Contribute

- **Reporting Bugs**: Open an issue on GitHub describing the steps to reproduce, expected behavior, actual behavior, and container logs.
- **Feature Requests**: Open an issue detailing the use case, proposed architecture, and benefit to the community.
- **Pull Requests**: Fork the repository, create a topic branch, implement your changes with tests/validations, and submit a PR.

---

## 🛠️ Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/JishnuPG-tech/Project.git
   cd Project
   ```
2. **Environment File**:
   Copy `.env.example` to `.env` and set local test secrets.
3. **Syntax Checks**:
   - Python: `python -m py_compile gateway/*.py proxy.py tg_streamer.py`
   - Shell: `bash -n entrypoint.sh`

---

## 🔀 Pull Request Process

1. **Branch Naming**: Use descriptive branch names like `feat/new-router`, `fix/hermes-config`, `docs/update-readme`.
2. **Commit Messages**: Follow Conventional Commits:
   - `feat(gateway): add new endpoint for agent metrics`
   - `fix(hermes): resolve port binding configuration`
   - `docs(readme): add client integration examples`
3. **Architecture Verification**: Ensure your changes adhere to the locked architecture documents ([`ARCHITECTURE.md`](ARCHITECTURE.md), [`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md), [`OPENWEBUI_ARCHITECTURE.md`](OPENWEBUI_ARCHITECTURE.md)).

---

## 🔒 Coding & Architecture Standards

- **No Hardcoded Secrets**: Secrets must be loaded via environment variables or secret store.
- **Persistent Volume Safety**: All writable state must sync to `/data/` volumes to survive container restarts.
- **Non-Blocking Proxies**: Use async HTTP client (`httpx` / `aiohttp`) for high-throughput routing.
