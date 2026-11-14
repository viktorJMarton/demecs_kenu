# KAJAK-KENU Structure & Principles

This note distills how the current repository is organized and the conventions we should reinforce when extending it. It blends DRY thinking, Flask idioms, and clean-code heuristics so that new work stays consistent.

---

## 1. High-Level Layout

```text
source/
├─ flaskr/                     # Main Flask package
│  ├─ main.py                  # App factory + public routes
│  ├─ auth.py                  # Admin authentication blueprint
│  ├─ payment.py               # SimplePay blueprint
│  ├─ events.py                # Server-sent events broadcaster
│  ├─ admin/                   # Modular admin views (dashboard, tours, bookings)
│  ├─ services/                # Business logic (tour service, SimplePay service)
│  ├─ models.py                # Dataclass wrappers for DB rows
│  ├─ db.py / schema.sql       # DB helpers + schema
│  ├─ templates/               # Feature-scoped Jinja views + partials
│  └─ static/                  # JS/CSS assets (+ compiled Tailwind output in public/)
│
├─ public/uploads/             # Runtime media served via /uploads
├─ test/                       # Modern test suite (endpoint/integration/route/unit)
├─ legacy tests & scripts      # `test_*.py`, data migration, diagnostics
├─ node_modules/, tailwind.*   # Frontend build toolchain
├─ requirements.txt / package.json
└─ docs (*.md, setup guides)
```

Key idea: keep HTTP-layer code in blueprints, push business rules into `services/`, and model/DB glue into `models.py` + `db.py`.

---

## 2. Module Responsibilities

### App Factory & Config (`flaskr/main.py`)

- Central `create_app()` wires config from `.env`, registers blueprints, and exposes convenience routes (index/tour detail/API uploads/booking form).
- `UPLOADS_ROOT` points at `public/uploads`, so any new file-serving route should derive from this config instead of recomputing paths.
- Session lifetime and DB path are configured once; reuse `current_app.config` instead of hardcoding values.

### Database Layer (`flaskr/db.py`, `schema.sql`)

- `get_db()` lazily opens SQLite and auto-runs schema if tables are missing—avoid duplicating schema bootstrap logic elsewhere.
- CLI command `flask --app flaskr init-db` already exposed; use this for fresh environments/tests instead of ad-hoc SQL scripts when possible.

### Blueprints

- **`auth`** handles session-based admin login with decorator `login_required`; import the decorator instead of rolling custom guards.
- **`events`** exposes `/events` SSE for dashboard updates plus helper broadcasters (`broadcast_tour_update`, etc.). Use these helpers from services/admin flows to keep push logic centralized.
- **`payment`** orchestrates SimplePay flows, delegates API calls to `SimplePayService`, and owns booking/payment state transitions.
- **`admin` package** splits dashboard/statistics, tour CRUD, and booking management; all admin routes share `/admin` prefix via their blueprint definitions.

### Services & Models

- `services/tour_service.py` and `services/simplepay_service.py` encapsulate DB queries and external API communication. New business logic should live beside them (e.g., `booking_service.py`) to keep views thin.
- `models.py` houses dataclasses (`Tour`, `Booking`, `User`) with `from_db_row` helpers for type-safe usage; prefer these instead of manipulating raw `sqlite3.Row` objects deep in the stack.

### Templates & Static Assets

- Templates are organized by feature (`templates/admin`, `templates/payment`, `templates/partials`). Reuse partials like `partials/tour_details.html` or create new ones under `partials/` when UI chunks are shared between modal/API responses.
- Static JS such as `calendar-modal.js`, `realtime.js`, and CSS sources under `static/src/` feed into Tailwind/PostCSS outputs emitted to `public/output.css`. Keep generated files out of Git when possible and document build steps in README.

### Tests

- Primary suite under `test/` is grouped by concern (endpoint/integration/route/unit) and configured via `test/conftest.py` fixtures. Use markers (`@pytest.mark.integration`, etc.) to control scope.
- Legacy quick scripts (`test_api.py`, `test_static_files.py`) still exist at repo root. If we modernize them, migrate into the structured `test/` tree.

### Ops & Tooling Scripts

- SQL migration helpers (`add_image_columns.sql`, `database_migration.sql`, `init_db.py`) and diagnostic utilities (`check_tours.py`, `migrate_tour_images.py`) live at the root. When adding new maintenance scripts, prefix them clearly and document in `ADMIN_README.md` to avoid tribal knowledge.

