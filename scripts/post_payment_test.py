import os
from dotenv import load_dotenv
load_dotenv()
from flaskr import create_app
from flaskr.db import get_db

config = {
    'TESTING': True,
    'SECRET_KEY': 'X' * 32,
    'WTF_CSRF_ENABLED': False,
}
app = create_app(config)
with app.app_context():
    db = get_db()
    tour = db.execute('SELECT id, price, max_participants FROM tours WHERE is_active = 1 ORDER BY date LIMIT 1').fetchone()
    if not tour:
        raise SystemExit('No active tour found.')
    tour_id = tour['id']
    price = tour['price']

client = app.test_client()
data = {
    'tour_id': tour_id,
    'customer_name': 'Test User',
    'customer_email': 'test@example.com',
    'customer_phone': '+36100112233',
    'participants_count': 1,
    'lifejacket_sizes[]': ['90+ kg'],
    'invoice_name': 'Test User',
    'invoice_country': 'hu',
    'invoice_zip': '1011',
    'invoice_city': 'Budapest',
    'invoice_address': 'Test street 1',
    'invoice_company': '',
    'notes': 'Testing',
    'accept_terms': 'on',
    'simplepay_data_transfer': 'on',
}
response = client.post('/payment/start', data=data, follow_redirects=False)
print('status', response.status_code)
print('headers', response.headers)
print('location', response.headers.get('Location'))
print('data', response.data[:200])
