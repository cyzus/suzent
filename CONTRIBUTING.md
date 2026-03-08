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
cd src-tauri
npm install
npm run dev
```

## 📝 Code Style

### Python
- Follow PEP 8 guidelines
- Use type hints where possible
- Keep functions focused and well-documented
- Run `pre-commit run --all-files` before committing

### TypeScript/React
- Use functional components with hooks
- Follow existing patterns in the codebase
- Keep components focused on single responsibilities

## 📊 Logging Guidelines

Consistent logging is critical for debugging and monitoring. Follow these guidelines:

### Log Levels

**DEBUG** - Development & detailed diagnostics
- Function entry/exit, variable values
- Performance metrics, state transitions
- Example: `logger.debug(f"Processing chat_id={chat_id}")`

**INFO** - Important state changes
- Service lifecycle (start/stop)
- Successful major operations
- User actions, background tasks
- Example: `logger.info("SocialBrain started")`

**WARNING** - Recoverable issues
- Deprecated features, fallback behavior
- Non-critical failures (will retry)
- Resource limits approaching
- Example: `logger.warning(f"Falling back to LiteLLM for {model}")`

**ERROR** - Action required
- Operation failed, cannot continue
- Data loss, external service failures
- Security violations, uncaught exceptions
- Example: `logger.error(f"Operation failed: {e}\\n{traceback}")`

### Best Practices

✅ **Do**:
- Include context (IDs, parameters)
- Use past tense for completed actions
- Add stack traces for errors
- Keep it actionable

❌ **Don't**:
- Log secrets or credentials
- Log PII (emails, names)
- Create high-frequency noise
- Use vague messages

### Example Pattern
```python
try:
    result = await operation(chat_id)
    logger.info(f"Operation completed for {chat_id}")
except Exception as e:
    logger.error(f"Operation failed for {chat_id}: {e}\\n{traceback.format_exc()}")
    raise
```

See full guidelines in the codebase documentation.

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

## Roadmap

Suzent is evolving rapidly and trying to keep up with the cutting-edge agent development.
We are prioritizing:

- Stability - fix bugs
- UX - providing a unique and intuitive user experience
- Memory Management - improving the memory/workspace logic


## ❓ Questions?

- Open a [GitHub Discussion](https://github.com/YOUR_USERNAME/suzent/discussions)
- Check the [documentation](./docs/)

---

Thank you for contributing! 🎉
