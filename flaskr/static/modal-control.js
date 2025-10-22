/**
 * Modal Control and Reset Functionality
 * Handles modal opening, closing, and state management
 */

document.addEventListener('DOMContentLoaded', function() {
  const closeBtn = document.getElementById('close-modal-btn');
  const modalToggle = document.getElementById('my_modal_7');
  
  // Modal bezárása és reset calendar nézetre - globális
  window.closeAndResetModal = function() {
    // Vissza calendar nézetbe
    showCalendarView();
    
    // Túra kijelölés törlése
    document.querySelectorAll('.tour-item').forEach(function(tourItem) {
      tourItem.classList.remove('btn-primary');
      tourItem.classList.add('btn-ghost');
    });
    
    // Foglalás gomb elrejtése
    const bookingSection = document.getElementById('booking-section');
    if (bookingSection) {
      bookingSection.classList.add('hidden');
    }
    
    // Kiválasztott túra törlése
    window.selectedTour = null;
    
    // Naptár visszaállítása aktuális hónapra és styling reset
    const calendar = document.querySelector('calendar-date');
    if (calendar) {
      const today = new Date().toISOString().split('T')[0];
      navigateCalendarToDate(calendar, today);
      calendar.setAttribute('value', today);
      
      // Kijelölt túra dátum törlése
      calendar.removeAttribute('data-selected-tour-date');
      
      // Túrák styling visszaállítása
      setTimeout(() => {
        styleTourDates();
      }, 500);
    }
    
    // Modal bezárása
    const modalToggle = document.getElementById('my_modal_7');
    if (modalToggle) {
      modalToggle.checked = false;
    }
  }
  
  // Intelligens bezárás gomb eseménykezelő
  if (closeBtn) {
    closeBtn.addEventListener('click', function() {
      // Ellenőrizzük, melyik nézetben vagyunk
      const calendarView = document.getElementById('calendar-view');
      const reservationView = document.getElementById('reservation-view');
      const loadingView = document.getElementById('loading-view');
      
      if (!reservationView.classList.contains('hidden')) {
        // Ha reservation nézetben vagyunk, vissza a calendar nézetre
        showCalendarView();
      } else if (!loadingView.classList.contains('hidden')) {
        // Ha loading nézetben vagyunk, vissza a calendar nézetre
        showCalendarView();
      } else {
        // Ha calendar nézetben vagyunk, bezárjuk az egész modal-t
        closeAndResetModal();
      }
    });
  }
  
  // Modal backdrop eseménykezelő (amikor a háttérre kattintunk)
  const modalBackdrop = document.querySelector('label[for="my_modal_7"].modal-backdrop');
  if (modalBackdrop) {
    modalBackdrop.addEventListener('click', function() {
      closeAndResetModal();
    });
  }
  
  // Intelligens ESC billentyű eseménykezelő
  document.addEventListener('keydown', function(event) {
    const modalToggle = document.getElementById('my_modal_7');
    if (event.key === 'Escape' && modalToggle && modalToggle.checked) {
      // Ellenőrizzük, melyik nézetben vagyunk
      const reservationView = document.getElementById('reservation-view');
      const loadingView = document.getElementById('loading-view');
      
      if (!reservationView.classList.contains('hidden')) {
        // Ha reservation nézetben vagyunk, vissza a calendar nézetre
        showCalendarView();
      } else if (!loadingView.classList.contains('hidden')) {
        // Ha loading nézetben vagyunk, vissza a calendar nézetre
        showCalendarView();
      } else {
        // Ha calendar nézetben vagyunk, bezárjuk az egész modal-t
        closeAndResetModal();
      }
    }
  });
  
  // Modal állapot változás figyelése (amikor programozottan zárjuk be)
  const modalCheckbox = document.getElementById('my_modal_7');
  if (modalCheckbox) {
    modalCheckbox.addEventListener('change', function() {
      if (!this.checked) {
        // Ha a modal bezáródott, reset calendar nézetre
        setTimeout(function() {
          showCalendarView();
          
          // Túra kijelölés törlése
          document.querySelectorAll('.tour-item').forEach(function(tourItem) {
            tourItem.classList.remove('btn-primary');
            tourItem.classList.add('btn-ghost');
          });
          
          // Foglalás gomb elrejtése
          const bookingSection = document.getElementById('booking-section');
          if (bookingSection) {
            bookingSection.classList.add('hidden');
          }
          
          // Kiválasztott túra törlése - globális változó tisztítása
          if (window.selectedTour !== undefined) {
            window.selectedTour = null;
          }
          
          // Naptár visszaállítása aktuális hónapra
          const calendar = document.querySelector('calendar-date');
          if (calendar) {
            const today = new Date().toISOString().split('T')[0];
            navigateCalendarToDate(calendar, today);
            calendar.setAttribute('value', today);
            
            // Kijelölt túra dátum törlése
            calendar.removeAttribute('data-selected-tour-date');
          }
        }, 100); // Kis késleltetés a smooth animációért
      }
    });
  }
});