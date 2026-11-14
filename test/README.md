# Test Suite Documentation

This directory contains the comprehensive test suite for the KAJAK-KENU Flask application, organized by test type for better maintainability and execution control.

## Test Structure

```
test/
├── conftest.py              # Shared test configuration and fixtures
├── endpoint_tests/          # HTTP endpoint and API tests
│   ├── __init__.py
│   └── test_endpoints.py
├── integration_tests/       # Full system integration tests
│   ├── __init__.py
│   └── test_integration.py
├── route_tests/             # Backend route logic tests
│   ├── __init__.py
│   └── test_routes.py
└── unit_tests/              # Individual function/class tests
    ├── __init__.py
    └── test_units.py
```

## Test Types

### 🔗 Endpoint Tests (`endpoint_tests/`)
- Test HTTP requests and responses
- Verify API endpoints functionality
- Check authentication and authorization
- Examples: Homepage loading, admin dashboard access

### 🔄 Integration Tests (`integration_tests/`)
- Test complete workflows end-to-end
- Include database operations
- Verify component interactions
- Examples: Full booking flow, admin workflows

### 🛣️ Route Tests (`route_tests/`)
- Test backend route handler logic
- Focus on business rules and validation
- Mock external dependencies
- Examples: Form validation, permission checks

### 🧩 Unit Tests (`unit_tests/`)
- Test individual functions and classes
- Isolate components with mocks
- Fast execution, high coverage
- Examples: Model methods, service functions

## Running Tests

### All Tests
```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=flaskr --cov-report=html
```

### Specific Test Types
```bash
# Run only endpoint tests
pytest -m endpoint

# Run only integration tests
pytest -m integration

# Run only route tests
pytest -m route

# Run only unit tests
pytest -m unit
```

### Specific Test Files
```bash
# Run specific test file
pytest test/endpoint_tests/test_endpoints.py

# Run specific test function
pytest test/unit_tests/test_units.py::TestModels::test_tour_model_creation
```

### Test Execution Options
```bash
# Stop on first failure
pytest -x

# Show print statements
pytest -s

# Run tests in parallel (requires pytest-xdist)
pytest -n auto

# Run only slow tests
pytest -m slow

# Skip slow tests
pytest -m "not slow"
```

## Test Configuration

### Fixtures
- `app`: Flask test application instance
- `client`: Test client for HTTP requests
- `db_session`: Direct database access for tests
- `auth_client`: Authenticated test client
- `sample_tour_data`: Sample tour data
- `sample_booking_data`: Sample booking data

### Markers
- `@pytest.mark.endpoint`: Endpoint tests
- `@pytest.mark.integration`: Integration tests
- `@pytest.mark.route`: Route tests
- `@pytest.mark.unit`: Unit tests
- `@pytest.mark.slow`: Slow-running tests

## Test Database

Tests use temporary SQLite databases that are created and destroyed for each test session. The database schema is automatically initialized using `flaskr/schema.sql`.

## Best Practices

1. **Test Isolation**: Each test should be independent
2. **Mock External Dependencies**: Use mocks for external APIs, email services, etc.
3. **Descriptive Names**: Test names should clearly describe what they test
4. **Arrange-Act-Assert**: Structure tests with clear setup, execution, and verification
5. **Coverage Goals**: Aim for >80% code coverage
6. **Fast Tests**: Keep unit tests fast, mark slow tests appropriately

## Continuous Integration

These tests are designed to run in CI/CD pipelines. Use the following commands:

```bash
# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-cov

# Run tests with coverage
pytest --cov=flaskr --cov-report=xml --cov-fail-under=80
```

## Adding New Tests

1. Choose the appropriate test directory based on test type
2. Follow the existing naming convention: `test_*.py`
3. Use descriptive test class and method names
4. Include docstrings explaining what each test verifies
5. Use fixtures from `conftest.py` for common setup