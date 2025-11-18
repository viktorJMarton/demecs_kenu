import os
import sys

os.environ.setdefault('SECRET_KEY', '12345678901234567890123456789012')
os.environ.setdefault('ADMIN_USERS_JSON', '[{"username":"demo","password":"demo1234"}]')
os.environ.setdefault('SIMPLEPAY_MERCHANT_ID', 'demo')
os.environ.setdefault('SIMPLEPAY_SECRET_KEY', 'demo')

import pytest

if __name__ == '__main__':
    raise SystemExit(pytest.main())
