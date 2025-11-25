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

## Environment configuration

- Copy `.env` (or set the variables elsewhere) before starting the app.
- `SECRET_KEY`, `DATABASE_URL`, `ADMIN_USERS_JSON` (or `ADMIN_USERNAME` + `ADMIN_PASSWORD[_HASH]`), SimplePay credentials (`SIMPLEPAY_MERCHANT_ID`, `SIMPLEPAY_SECRET_KEY`), and SMTP settings (`EMAIL_SMTP_*`, `EMAIL_FROM`, `CONTACT_RECIPIENT`) must all be present in the environment.
- The included `.env` file contains a hashed example admin user so the app boots without runtime errors; replace it with production values in your deployment.

### SimplePay operational checklist

- **Branding & consent**: The booking templates (`partials/booking_form*.html`) already include the official SimplePay logomark and the kötelező adattovábbítási nyilatkozat checkbox. If you customise the checkout UI, keep these elements visible and unchecked by default.
- **Callback URLs**: `/payment/success|fail|cancel|timeout` now verify the signed `r` + `s` query parameters before updating bookings. Ensure the same URLs are configured inside the SimplePay admin surface.
- **Reconciliation**: Admins can POST to `/payment/sync` with an `order_ref` or `transaction_id` to trigger the SimplePay `/query` endpoint and refresh local transaction states when an IPN is delayed.
- **Reference**: See `SIMPLEPAY_SETUP.md` for the full integration guide (timeouts, signature headers, and troubleshooting).
