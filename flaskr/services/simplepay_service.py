"""SimplePay Payment Gateway Service."""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class SimplePayService:
    """SimplePay API helper that fully follows the v2 spec."""

    SANDBOX_BASE_URL = "https://sandbox.simplepay.hu/payment/v2"
    LIVE_BASE_URL = "https://secure.simplepay.hu/payment/v2"
    HEADER_SIGNATURE = "Signature"
    DEFAULT_SDK_VERSION = "KajakKenu_Flask_2025.11"

    def __init__(self, merchant_id: str, secret_key: str, sandbox: bool = True):
        self.merchant_id = merchant_id
        self.secret_key = secret_key
        self.secret_key_bytes = secret_key.encode("utf-8")
        self.sandbox = sandbox
        self.base_url = self.SANDBOX_BASE_URL if sandbox else self.LIVE_BASE_URL
        self.sdk_version = os.getenv("SIMPLEPAY_SDK_VERSION", self.DEFAULT_SDK_VERSION)
        
    def generate_order_ref(self, booking_id: int) -> str:
        """
        Egyedi order referencia generálása
        
        Args:
            booking_id: Foglalás azonosító
            
        Returns:
            Egyedi order referencia string (pl: ORDER-B123-1234567890)
        """
        timestamp = int(datetime.now().timestamp())
        return f"ORDER-B{booking_id}-{timestamp}"
    
    def _serialize_payload(self, payload: Dict) -> bytes:
        return json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

    def _sign(self, payload: bytes) -> str:
        digest = hmac.new(self.secret_key_bytes, payload, hashlib.sha384).digest()
        return base64.b64encode(digest).decode('ascii')

    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        if not signature:
            return False
        expected = self._sign(payload)
        return hmac.compare_digest(expected, signature)

    def _post(self, endpoint: str, payload: Dict) -> Tuple[int, Dict]:
        body = self._serialize_payload(payload)
        headers = {
            'Content-Type': 'application/json',
            self.HEADER_SIGNATURE: self._sign(body),
        }
        url = f"{self.base_url}/{endpoint}"
        response = requests.post(url, data=body, headers=headers, timeout=30)
        body_bytes = response.content or b''
        incoming_signature = response.headers.get(self.HEADER_SIGNATURE, '')
        if incoming_signature and not self._verify_signature(body_bytes, incoming_signature):
            raise RuntimeError('Invalid signature returned by SimplePay.')
        try:
            data = response.json()
        except json.JSONDecodeError:  # pragma: no cover - defensive
            logger.error('SimplePay response is not valid JSON: %s', response.text)
            raise
        return response.status_code, data

    def decode_signed_payload(self, raw_payload: bytes, signature: str) -> Dict:
        """Validate and decode a signed JSON payload coming from SimplePay."""
        if not self._verify_signature(raw_payload, signature):
            raise ValueError('SimplePay signature verification failed.')
        if not raw_payload:
            return {}
        return json.loads(raw_payload.decode('utf-8'))

    def encode_signed_payload(self, payload: Dict) -> Tuple[str, str]:
        """Serialize payload and return (body, signature)."""
        body_bytes = self._serialize_payload(payload)
        return body_bytes.decode('utf-8'), self._sign(body_bytes)

    def decode_back_payload(self, r_param: str, signature: str) -> Dict:
        """Validate SimplePay back redirect parameters and return the JSON payload."""
        if not r_param or not signature:
            raise ValueError('Missing back redirect parameters.')
        try:
            # Back payload is Base64 encoded JSON (URL safe encoded in querystring)
            padded = r_param + '=' * (-len(r_param) % 4)
            payload_bytes = base64.urlsafe_b64decode(padded)
        except (TypeError, ValueError) as exc:
            raise ValueError('Back payload could not be decoded.') from exc
        if not self._verify_signature(payload_bytes, signature):
            raise ValueError('Invalid SimplePay back signature.')
        return json.loads(payload_bytes.decode('utf-8'))
    
    def prepare_payment_data(
        self,
        order_ref: str,
        amount: int,
        customer_email: str,
        customer_name: str,
        customer_phone: str,
        invoice_data: Dict,
        success_url: str,
        fail_url: str,
        cancel_url: str,
        timeout_url: str,
        language: str = 'HU',
        timeout_minutes: int = 20
    ) -> Dict:
        """
        Fizetési adatok előkészítése SimplePay START kéréshez
        
        Args:
            order_ref: Egyedi megrendelés azonosító
            amount: Összeg (integer, fillérben/centben)
            customer_email: Vásárló email címe
            customer_name: Vásárló neve
            customer_phone: Vásárló telefonszáma
            invoice_data: Számlázási adatok (név, cím, város, irányítószám, ország)
            success_url: Sikeres fizetés után visszairányítási URL
            fail_url: Sikertelen fizetés után visszairányítási URL
            cancel_url: Megszakított fizetés után visszairányítási URL
            timeout_url: Időtúllépés után visszairányítási URL
            language: Fizetési oldal nyelve (HU, EN, DE)
            timeout_minutes: Timeout percben (alapértelmezett 20 perc webes vásárláshoz)
            
        Returns:
            SimplePay API-nak küldendő adatok dictionary
        """
        timeout_dt = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
        timeout_str = timeout_dt.isoformat(timespec='seconds')
        salt = secrets.token_hex(16)
        
        payment_data = {
            'salt': salt,
            'merchant': self.merchant_id,
            'orderRef': order_ref,
            'currency': 'HUF',
            'total': str(amount),
            'timeout': timeout_str,
            'methods': ['CARD'],  # Bankkártyás fizetés
            'sdkVersion': self.sdk_version,
            'customer': customer_name,
            'customerEmail': customer_email,
            'language': language,
            'invoice': {
                'name': invoice_data.get('name', customer_name),
                'country': invoice_data.get('country', 'hu'),
                'state': invoice_data.get('state', ''),
                'city': invoice_data.get('city', ''),
                'zip': invoice_data.get('zip', ''),
                'address': invoice_data.get('address', ''),
                'company': invoice_data.get('company', ''),
                'phone': invoice_data.get('phone', customer_phone)
            },
            'urls': {
                'success': success_url,
                'fail': fail_url,
                'cancel': cancel_url,
                'timeout': timeout_url
            },
            'threeDSReqAuthMethod': invoice_data.get('threeDSReqAuthMethod', '01')
        }
        
        return payment_data
    
    def start_payment(self, payment_data: Dict) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Fizetés indítása SimplePay-nél (START endpoint)
        
        Args:
            payment_data: Előkészített fizetési adatok (signature-rel együtt)
            
        Returns:
            Tuple: (success: bool, payment_url: str or None, response_data: dict or None)
        """
        try:
            logger.info(f"Starting payment for order: {payment_data.get('orderRef')}")
            logger.debug("Payment data: %s", json.dumps(payment_data, indent=2, ensure_ascii=False))

            status_code, response_data = self._post('start', payment_data)
            logger.info("SimplePay START response: %s", status_code)
            logger.debug("Response data: %s", json.dumps(response_data, indent=2, ensure_ascii=False))

            if status_code == 200 and response_data.get('paymentUrl'):
                payment_url = response_data['paymentUrl']
                logger.info(f"Payment URL received: {payment_url}")
                return True, payment_url, response_data
            else:
                error_msg = response_data.get('errorCodes', ['Unknown error'])
                logger.error(f"SimplePay START failed: {error_msg}")
                return False, None, response_data
                
        except requests.RequestException as e:
            logger.error("SimplePay START request failed: %s", str(e))
            return False, None, {'error': str(e)}
        except Exception as e:  # pragma: no cover - defensive
            logger.error("Unexpected error in start_payment: %s", str(e))
            return False, None, {'error': str(e)}
    
    def process_ipn(self, raw_body: bytes, signature: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        IPN (Instant Payment Notification) feldolgozása
        
        Args:
            raw_body: SimplePay IPN POST raw body
            signature: Signature header értéke
            
        Returns:
            Tuple: (success: bool, status: str, data: dict or None)
        """
        try:
            ipn_data = self.decode_signed_payload(raw_body, signature)
            status = ipn_data.get('status', '').upper()
            order_ref = ipn_data.get('orderRef', '')
            transaction_id = ipn_data.get('transactionId', '')
            logger.info("IPN received for order %s: status=%s, transaction_id=%s", order_ref, status, transaction_id)
            return True, status, ipn_data
        except Exception as e:
            logger.error("Error processing IPN: %s", str(e))
            return False, 'PROCESSING_ERROR', None
    
    def initiate_refund(self, transaction_id: str, order_ref: str, amount: int) -> Tuple[bool, Optional[Dict]]:
        """
        Visszatérítés (refund) indítása
        
        Args:
            transaction_id: SimplePay tranzakció azonosító
            order_ref: Eredeti megrendelés azonosító
            amount: Visszatérítendő összeg
            
        Returns:
            Tuple: (success: bool, response_data: dict or None)
        """
        refund_data = {
            'salt': secrets.token_hex(16),
            'merchant': self.merchant_id,
            'orderRef': order_ref,
            'transactionId': transaction_id,
            'refundAmount': str(amount),
            'sdkVersion': self.sdk_version,
        }
        try:
            logger.info("Initiating refund for transaction %s, order %s", transaction_id, order_ref)
            status_code, response_data = self._post('refund', refund_data)
            logger.info("SimplePay REFUND response: %s", status_code)
            logger.debug("Response data: %s", json.dumps(response_data, indent=2, ensure_ascii=False))
            if status_code == 200:
                return True, response_data
            logger.error("SimplePay REFUND failed: %s", response_data)
            return False, response_data
        except Exception as e:
            logger.error("Error initiating refund: %s", str(e))
            return False, {'error': str(e)}

    def query_transactions(
        self,
        order_refs: Optional[List[str]] = None,
        transaction_ids: Optional[List[str]] = None,
    ) -> Dict:
        """Fetch transaction data via /query (supports both orderRef and transactionId)."""
        if not order_refs and not transaction_ids:
            raise ValueError('At least one orderRef or transactionId is required for query.')
        payload: Dict[str, object] = {
            'merchant': self.merchant_id,
            'salt': secrets.token_hex(16),
            'sdkVersion': self.sdk_version,
        }
        if order_refs:
            payload['orderRefs'] = order_refs
        if transaction_ids:
            payload['transactionIds'] = transaction_ids
        status_code, response_data = self._post('query', payload)
        if status_code != 200:
            raise RuntimeError(f"SimplePay query failed: {response_data}")
        return response_data

    def finish_transaction(
        self,
        transaction_id: str,
        approve_total: int,
        original_total: Optional[int] = None,
    ) -> Dict:
        """Call the FINISH endpoint for two-step captures."""
        payload = {
            'merchant': self.merchant_id,
            'salt': secrets.token_hex(16),
            'transactionId': transaction_id,
            'approveTotal': str(approve_total),
            'currency': 'HUF',
            'sdkVersion': self.sdk_version,
        }
        if original_total is not None:
            payload['originalTotal'] = str(original_total)
        status_code, response_data = self._post('finish', payload)
        if status_code != 200:
            raise RuntimeError(f"SimplePay finish failed: {response_data}")
        return response_data
