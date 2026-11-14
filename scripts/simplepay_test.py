import os
from dotenv import load_dotenv
load_dotenv()
from flaskr.services.simplepay_service import SimplePayService
merchant = os.environ.get('SIMPLEPAY_MERCHANT_ID')
secret = os.environ.get('SIMPLEPAY_SECRET_KEY')
sandbox = os.environ.get('SIMPLEPAY_SANDBOX', 'true').lower() == 'true'
service = SimplePayService(merchant, secret, sandbox)
payment_data = service.prepare_payment_data(
    order_ref='DEMO-TEST-123',
    amount=1000,
    customer_email='demo@example.com',
    customer_name='Demo User',
    customer_phone='+36100112233',
    invoice_data={
        'name': 'Demo User',
        'country': 'HU',
        'city': 'Budapest',
        'zip': '1011',
        'address': 'Demo Street 1',
        'company': ''
    },
    success_url='https://example.com/success',
    fail_url='https://example.com/fail',
    cancel_url='https://example.com/cancel',
    timeout_url='https://example.com/timeout',
)
success, payment_url, response = service.start_payment(payment_data)
print('success=', success)
print('payment_url=', payment_url)
print('response=', response)
