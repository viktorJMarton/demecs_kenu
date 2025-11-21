/**
 * Valós idejű frissítések kezelése Server-Sent Events-szel
 */
class RealTimeUpdater {
    constructor() {
        this.eventSource = null;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
        this.reconnectAttempts = 0;
    }

    init() {
        this.connect();
        this.setupVisibilityHandler();
    }

    connect() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        try {
            this.eventSource = new EventSource('/events');
            
            this.eventSource.onopen = () => {
                console.log('SSE kapcsolat létrejött');
                this.reconnectAttempts = 0;
                this.reconnectDelay = 1000;
              
            };

            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleEvent(data);
                } catch (error) {
                    console.error('SSE üzenet feldolgozási hiba:', error);
                }
            };

            this.eventSource.onerror = (error) => {
                console.error('SSE hiba:', error);
                this.eventSource.close();
                this.scheduleReconnect();
            };

        } catch (error) {
            console.error('SSE kapcsolat hiba:', error);
            this.scheduleReconnect();
        }
    }

    handleEvent(data) {
        console.log('SSE esemény érkezett:', data);

        switch (data.type) {
            case 'connected':
                console.log('SSE kapcsolat megerősítve');
                break;

            case 'tour_update':
                this.handleTourUpdate(data.data);
                break;

            case 'booking_update':
                this.handleBookingUpdate(data.data);
                break;

            case 'system_message':
                this.handleSystemMessage(data.data);
                break;

            case 'ping':
                // Keep-alive üzenet, nem kell kezelni
                break;

            default:
                console.log('Ismeretlen esemény típus:', data.type);
        }
    }

    handleTourUpdate(tourData) {
        const { tour_id, action, tour_data } = tourData;
        
        switch (action) {
            case 'created':
                this.showNotification(`Új túra hozzáadva: ${tour_data.title}`, 'info');
                this.refreshTourCalendar();
                break;

            case 'updated':
                this.showNotification(`Túra frissítve: ${tour_data.title}`, 'info');
                this.refreshTourCalendar();
                this.checkSelectedTour(tour_id, tour_data);
                break;

            case 'deleted':
                this.showNotification(`Túra törölve: ${tour_data.title}`, 'warning');
                this.refreshTourCalendar();
                this.closeModalIfTourDeleted(tour_id);
                break;
        }
    }

    handleBookingUpdate(bookingData) {
        const { booking_id, tour_id, action, booking_data } = bookingData;
        
        switch (action) {
            case 'created':
                this.showNotification('Új foglalás érkezett', 'info');
                this.updateTourCapacity(tour_id);
                break;

            case 'updated':
                this.showNotification('Foglalás frissítve', 'info');
                this.updateTourCapacity(tour_id);
                break;

            case 'cancelled':
                this.showNotification('Foglalás lemondva', 'warning');
                this.updateTourCapacity(tour_id);
                break;
        }
    }

    handleSystemMessage(messageData) {
        const { message, level } = messageData;
        this.showNotification(message, level);
    }

    // Túra kapacitás frissítése
    updateTourCapacity(tourId) {
        // Ha van nyitott modal és az adott túrára vonatkozik
        if (window.selectedTour && window.selectedTour.id == tourId) {
            // Újra lekérjük a túra adatait
            this.refreshTourDetails(tourId);
        }
    }

    // Túra részletek frissítése
    refreshTourDetails(tourId) {
        try {
            const tourDetails = (window.toursData || []).find(t => String(t.id) === String(tourId));
            if (tourDetails) this.updateReservationView(tourDetails);
        } catch (error) {
            console.error('Túra adatok frissítési hiba:', error);
        }
    }

    // Reservation view frissítése
    updateReservationView(tourDetails) {
        const currentParticipants = tourDetails.currentParticipants || tourDetails.current_participants || 0;
        const maxParticipants = tourDetails.maxParticipants || tourDetails.max_participants || 15;
        
        // Létszám info frissítése
        const participantsElement = document.querySelector('.reservation-participants');
        if (participantsElement) {
            participantsElement.textContent = `${currentParticipants}/${maxParticipants} fő`;
        }

        // Progress bar frissítése
        const progressBar = document.querySelector('.reservation-progress');
        if (progressBar) {
            const progress = maxParticipants > 0 ? (currentParticipants / maxParticipants) * 100 : 0;
            progressBar.style.width = `${progress}%`;
        }

        // Túlfoglalás figyelmeztetés
        if (currentParticipants > maxParticipants) {
            this.showNotification('Figyelem! Ez a túra túl van foglalva!', 'error');
        }
    }

    // Kiválasztott túra ellenőrzése változások után
    checkSelectedTour(tourId, tourData) {
        if (window.selectedTour && window.selectedTour.id == tourId) {
            // Frissítjük a kiválasztott túra adatait
            window.selectedTour = { ...window.selectedTour, ...tourData };
            
            // Ha a modal nyitva van, frissítjük
            const reservationView = document.getElementById('reservation-view');
            if (reservationView && !reservationView.classList.contains('hidden')) {
                this.refreshTourDetails(tourId);
            }
        }
    }

    // Modal bezárása ha túrát törölték
    closeModalIfTourDeleted(tourId) {
        if (window.selectedTour && window.selectedTour.id == tourId) {
            const modalToggle = document.getElementById('my_modal_7');
            if (modalToggle && modalToggle.checked) {
                modalToggle.checked = false;
                this.showNotification('A kiválasztott túra törölve lett', 'warning');
            }
        }
    }

    // Túra calendar frissítése
    refreshTourCalendar() {
        // Ha létezik a styleTourDates függvény (calendar modal-ban)
        if (typeof styleTourDates === 'function') {
            setTimeout(() => {
                styleTourDates();
            }, 500);
        }

        // Túra lista frissítése
        setTimeout(() => {
            location.reload(); // Egyszerű megoldás - teljes oldal frissítés
        }, 1000);
    }

    // Értesítés megjelenítése
    showNotification(message, type = 'info') {
        // DaisyUI toast létrehozása
        const toast = document.createElement('div');
        toast.className = `alert alert-${this.getAlertClass(type)} w-auto max-w-sm shadow-lg`;
        toast.style.position = 'fixed';
        toast.style.top = '1.5rem';
        toast.style.left = '50%';
        toast.style.transform = 'translateX(-50%)';
        toast.style.zIndex = '1400';
        toast.innerHTML = `
            <div class="flex items-center gap-2">
                <i class="fas ${this.getAlertIcon(type)}"></i>
                <span>${message}</span>
                <button class="btn btn-ghost btn-xs" onclick="this.parentElement.parentElement.remove()">✕</button>
            </div>
        `;

        document.body.appendChild(toast);

        // Auto-remove után 5 másodperc
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 5000);
    }

    getAlertClass(type) {
        const classes = {
            'success': 'success',
            'error': 'error',
            'warning': 'warning',
            'info': 'info'
        };
        return classes[type] || 'info';
    }

    getAlertIcon(type) {
        const icons = {
            'success': 'fa-check-circle',
            'error': 'fa-exclamation-circle',
            'warning': 'fa-exclamation-triangle',
            'info': 'fa-info-circle'
        };
        return icons[type] || 'fa-info-circle';
    }

    // Újracsatlakozás ütemezése
    scheduleReconnect() {
        if (this.reconnectAttempts < 10) {
            this.reconnectAttempts++;
            
            setTimeout(() => {
                console.log(`SSE újracsatlakozás kísérlet #${this.reconnectAttempts}`);
                this.connect();
            }, this.reconnectDelay);

            // Exponenciális backoff
            this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
        } else {
            console.error('SSE maximális újracsatlakozási kísérletek elérve');
            this.showNotification('Valós idejű frissítések nem elérhetők', 'warning');
        }
    }

    // Oldal láthatóság kezelése
    setupVisibilityHandler() {
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && this.eventSource && this.eventSource.readyState === EventSource.CLOSED) {
                // Ha az oldal újra látható és a kapcsolat megszakadt, újracsatlakozunk
                setTimeout(() => {
                    this.connect();
                }, 1000);
            }
        });
    }

    // Kapcsolat bontása
    disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
}

// Globális instance
window.realTimeUpdater = new RealTimeUpdater();

// Auto-indítás amikor a DOM betöltődött
document.addEventListener('DOMContentLoaded', function() {
    // Csak a felhasználói oldalon indítjuk el (nem admin oldalon)
    if (!window.location.pathname.startsWith('/admin')) {
        window.realTimeUpdater.init();
    }
});