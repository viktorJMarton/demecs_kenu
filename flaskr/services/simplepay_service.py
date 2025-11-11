"""
SimplePay Payment Gateway Service
Integráció a SimplePay fizetési rendszerrel
"""

import hashlib
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class SimplePayService:
    """SimplePay API kommunikáció és hash számítás kezelése"""
    
    # SimplePay API URL-ek
    SANDBOX_BASE_URL = "https://sandbox.simplepay.hu/payment/v2"
    LIVE_BASE_URL = "https://secure.simplepay.hu/payment/v2"
    
    def __init__(self, merchant_id: str, secret_key: str, sandbox: bool = True):
        """
        SimplePay service inicializálása
        
        Args:
            merchant_id: SimplePay Merchant azonosító
            secret_key: SimplePay SECRET KEY
            sandbox: True = teszt környezet, False = éles környezet
        """
        self.merchant_id = merchant_id
        self.secret_key = secret_key
        self.sandbox = sandbox
        self.base_url = self.SANDBOX_BASE_URL if sandbox else self.LIVE_BASE_URL
        
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
    
    def calculate_signature(self, data: Dict) -> str:
        """
        SimplePay signature (hash) számítás SHA-384 algoritmussal
        
        A SimplePay dokumentáció szerint meghatározott sorrendben összefűzi
        az adatokat és hash-eli a SECRET KEY-vel együtt.
        
        Args:
            data: Fizetési adatok dictionary
            
        Returns:
            SHA-384 hash string (hexadecimális)
        """
        # Kötelező mezők a meghatározott sorrendben
        signature_base = ""
        
        # SALT (timestamp)
        signature_base += str(data.get('salt', ''))
        
        # MERCHANT
        signature_base += str(data.get('merchant', ''))
        
        # ORDER REF
        signature_base += str(data.get('orderRef', ''))
        
        # CURRENCY
        signature_base += str(data.get('currency', ''))
        
        # TOTAL (amount)
        signature_base += str(data.get('total', ''))
        
        # TIMEOUT
        if 'timeout' in data:
            signature_base += str(data['timeout'])
        
        # METHODS
        if 'methods' in data:
            methods = data['methods']
            if isinstance(methods, list):
                signature_base += ','.join(methods)
            else:
                signature_base += str(methods)
        
        # URLs
        if 'url' in data:
            urls = data['url']
            signature_base += urls.get('success', '')
            signature_base += urls.get('fail', '')
            signature_base += urls.get('cancel', '')
            signature_base += urls.get('timeout', '')
        
        # SECRET KEY hozzáadása
        signature_base += self.secret_key
        
        # SHA-384 hash számítás
        signature = hashlib.sha384(signature_base.encode('utf-8')).hexdigest()
        
        logger.debug(f"Signature base (without secret): {signature_base[:-len(self.secret_key)]}")
        logger.debug(f"Generated signature: {signature}")
        
        return signature
    
    def verify_signature(self, data: Dict, received_signature: str) -> bool:
        """
        IPN notification signature ellenőrzése
        
        Args:
            data: Beérkezett IPN adatok
            received_signature: Beérkezett signature
            
        Returns:
            True ha a signature valid, False ha nem
        """
        calculated_signature = self.calculate_signature(data)
        is_valid = calculated_signature == received_signature
        
        if not is_valid:
            logger.warning(f"Signature mismatch! Calculated: {calculated_signature}, Received: {received_signature}")
        
        return is_valid
    
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
        # Timeout: alapértelmezetten 20 perc webes vásárláshoz (IPEW)
        # PDF szerint: webes vásárlás 20 perc, fizikai 10 perc, számla 60-180 nap
        timeout_datetime = datetime.now() + timedelta(minutes=timeout_minutes)
        timeout_str = timeout_datetime.strftime('%Y-%m-%dT%H:%M:%S%z')
        if not timeout_str.endswith('+00:00'):
            timeout_str += '+01:00'  # CET timezone
        
        # Salt (timestamp)
        salt = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        
        payment_data = {
            'salt': salt,
            'merchant': self.merchant_id,
            'orderRef': order_ref,
            'currency': 'HUF',
            'total': amount,
            'timeout': timeout_str,
            'methods': ['CARD'],  # Bankkártyás fizetés
            'customer': customer_email,
            'customerPhone': customer_phone,
            'language': language,
            'invoice': {
                'name': invoice_data.get('name', customer_name),
                'country': invoice_data.get('country', 'hu'),
                'state': invoice_data.get('state', ''),
                'city': invoice_data.get('city', ''),
                'zip': invoice_data.get('zip', ''),
                'address': invoice_data.get('address', ''),
                'company': invoice_data.get('company', '')
            },
            'url': {
                'success': success_url,
                'fail': fail_url,
                'cancel': cancel_url,
                'timeout': timeout_url
            }
        }
        
        # Signature számítás
        signature = self.calculate_signature(payment_data)
        payment_data['signature'] = signature
        
        return payment_data
    
    def start_payment(self, payment_data: Dict) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Fizetés indítása SimplePay-nél (START endpoint)
        
        Args:
            payment_data: Előkészített fizetési adatok (signature-rel együtt)
            
        Returns:
            Tuple: (success: bool, payment_url: str or None, response_data: dict or None)
        """
        start_url = f"{self.base_url}/start"
        
        try:
            logger.info(f"Starting payment for order: {payment_data.get('orderRef')}")
            logger.debug(f"Payment data: {json.dumps(payment_data, indent=2, ensure_ascii=False)}")
            
            response = requests.post(
                start_url,
                json=payment_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            response_data = response.json()
            logger.info(f"SimplePay START response: {response.status_code}")
            logger.debug(f"Response data: {json.dumps(response_data, indent=2, ensure_ascii=False)}")
            
            if response.status_code == 200 and response_data.get('paymentUrl'):
                payment_url = response_data['paymentUrl']
                logger.info(f"Payment URL received: {payment_url}")
                return True, payment_url, response_data
            else:
                error_msg = response_data.get('errorCodes', ['Unknown error'])
                logger.error(f"SimplePay START failed: {error_msg}")
                return False, None, response_data
                
        except requests.RequestException as e:
            logger.error(f"SimplePay START request failed: {str(e)}")
            return False, None, {'error': str(e)}
        except Exception as e:
            logger.error(f"Unexpected error in start_payment: {str(e)}")
            return False, None, {'error': str(e)}
    
    def process_ipn(self, ipn_data: Dict) -> Tuple[bool, str, Optional[Dict]]:
        """
        IPN (Instant Payment Notification) feldolgozása
        
        Args:
            ipn_data: SimplePay IPN POST adatok
            
        Returns:
            Tuple: (success: bool, status: str, data: dict or None)
        """
        try:
            # Signature ellenőrzés
            received_signature = ipn_data.get('signature', '')
            
            # Signature nélküli adatok másolata az ellenőrzéshez
            verification_data = {k: v for k, v in ipn_data.items() if k != 'signature'}
            
            if not self.verify_signature(verification_data, received_signature):
                logger.error("IPN signature verification failed!")
                return False, 'SIGNATURE_ERROR', None
            
            # Tranzakció státusz
            status = ipn_data.get('status', '').upper()
            order_ref = ipn_data.get('orderRef', '')
            transaction_id = ipn_data.get('transactionId', '')
            
            logger.info(f"IPN received for order {order_ref}: status={status}, transaction_id={transaction_id}")
            
            return True, status, ipn_data
            
        except Exception as e:
            logger.error(f"Error processing IPN: {str(e)}")
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
        refund_url = f"{self.base_url}/refund"
        
        refund_data = {
            'salt': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'merchant': self.merchant_id,
            'orderRef': order_ref,
            'transactionId': transaction_id,
            'refundAmount': amount
        }
        
        # Signature számítás
        signature_base = (
            refund_data['salt'] +
            refund_data['merchant'] +
            refund_data['orderRef'] +
            refund_data['transactionId'] +
            str(refund_data['refundAmount']) +
            self.secret_key
        )
        refund_data['signature'] = hashlib.sha384(signature_base.encode('utf-8')).hexdigest()
        
        try:
            logger.info(f"Initiating refund for transaction {transaction_id}, order {order_ref}")
            
            response = requests.post(
                refund_url,
                json=refund_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            response_data = response.json()
            logger.info(f"SimplePay REFUND response: {response.status_code}")
            logger.debug(f"Response data: {json.dumps(response_data, indent=2, ensure_ascii=False)}")
            
            if response.status_code == 200:
                return True, response_data
            else:
                logger.error(f"SimplePay REFUND failed: {response_data}")
                return False, response_data
                
        except Exception as e:
            logger.error(f"Error initiating refund: {str(e)}")
            return False, {'error': str(e)}
