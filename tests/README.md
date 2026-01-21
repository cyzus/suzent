# Test Suite

This directory contains the test suite for Suzent.

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── test_core_utils.py       # Core utility functions
├── test_database.py         # Database operations (SQLModel)
├── test_lancedb_store.py    # Memory store operations (LanceDB)
├── test_memory_models.py    # Memory system models
├── test_sandbox.py          # Sandbox execution tests
└── tools/
    └── test_websearch_tool.py  # Web search tool tests
```

## Running Tests

### Run all tests
```bash
pytest
```

### Run specific test file
```bash
pytest tests/test_database.py -v
```

### Run tests by marker
```bash
# Run only fast tests (skip sandbox, slow, and stress tests)
pytest -m "not sandbox and not slow and not stress"

# Run sandbox tests
pytest -m sandbox

# Run slow tests
pytest -m slow

# Run stress tests
pytest -m stress
```

### Run with coverage
```bash
pytest --cov=suzent --cov-report=html
```

## Test Markers

- `sandbox`: Tests requiring microsandbox server (external dependency)
- `integration`: Tests requiring external services
- `slow`: Tests that take significant time
- `stress`: Load/stress tests for stability verification

## Test Categories

### Unit Tests
Fast, isolated tests for individual components:
- `test_core_utils.py` - JSON encoding, serialization
- `test_database.py` - Database CRUD operations
- `test_memory_models.py` - Pydantic model validation
- `test_websearch_tool.py` - Tool mocking and behavior

### Integration Tests
Tests requiring external services:
- `test_lancedb_store.py` - Vector database operations (async)
- `test_sandbox.py` - Sandbox execution (requires microsandbox server)

### Stress Tests
Long-running tests for stability:
- `test_sandbox.py::TestStress` - Rapid cycles, concurrent operations

## Prerequisites

### For all tests
```bash
uv pip install -e ".[dev]"
```

### For sandbox tests
Sandbox tests require a running microsandbox server:

1. Start the server (WSL2 with KVM support):
   ```bash
   docker compose -f docker/sandbox-compose.yml up -d
   ```

2. Wait 30-60 seconds for initialization

3. Run sandbox tests:
   ```bash
   pytest -m sandbox -v
   ```

### For memory store tests
Tests use a temporary LanceDB instance (no external setup required).

## Writing Tests

### Use shared fixtures
```python
def test_example(temp_db, unique_id):
    """Use shared fixtures from conftest.py."""
    chat_id = temp_db.create_chat(f"Test {unique_id}", {})
    assert chat_id is not None
```

### Add appropriate markers
```python
@pytest.mark.slow
def test_long_operation():
    """Mark tests appropriately."""
    pass
```

### Async tests
```python
@pytest.mark.asyncio
async def test_async_operation():
    """Async tests work automatically with asyncio_mode = 'auto'."""
    pass
```

## Continuous Integration

Fast tests run on every commit:
```bash
pytest -m "not sandbox and not slow and not stress"
```

Full test suite runs on release branches:
```bash
pytest -v
```