---

## 3. DRY Guardrails (Project-Specific)

1. **Centralize DB access** – use `get_db()` everywhere; if a function needs raw connections outside request context, add helper wrappers instead of opening new `sqlite3` connections.
2. **Reuse services** – if both admin and public routes need tour queries, extend `tour_service.py` with new functions rather than duplicating SQL in blueprints.
3. **Shared UI pieces** – render repeated fragments (tour cards, booking forms, status badges) via Jinja macros/partials under `templates/partials/`. Avoid copying modal markup into multiple templates.
4. **Consistent event broadcasting** – call `broadcast_*` helpers in `events.py` whenever a CRUD action should notify dashboards; do not inline SSE queue logic.
5. **Configuration via `current_app.config`** – secrets, file paths, and feature flags belong in config or `.env`, not hardcoded strings.
6. **Logging & error messages** – route-level handlers (like payment) already log to `logger`; extend existing loggers instead of introducing isolated `print` statements.

---

## 4. Flask Coding Principles to Enforce

- **App Factory Pattern**: keep extensions/blueprints registered inside `create_app()`; new blueprints should expose `bp` objects and be imported at registration time only.
- **Blueprint Isolation**: define `url_prefix`, templates, and permission checks per blueprint. Admin-only routes must import `login_required` rather than duplicating session checks.
- **Context-Aware DB Calls**: rely on `g` + teardown hooks to close DB connections. Background scripts should use `app.app_context()` when reusing application factories.
- **Config Separation**: `.env` feeds `SECRET_KEY`, DB URL, SimplePay credentials, etc. Add new config keys in one place (preferably `create_app()` or dedicated config objects) and document them in `SIMPLEPAY_SETUP.md` or README.
- **Error Handling & Flashing**: follow the pattern in `payment.start_payment`—validate inputs, collect errors, flash with severity tags, then redirect. Keep user-facing messages localized (HU) for consistency.
- **Static Assets Pipeline**: when touching CSS/JS, source edits go to `flaskr/static/src/` and compile through Tailwind/PostCSS. Document the build step in `package.json` scripts to avoid manual drift.
- **CLI Integrations**: use Click commands (e.g., `init-db`) for maintenance tasks. If a new script needs app context, consider exposing it as a CLI command instead of a standalone `.py` file when feasible.

---

## 5. Clean Code Heuristics Tailored to This Repo

- **Naming**: Keep English module/class names (e.g., `admin_bookings.py`) while allowing Hungarian UX copy in templates. Function names should describe intent (`start_payment`, `get_upcoming_tours`).
- **Function Scope**: Views should orchestrate request/response logic and delegate heavy lifting to services/models. If a route grows beyond ~40 lines, extract helpers.
- **Validation Strategy**: Collect validation errors in lists (as seen in `payment.start_payment`) and return early. Mirror this pattern in future forms to keep code uniform.
- **Type Hints & Dataclasses**: Services already use typing (e.g., `List[Tour]`). Extend hints for new functions and prefer dataclasses/model methods for data transformations.
- **Logging and Exceptions**: Use the module-level `logger` to capture errors with `exc_info=True`. Surface friendly flashes but keep tracebacks in logs for debugging.
- **Tests First Mindset**: When adding features, decide which layer it touches and place tests accordingly (unit vs. route vs. integration). Use fixtures from `test/conftest.py` to avoid manual DB seeding.
- **Documentation & TODOs**: Update `ARCHITECTURE_NOTES.md`, `README.md`, or `ADMIN_README.md` whenever new blueprints/services/scripts appear so future contributors see the intended flow.

---

## 6. Quick Checklist Before Shipping Changes

- [ ] Does the change live in the appropriate blueprint/service/module without duplicating logic?
- [ ] Are config/secrets pulled from environment or `current_app.config`?
- [ ] Did we reuse existing partials/components or create new shared ones?
- [ ] Are new background effects broadcasting through `events.py` helpers?
- [ ] Do new modules include tests and documentation updates?
- [ ] Did we run `pytest` (or targeted markers) and the relevant frontend build step?

Keeping these guardrails in mind should help us extend the KAJAK-KENU app confidently while staying DRY, idiomatic to Flask, and easy to maintain.
