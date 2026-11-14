from flask import Blueprint, Response, json
import time
import threading
from queue import Queue

bp = Blueprint('events', __name__)

# Globális esemény queue
event_queue = Queue()

class EventBroadcaster:
    def __init__(self):
        self.clients = []
    
    def add_client(self, client_queue):
        """Új kliens hozzáadása"""
        self.clients.append(client_queue)
    
    def remove_client(self, client_queue):
        """Kliens eltávolítása"""
        if client_queue in self.clients:
            self.clients.remove(client_queue)
    
    def broadcast_event(self, event_type, data):
        """Esemény küldése minden kliensnek"""
        event_data = {
            'type': event_type,
            'data': data,
            'timestamp': time.time()
        }
        
        # Összes kliens queue-jába berakjuk az eseményt
        for client_queue in self.clients[:]:  # Másolatot készítünk iteráláshoz
            try:
                client_queue.put(event_data, timeout=1)
            except:
                # Ha a kliens nem érhető el, eltávolítjuk
                self.remove_client(client_queue)

# Globális broadcaster instance
broadcaster = EventBroadcaster()

@bp.route('/events')
def stream():
    """Server-Sent Events endpoint"""
    def event_stream():
        client_queue = Queue()
        broadcaster.add_client(client_queue)
        
        try:
            # Kezdeti kapcsolat üzenet
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Kapcsolat létrejött'})}\n\n"
            
            while True:
                try:
                    # Várunk eseményre max 30 másodpercig
                    event = client_queue.get(timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except:
                    # Timeout esetén keep-alive üzenetet küldünk
                    yield f"data: {json.dumps({'type': 'ping', 'timestamp': time.time()})}\n\n"
                    
        except GeneratorExit:
            # Kliens megszakította a kapcsolatot
            broadcaster.remove_client(client_queue)
    
    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        }
    )

def broadcast_tour_update(tour_id, action, tour_data=None):
    """Túra változás broadcast"""
    broadcaster.broadcast_event('tour_update', {
        'tour_id': tour_id,
        'action': action,  # 'created', 'updated', 'deleted'
        'tour_data': tour_data
    })

def broadcast_booking_update(booking_id, tour_id, action, booking_data=None):
    """Foglalás változás broadcast (PII-mentes)"""
    payload = {
        'booking_id': booking_id,
        'tour_id': tour_id,
        'action': action,
        'booking_data': {
            'payment_status': (booking_data or {}).get('payment_status'),
            'participants_count': (booking_data or {}).get('participants_count')
        }
    }
    broadcaster.broadcast_event('booking_update', payload)

def broadcast_system_message(message, level='info'):
    """Rendszer üzenet broadcast"""
    broadcaster.broadcast_event('system_message', {
        'message': message,
        'level': level,  # 'info', 'warning', 'error', 'success'
    })