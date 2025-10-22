# Copilot Instructions for KAJAK_KENU Codebase

## Project Overview
- This is a modular Flask application inspired by the Flask official tutorial.
- Main app logic, blueprints, templates, and static files are in `flaskr/`.
- Tests and fixtures are in `tests/`.
- Uses `pyproject.toml` for dependency management and `.venv/` for the virtual environment.

## Key Components
- `flaskr/__init__.py`: App factory and blueprint registration.
- `flaskr/db.py` & `flaskr/schema.sql`: Database connection and schema setup.
- `flaskr/auth.py`, `flaskr/blog.py`: Blueprints for authentication and blog features.
- `flaskr/templates/`: Jinja2 templates for UI, organized by feature.
- `flaskr/static/style.css`: Main stylesheet.
- `tests/`: Pytest-based tests for each major module.

## Developer Workflows
- **Setup:**
  - Create a virtual environment in `.venv/` and install dependencies from `pyproject.toml`.
- **Run App:**
  - Use Flask CLI: `flask --app flaskr run` (ensure `.venv` is activated).
- **Database:**
  - Initialize with `flask --app flaskr init-db` (runs schema from `schema.sql`).
- **Testing:**
  - Run all tests with `pytest` from the project root.

## Project Conventions
- Blueprints are used for modularity (`auth`, `blog`).
- Templates are grouped by feature in subfolders.
- Test files are named `test_*.py` and mirror the structure of `flaskr/`.
- Use fixtures in `tests/conftest.py` for app/test client setup.
- Static files are minimal and located in `flaskr/static/`.

## Integration Points
- No external APIs or services are integrated by default.
- Database is SQLite, managed via `db.py` and `schema.sql`.

## Examples
- To add a new feature, create a new blueprint in `flaskr/`, add templates/static as needed, and register it in `__init__.py`.
- To add tests, create a new `test_*.py` in `tests/` and use fixtures from `conftest.py`.

## References
- See `README.md` for directory structure and additional notes.
- Key files: `flaskr/__init__.py`, `flaskr/db.py`, `flaskr/auth.py`, `flaskr/blog.py`, `tests/conftest.py`.

---

Update this file if you introduce new blueprints, workflows, or conventions.
