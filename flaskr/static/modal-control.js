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
    // Ensure both click and touch explicitly close the modal fully (match backdrop behavior)
    const forceClose = function(e) {
      if (e && typeof e.preventDefault === 'function') e.preventDefault();

      // Diagnostic log for debugging on devices
      try { console.log('[modal-control] forceClose invoked', { hasEvent: !!e }); } catch (_) {}

      // Uncheck the modal toggle (label may toggle it, but ensure state)
      if (modalToggle) {
        try { console.log('[modal-control] modalToggle before:', modalToggle.checked); } catch (_) {}
        modalToggle.checked = false;
        modalToggle.dispatchEvent(new Event('change'));
        try { console.log('[modal-control] modalToggle after:', modalToggle.checked); } catch (_) {}
      }

      // Run the shared cleanup to restore calendar view and remove overlays
      try { if (typeof window.closeAndResetModal === 'function') window.closeAndResetModal(); } catch (err) { console.warn('[modal-control] closeAndResetModal error', err); }

      // Fallback: ensure the modal container is visually hidden on devices where CSS may not update immediately
      try {
        const container = document.getElementById('my_modal_7-container');
        if (container) {
          setTimeout(() => {
            try {
              const style = window.getComputedStyle(container);
              const visible = style && style.display !== 'none' && style.visibility !== 'hidden' && (parseFloat(style.opacity || '1') > 0);
              try { console.log('[modal-control] container visible after close?', visible); } catch (_) {}
              if (visible) {
                container.style.display = 'none';
                container.setAttribute('data-closed-fallback', 'true');
                try { console.log('[modal-control] applied fallback hide to modal container'); } catch (_) {}
              }
            } catch (e) { console.warn('[modal-control] fallback visibility check error', e); }
          }, 60);
        }
      } catch (err) {
        console.warn('[modal-control] fallback hide failed', err);
      }

      // Also restore page scroll if previously modified
      try { document.documentElement.style.overflow = ''; document.body.style.overflow = ''; } catch (_) {}
    };

    closeBtn.addEventListener('click', forceClose, { passive: false });
    // iOS sometimes fires touchend instead of click for fast taps; listen for it too
    closeBtn.addEventListener('touchend', forceClose, { passive: false });
  }
  
  // Modal backdrop eseménykezelő (amikor a háttérre kattintunk)
  const modalBackdrop = document.querySelector('label[for="my_modal_7"].modal-backdrop');
  if (modalBackdrop) {
    modalBackdrop.addEventListener('click', function() {
      closeAndResetModal();
    });
  }

  // Ha a modal-box felső (naptár feletti) területére kattintunk, lépjünk ki
  const calendarView = document.getElementById('calendar-view');
  const modalBox = calendarView ? calendarView.closest('.modal-box') : null;
  if (modalBox && modalToggle && calendarView) {
    modalBox.addEventListener('click', function(event) {
      if (!modalToggle.checked || calendarView.classList.contains('hidden')) {
        return;
      }

      if (event.target.closest('button, a, input, label, textarea, select')) {
        return;
      }

      const rect = calendarView.getBoundingClientRect();
      if (event.clientY < rect.top - 6) {
        event.preventDefault();
        closeAndResetModal();
      }
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
      if (this.checked) {
        // If modal opens, ensure any leftover overlay state is cleared (map-overlay hiding modal-box)
        try { if (typeof window.restoreModalFromMapOverlay === 'function') { window.restoreModalFromMapOverlay(); } } catch (_) { }

        // If we previously applied a visual fallback hide, remove it so modal can show again
        try {
          const container = document.getElementById('my_modal_7-container');
          if (container && container.getAttribute('data-closed-fallback') === 'true') {
            container.style.display = '';
            container.removeAttribute('data-closed-fallback');
            try { console.log('[modal-control] removed fallback hide on open'); } catch (_) {}
          }
        } catch (_) {}
      } else {
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