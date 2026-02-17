/**
 * Modal Control and Reset Functionality
 * Handles modal opening, closing, and state management
 */

document.addEventListener('DOMContentLoaded', function () {
  const closeBtn = document.getElementById('close-modal-btn');
  const modalToggle = document.getElementById('my_modal_7');

  // Modal bezárása és reset calendar nézetre - globális
  window.closeAndResetModal = function () {
    // Vissza calendar nézetbe
    showCalendarView();

    // Túra kijelölés törlése
    document.querySelectorAll('.tour-item').forEach(function (tourItem) {
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
      if (typeof navigateCalendarToDate === 'function') {
        navigateCalendarToDate(calendar, today);
      }
      calendar.setAttribute('value', today);
      calendar.removeAttribute('data-selected-tour-date');

      setTimeout(() => {
        if (typeof styleTourDates === 'function') {
          styleTourDates();
        }
      }, 500);
    }

    // Modal bezárása
    const modalToggle = document.getElementById('my_modal_7');
    if (modalToggle) {
      modalToggle.checked = false;
    }

    // Clear inline styles set by ensureModalOpen / forceModalVisible
    if (typeof window.forceModalHidden === 'function') {
      window.forceModalHidden();
    }

    // Restore body scroll
    document.body.style.overflow = '';
    document.documentElement.style.overflow = '';
  }

  // Intelligens bezárás gomb eseménykezelő
  if (closeBtn) {
    const forceClose = function (e) {
      if (e && typeof e.preventDefault === 'function') e.preventDefault();

      if (modalToggle) {
        modalToggle.checked = false;
        modalToggle.dispatchEvent(new Event('change'));
      }

      try { if (typeof window.closeAndResetModal === 'function') window.closeAndResetModal(); } catch (err) { }

      // Clear inline styles set by ensureModalOpen
      if (typeof window.forceModalHidden === 'function') {
        window.forceModalHidden();
      }

      // Restore page scroll
      document.body.style.overflow = '';
      document.documentElement.style.overflow = '';
    };

    closeBtn.addEventListener('click', forceClose, { passive: false });
    closeBtn.addEventListener('touchend', forceClose, { passive: false });
  }

  // Modal backdrop eseménykezelő
  const modalBackdrop = document.querySelector('label[for="my_modal_7"].modal-backdrop');
  if (modalBackdrop) {
    modalBackdrop.addEventListener('click', function () {
      closeAndResetModal();
    });
  }

  // Click above calendar view closes modal
  const calendarView = document.getElementById('calendar-view');
  const modalBox = calendarView ? calendarView.closest('.modal-box') : null;
  if (modalBox && modalToggle && calendarView) {
    modalBox.addEventListener('click', function (event) {
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

  // ESC key handler
  document.addEventListener('keydown', function (event) {
    const modalToggle = document.getElementById('my_modal_7');
    if (event.key === 'Escape' && modalToggle && modalToggle.checked) {
      const reservationView = document.getElementById('reservation-view');
      const loadingView = document.getElementById('loading-view');

      if (!reservationView.classList.contains('hidden')) {
        showCalendarView();
      } else if (!loadingView.classList.contains('hidden')) {
        showCalendarView();
      } else {
        closeAndResetModal();
      }
    }
  });

  // Modal checkbox change listener
  const modalCheckbox = document.getElementById('my_modal_7');
  if (modalCheckbox) {
    modalCheckbox.addEventListener('change', function () {
      if (this.checked) {
        // Restore from any overlay state
        try { if (typeof window.restoreModalFromMapOverlay === 'function') { window.restoreModalFromMapOverlay(); } } catch (_) { }
      } else {
        // Modal closed — reset state
        setTimeout(function () {
          showCalendarView();

          document.querySelectorAll('.tour-item').forEach(function (tourItem) {
            tourItem.classList.remove('btn-primary');
            tourItem.classList.add('btn-ghost');
          });

          const bookingSection = document.getElementById('booking-section');
          if (bookingSection) {
            bookingSection.classList.add('hidden');
          }

          if (window.selectedTour !== undefined) {
            window.selectedTour = null;
          }

          const calendar = document.querySelector('calendar-date');
          if (calendar) {
            const today = new Date().toISOString().split('T')[0];
            if (typeof navigateCalendarToDate === 'function') {
              navigateCalendarToDate(calendar, today);
            }
            calendar.setAttribute('value', today);
            calendar.removeAttribute('data-selected-tour-date');
          }

          // Clear inline styles from ensureModalOpen
          if (typeof window.forceModalHidden === 'function') {
            window.forceModalHidden();
          }

          document.body.style.overflow = '';
          document.documentElement.style.overflow = '';
        }, 100);
      }
    });
  }
});