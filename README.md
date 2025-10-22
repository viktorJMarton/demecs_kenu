# Project Documentation

## Project Directory Structure

```
source/
│
├── flaskr/
│   ├── __init__.py
│   ├── db.py
│   ├── schema.sql
│   ├── auth.py
│   ├── blog.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   └── register.html
│   │   └── blog/
│   │       ├── create.html
│   │       ├── index.html
│   │       └── update.html
│   └── static/
│       └── style.css
├── tests/
│   ├── conftest.py
│   ├── data.sql
│   ├── test_factory.py
│   ├── test_db.py
│   ├── test_auth.py
│   └── test_blog.py
├── .venv/
├── pyproject.toml
└── MANIFEST.in
```

## Notes

- This structure is inspired by the Flask official tutorial and is suitable for modular, testable Flask applications.
- Place your virtual environment in `.venv/`.
- Use `pyproject.toml` for dependency management if you prefer modern Python packaging.
- `MANIFEST.in` is for packaging data files.
- The `flaskr` package contains the main app logic, blueprints, templates, and static files.
- The `tests` folder contains test modules and fixtures.