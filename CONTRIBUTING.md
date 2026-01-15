# Contributing to Suzent

Thank you for your interest in contributing to Suzent! This guide will help you get started.

## 🐛 Reporting Bugs

1. **Search existing issues** first to avoid duplicates
2. Open a new issue with:
   - Clear title describing the problem
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, browser)
   - Relevant logs or screenshots

## 💡 Suggesting Features

1. Check if the feature has been requested already
2. Open a new issue describing:
   - The problem you're trying to solve
   - Your proposed solution
   - Alternative approaches you've considered

## 🔧 Development Setup

### Prerequisites
- Python 3.12+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker (optional, for services)

### Backend Setup
```bash
# Clone the repository
git clone https://github.com/cyzus/suzent.git
cd suzent

# Create virtual environment and install dependencies
uv sync

# Copy environment file
cp .env.example .env
# Edit .env and add at least one API key

# Run the backend
python src/suzent/server.py
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### Running with Docker (Services)
```bash
# Start PostgreSQL, Redis, and SearXNG
docker compose -f docker/docker-compose.yml up -d
```

## 📝 Code Style

### Python
- Follow PEP 8 guidelines
- Use type hints where possible
- Keep functions focused and well-documented
- Run `ruff check` before committing

### TypeScript/React
- Use functional components with hooks
- Follow existing patterns in the codebase
- Keep components focused on single responsibilities

## 🔀 Pull Request Process

1. **Fork** the repository
2. **Create a branch** for your feature/fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** with clear, focused commits
4. **Test your changes** locally
5. **Push** to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
6. **Open a Pull Request** with:
   - Clear description of changes
   - Link to related issues
   - Screenshots/recordings for UI changes

### PR Checklist
- [ ] Code follows project style guidelines
- [ ] Changes have been tested locally
- [ ] Documentation updated if needed
- [ ] No unnecessary changes to unrelated files

## 📁 Project Structure

```
suzent/
├── src/suzent/          # Python backend
│   ├── routes/          # API endpoints
│   ├── tools/           # Agent tools
│   └── memory/          # Memory system
├── frontend/            # React frontend
│   ├── src/components/  # UI components
│   ├── src/hooks/       # React contexts
│   └── src/lib/         # API clients
├── docker/              # Docker configurations
└── docs/                # Documentation
```

## ❓ Questions?

- Open a [GitHub Discussion](https://github.com/YOUR_USERNAME/suzent/discussions)
- Check the [documentation](./docs/)

---

Thank you for contributing! 🎉
