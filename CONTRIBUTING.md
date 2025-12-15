# Contributing to Suzent

Thank you for your interest in contributing to Suzent! This document provides guidelines and instructions for contributing.

## Development Setup

### Quick Start

1. Clone the repository:
```bash
git clone https://github.com/cyzus/suzent.git
cd suzent
```

2. Run the setup script:
```bash
./scripts/setup_dev.sh
```

3. Configure your environment:
```bash
# Edit .env with your API keys
cp .env.example .env
nano .env
```

### Manual Setup

If you prefer manual setup or the script doesn't work:

**Backend:**
```bash
# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --extra dev

# Install Playwright
uv run playwright install chromium
```

**Frontend:**
```bash
cd frontend
npm install
```

## Development Workflow

### Running the Application

**Backend (Terminal 1):**
```bash
python src/suzent/server.py
# Runs on http://localhost:8000
```

**Frontend (Terminal 2):**
```bash
cd frontend
npm run dev
# Runs on http://localhost:5173
```

### Running Tests

**Backend tests:**
```bash
uv run pytest test/ -v
```

**Frontend type checking:**
```bash
cd frontend
npx tsc --noEmit
```

### Code Quality

**Python linting:**
```bash
uv run ruff check src/
uv run ruff format src/  # Auto-format
```

**Frontend linting:**
```bash
cd frontend
npm run lint  # If configured
```

## Project Structure

```
suzent/
├── src/suzent/          # Python backend
│   ├── routes/          # API endpoints
│   ├── tools/           # Agent tools
│   └── memory/          # Memory system
├── frontend/            # React frontend
│   ├── src/
│   │   ├── components/  # React components
│   │   ├── hooks/       # React hooks
│   │   └── lib/         # Utilities
├── test/                # Tests
│   ├── unit/            # Unit tests
│   └── integration/     # Integration tests
├── config/              # Configuration files
└── docs/                # Documentation
```

## Contributing Guidelines

### Before You Start

1. Check existing issues and PRs to avoid duplicates
2. For major changes, open an issue first to discuss
3. Follow the existing code style and patterns
4. Write tests for new features
5. Update documentation as needed

### Making Changes

1. Fork the repository
2. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. Make your changes following these guidelines:
   - **Code Style**: Follow PEP 8 for Python, use Prettier defaults for TypeScript
   - **Commits**: Write clear, descriptive commit messages
   - **Tests**: Add tests for new functionality
   - **Documentation**: Update relevant docs

4. Test your changes:
   ```bash
   # Run backend tests
   uv run pytest test/ -v
   
   # Run linter
   uv run ruff check src/
   
   # Build frontend
   cd frontend && npm run build
   ```

5. Commit and push:
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   git push origin feature/your-feature-name
   ```

6. Open a Pull Request with:
   - Clear description of changes
   - Link to related issues
   - Screenshots for UI changes
   - Test results

### Commit Message Format

Follow conventional commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Adding tests
- `refactor:` Code refactoring
- `style:` Formatting changes
- `chore:` Maintenance tasks

Examples:
- `feat: add chat export functionality`
- `fix: resolve streaming timeout issue`
- `docs: update API reference`

## Adding New Features

### Adding a New Tool

1. Create `src/suzent/tools/yourtool_tool.py`:
```python
from smolagents.tools import Tool

class YourTool(Tool):
    name = "your_tool"
    description = "Clear description for the LLM"
    inputs = {
        "input_name": {
            "type": "string",
            "description": "Input description"
        }
    }
    output_type = "string"
    
    def forward(self, input_name: str) -> str:
        # Implementation
        return result
```

2. Register in `src/suzent/agent_manager.py`:
```python
tool_module_map = {
    # ... existing tools
    "YourTool": "suzent.tools.yourtool_tool",
}
```

3. Add to default tools in `config/default.example.yaml`:
```yaml
DEFAULT_TOOLS:
  - "YourTool"
```

4. Write tests in `test/unit/test_yourtool.py`

### Adding API Endpoints

1. Create route handler in `src/suzent/routes/your_routes.py`
2. Import and register in `src/suzent/server.py`
3. Update API documentation
4. Add integration tests

### Adding Frontend Components

1. Create component in `frontend/src/components/`
2. Follow existing patterns (TypeScript, Tailwind CSS)
3. Use brutal design system (see `AGENTS.md`)
4. Add to appropriate parent component

## Testing

### Writing Tests

**Unit tests** (test/unit/):
```python
def test_your_feature(chat_db, sample_chat):
    """Test description."""
    result = your_function(chat_db, sample_chat)
    assert result == expected
```

**Integration tests** (test/integration/):
```python
async def test_api_endpoint():
    """Test API endpoint."""
    response = await client.get("/your-endpoint")
    assert response.status_code == 200
```

### Test Coverage

Aim for:
- New features: 80%+ coverage
- Bug fixes: Add regression test
- Critical paths: 90%+ coverage

## Documentation

### Updating Documentation

When adding features, update:
- `README.md` - Overview and quick start
- `AGENTS.md` - Developer guide
- `docs/` - Detailed documentation
- API docstrings
- Configuration examples

### Documentation Standards

- Clear and concise
- Include code examples
- Show expected output
- Link related docs

## Code Review Process

### What We Look For

- **Functionality**: Does it work as intended?
- **Tests**: Are there adequate tests?
- **Code Quality**: Is it readable and maintainable?
- **Performance**: Any performance concerns?
- **Security**: Any security implications?
- **Documentation**: Is it well documented?

### Review Timeline

- Initial review: 1-3 days
- Follow-up: 1-2 days
- Merge: After approval + passing CI

## Getting Help

- **Issues**: Open an issue for bugs or questions
- **Discussions**: Use GitHub Discussions for general questions
- **Documentation**: Check `AGENTS.md` and `docs/`

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Credited in release notes
- Appreciated by the community! 🎉

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.

---

Thank you for contributing to Suzent! 🚀
