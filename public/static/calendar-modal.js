/**
 * Calendar Modal Main Functionality
 * Handles tour selection, calendar navigation, and reservation views
 */

document.addEventListener('DOMContentLoaded', function () {
  const calendar = document.querySelector('#cally-calendar');
  const toursList = document.getElementById('future-tours-list');
  const toursLoading = document.getElementById('tour-list-loading');
  const bookingSection = document.getElementById('booking-section');
  const selectedTourName = document.getElementById('selected-tour-name');
  const tourDetailsBtn = document.getElementById('tour-details-btn');
  const backBtn = document.getElementById('back-to-calendar') || document.getElementById('back-to-calendar-btn');

  // Nézet elemek
  const calendarView = document.getElementById('calendar-view');
  const loadingView = document.getElementById('loading-view');
  const reservationView = document.getElementById('reservation-view');

  window.selectedTour = null;
  window.toursData = [];

  const formatDescriptionText = (value) => {
    if (value === null || value === undefined) {
      return '';
    }

    const escaped = String(value).replace(/[&<>"']/g, (char) => {
      switch (char) {
        case '&':
          return '&amp;';
        case '<':
          return '&lt;';
        case '>':
          return '&gt;';
        case '"':
          return '&quot;';
        case "'":
          return '&#39;';
        default:
          return char;
      }
    });

    const normalized = escaped.replace(/\r\n/g, '\n');
    const paragraphs = normalized.split(/\n\s*\n/);

    return paragraphs
      .map((paragraph, index) => {
        const html = paragraph.replace(/\n/g, '<br>');
        const marginStyle = index === paragraphs.length - 1 ? 'margin:0;' : 'margin:0 0 0.75rem 0;';
        return `<p style="${marginStyle}" class="leading-relaxed">${html}</p>`;
      })
      .join('');
  };

  // Túrák betöltése az API-ból
  function loadFutureTours() {
    if (toursLoading) toursLoading.style.display = 'block';
    try {
      const script = document.getElementById('initial-tours-json');
      const tours = script ? JSON.parse(script.textContent || '[]') : [];
      window.toursData = tours;
      renderToursList(tours);
      styleTourDatesOnCalendar(tours);
      if (toursLoading) toursLoading.style.display = 'none';
    } catch (error) {
      console.error('Túrák betöltési hiba:', error);
      if (toursLoading) {
        toursLoading.textContent = 'Hiba a túrák betöltésében';
      }
    }
  }

  // Túralista renderelése
  function renderToursList(tours) {
    if (!toursList) return;

    toursList.innerHTML = '';

    tours.forEach(tour => {
      const listItem = document.createElement('li');
      listItem.innerHTML = `
        <a class="tour-item cursor-pointer hover:bg-base-200 rounded-lg p-3 transition-all" 
           data-tour-id="${tour.id}" 
           data-date="${tour.date}"
           data-price="${tour.price}"
           data-difficulty="${tour.difficulty}"
           data-location="${tour.location}">
          <div class="flex justify-between items-center">
            <div>
              <div class="font-bold">${tour.name}</div>
              <div class="text-sm text-base-content/70">${tour.date} | ${tour.location}</div>
            </div>
            <div class="text-right">
              <div class="text-sm font-semibold text-primary">${tour.price} Ft</div>
              <div class="text-xs text-base-content/60">${tour.difficulty}</div>
            </div>
          </div>
        </a>
      `;

      // Kattintás esemény hozzáadása
      const tourItem = listItem.querySelector('.tour-item');
      tourItem.addEventListener('click', function () {
        selectTourFromList(tour);
      });

      toursList.appendChild(listItem);
    });
  }

  // Túra kiválasztása a listából
  function selectTourFromList(tour) {
    // Előző kijelölés eltávolítása
    document.querySelectorAll('.tour-item').forEach(item => {
      item.classList.remove('bg-primary', 'text-primary-content');
    });

    // Aktuális túra kijelölése
    const currentItem = document.querySelector(`[data-tour-id="${tour.id}"]`);
    if (currentItem) {
      currentItem.classList.add('bg-primary', 'text-primary-content');
    }

    // Naptár dátumának beállítása
    if (calendar) {
      calendar.setAttribute('value', tour.date);
    }

    // Túra adatok tárolása
    window.selectedTour = tour;

    // console.log('Túra kiválasztva:', tour);
  }

  // Initiális naptár beállítás - aktuális hónap mutatása
  function initializeCalendarMonth() {
    if (calendar) {
      // Aktuális dátum beállítása
      const today = new Date().toISOString().split('T')[0];
      calendar.setAttribute('value', today);
    }

    // Túrák betöltése
    loadFutureTours();
  }

  // Túrák napjainak styling a Cally calendar-on
  function styleTourDatesOnCalendar(tours) {
    if (!tours || !calendar) return;

    // Dinamikus CSS generálása túra napokhoz
    generateCallyTourDateStyles(tours);

    // Cally calendar eseménykezelő hozzáadása
    setTimeout(() => {
      addCalendarClickListeners(tours);
    }, 500);
  }

  function styleTourDates() {
    if (!calendar || !Array.isArray(window.toursData) || window.toursData.length === 0) {
      return;
    }

    styleTourDatesOnCalendar(window.toursData);
  }

  // Cally calendar kattintás eseménykezelők
  function addCalendarClickListeners(tours) {
    const calendarMonth = calendar ? calendar.querySelector('calendar-month') : null;
    if (!calendarMonth) return;

    const toursByDate = {};
    tours.forEach(tour => {
      toursByDate[tour.date] = tour;
    });

    calendar.__toursByDate = toursByDate;

    if (!calendar.__tourDateChangeHandler) {
      const handler = function (event) {
        const selectedDate = event.target.value;
        const mapping = calendar.__toursByDate || {};
        const tour = mapping[selectedDate];

        if (tour) {
          selectTourFromList(tour);
        }
      };

      calendar.__tourDateChangeHandler = handler;
      calendar.addEventListener('change', handler);
    }
  }

  // Dinamikus CSS generálása Cally calendar túra napokhoz
  function generateCallyTourDateStyles(tours) {
    // Eltávolítjuk a korábbi dinamikus style-t ha létezik
    const existingStyle = document.getElementById('dynamic-cally-tour-styles');
    if (existingStyle) {
      existingStyle.remove();
    }

    // Új style element létrehozása
    const styleElement = document.createElement('style');
    styleElement.id = 'dynamic-cally-tour-styles';

    let cssRules = '';

    // Túra napok styling - kék háttér Cally calendar-hoz
    tours.forEach(function (tour) {
      cssRules += `
        calendar-month::part(button)[value="${tour.date}"] {
          background-color: #3b82f6 !important;
          color: white !important;
          font-weight: bold !important;
          border-radius: 6px !important;
          cursor: pointer !important;
        }
        
        calendar-month::part(button)[value="${tour.date}"]:hover {
          background-color: #2563eb !important;
          transform: scale(1.05);
        }
        
        calendar-date[data-selected-tour="${tour.date}"] calendar-month::part(button)[value="${tour.date}"] {
          background-color: #ef4444 !important;
          color: white !important;
        }
      `;
    });

    styleElement.textContent = cssRules;
    document.head.appendChild(styleElement);
  }

  // Naptár kijelölés frissítése
  function updateCalendarSelection(selectedDate) {
    // Kijelölt dátum tárolása a naptár attribútumként
    if (calendar) {
      calendar.setAttribute('data-selected-tour', selectedDate);
    }
  }

  // Nézet váltó függvények - globálisak
  window.showCalendarView = function () {
    calendarView.classList.remove('hidden');
    loadingView.classList.add('hidden');
    reservationView.classList.add('hidden');
    document.getElementById('reservation-footer').classList.add('hidden');
    backBtn.classList.add('hidden');

    // "Összes túra megjelenítése" gomb elrejtése visszalépéskor
    const showAllToursBtn = document.getElementById('show-all-tours-btn-container');
    if (showAllToursBtn) {
      showAllToursBtn.classList.add('hidden');
    }
  }

  window.showLoadingView = function () {
    calendarView.classList.add('hidden');
    loadingView.classList.remove('hidden');
    reservationView.classList.add('hidden');
    document.getElementById('reservation-footer').classList.add('hidden');
    backBtn.classList.remove('hidden');
  }

  window.showReservationView = function () {
    calendarView.classList.add('hidden');
    loadingView.classList.add('hidden');
    reservationView.classList.remove('hidden');
    document.getElementById('reservation-footer').classList.remove('hidden');
    backBtn.classList.remove('hidden');
  }

  // Túra kiválasztás logika
  document.querySelectorAll('.tour-item').forEach(function (item) {
    item.addEventListener('click', function () {
      // Eltávolítjuk a korábbi kijelölést
      document.querySelectorAll('.tour-item').forEach(function (tourItem) {
        tourItem.classList.remove('btn-primary');
        tourItem.classList.add('btn-ghost');
      });

      // Kijelöljük az aktuális túrát
      this.classList.remove('btn-ghost');
      this.classList.add('btn-primary');

      // Beállítjuk a naptárat és navigálunk a megfelelő hónapra
      const date = this.getAttribute('data-date');
      if (calendar) {
        // Navigálunk a túra hónapjához
        navigateCalendarToDate(calendar, date);
        calendar.setAttribute('value', date);

        // Naptár kijelölés frissítése
        setTimeout(() => {
          updateCalendarSelection(date);
        }, 800); // Várunk amíg a navigáció befejeződik
      }

      // Tároljuk a kiválasztott túrát az új adatokkal
      window.selectedTour = {
        id: this.getAttribute('data-tour-id'),
        name: this.querySelector('.font-bold').textContent.trim(),
        date: date,
        price: this.getAttribute('data-price'),
        difficulty: this.getAttribute('data-difficulty'),
        location: this.getAttribute('data-location')
      };

      selectedTourName.textContent = window.selectedTour.name;
      bookingSection.classList.remove('hidden');
    });
  });

  // Naptár inicializálása
  initializeCalendarMonth();

  // Naptár változások figyelése
  const observer = new MutationObserver(function (mutations) {
    mutations.forEach(function (mutation) {
      if (mutation.type === 'childList' || mutation.type === 'subtree') {
        // Kis késleltetéssel újra alkalmazzuk a styling-ot
        setTimeout(() => {
          styleTourDates();
        }, 200);
      }
    });
  });

  // Observer indítása a naptáron
  if (calendar) {
    observer.observe(calendar, {
      childList: true,
      subtree: true,
      attributes: false
    });
  }

  // Túra részletei gomb eseménykezelő
  if (tourDetailsBtn) {
    tourDetailsBtn.addEventListener('click', function () {
      if (window.selectedTour) {
        // Loading nézet mutatása
        showLoadingView();

        // Szimulált API hívás (később ez lesz a valódi DB lekérés)
        setTimeout(function () {
          loadTourDetails(window.selectedTour);
        }, 1500); // 1.5s loading szimulálás
      }
    });
  }

  // Vissza gomb
  if (backBtn) {
    backBtn.addEventListener('click', function () {
      showCalendarView();
    });
  }

  // Reservation footer gombok
  const cancelReservationBtn = document.getElementById('cancel-reservation-btn');
  const confirmReservationBtn = document.getElementById('confirm-reservation-btn');

  if (cancelReservationBtn) {
    cancelReservationBtn.addEventListener('click', function () {
      showCalendarView();
    });
  }

  if (confirmReservationBtn) {
    confirmReservationBtn.addEventListener('click', function () {
      if (window.selectedTour && window.currentTourDetails) {
        confirmReservation(window.currentTourDetails.id, window.currentTourDetails.name);
      }
    });
  }

  // Delegált handler: galéria képek megnyitása modalban (a tartalom dinamikusan kerül be)
  // While overlay is open, hide the DaisyUI modal content behind it to avoid visual bleed-through
  let __hiddenModalBox = null;
  document.addEventListener('click', function (e) {
    const trigger = e.target.closest('.open-image');
    if (trigger) {
      const src = trigger.getAttribute('data-src');
      const alt = trigger.getAttribute('data-alt') || 'Kép';
      // Overlay alapú megoldás — kompatibilis a meglévő modallal
      const overlay = document.getElementById('image-overlay');
      const overlayImg = document.getElementById('image-overlay-img');
      if (overlay && overlayImg && src) {
        // Ensure overlay is appended to <body> so it escapes modal stacking/overflow
        if (overlay.parentElement !== document.body) {
          try { document.body.appendChild(overlay); } catch (err) { }
        }

        // Find and hide the nearest modal content behind the overlay
        const modal = trigger.closest('.modal');
        __hiddenModalBox = modal ? modal.querySelector('.modal-box') : null;
        if (__hiddenModalBox) {
          __hiddenModalBox.classList.add('hidden');
          __hiddenModalBox.setAttribute('aria-hidden', 'true');
          try { __hiddenModalBox.inert = true; } catch (_) { }
        }

        overlayImg.src = src;
        overlayImg.alt = alt;
        overlay.classList.remove('hidden');
        overlay.classList.add('flex');
        e.preventDefault();
        return;
      }

      // Visszaesésként próbáljuk a <dialog>-ot, ha létezik és nincs másik modal nyitva
      const modal = document.getElementById('image-modal');
      const modalImg = document.getElementById('image-modal-img');
      if (modal && modalImg && src && typeof modal.showModal === 'function') {
        try {
          modalImg.src = src;
          modalImg.alt = alt;
          modal.showModal();
          e.preventDefault();
          return;
        } catch (err) {
          // Ha nem nyitható (már van nyitott modal), marad az overlay megoldás
          if (overlay && overlayImg) {
            overlayImg.src = src;
            overlayImg.alt = alt;
            overlay.classList.remove('hidden');
            overlay.classList.add('flex');
            e.preventDefault();
          }
        }
      }
    }

    // Overlay zárás: háttérre kattintás vagy X gomb
    const overlay = document.getElementById('image-overlay');
    if (overlay && !overlay.classList.contains('hidden')) {
      if (e.target === overlay || e.target.closest('[data-close-image-overlay]')) {
        overlay.classList.add('hidden');
        overlay.classList.remove('flex');
        // Restore modal content if we hid it
        if (__hiddenModalBox) {
          __hiddenModalBox.classList.remove('hidden');
          __hiddenModalBox.removeAttribute('aria-hidden');
          try { __hiddenModalBox.inert = false; } catch (_) { }
          __hiddenModalBox = null;
        }
      }
    }
  });

  // ESC gomb zárja az overlayt
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      const overlay = document.getElementById('image-overlay');
      if (overlay && !overlay.classList.contains('hidden')) {
        overlay.classList.add('hidden');
        overlay.classList.remove('flex');
        // Restore modal content if we hid it
        if (__hiddenModalBox) {
          __hiddenModalBox.classList.remove('hidden');
          __hiddenModalBox.removeAttribute('aria-hidden');
          try { __hiddenModalBox.inert = false; } catch (_) { }
          __hiddenModalBox = null;
        }
      }
    }
  });

  // Naptár navigálása a megadott dátumhoz
  function navigateCalendarToDate(calendar, targetDate) {
    const target = new Date(targetDate);
    const targetYear = target.getFullYear();
    const targetMonth = target.getMonth(); // 0-based (január = 0)

    // Aktuális naptár dátum lekérése
    const currentValue = calendar.getAttribute('value') || new Date().toISOString().split('T')[0];
    const current = new Date(currentValue);
    const currentYear = current.getFullYear();
    const currentMonth = current.getMonth();

    // Kiszámítjuk hány hónapot kell navigálni
    const monthDiff = (targetYear - currentYear) * 12 + (targetMonth - currentMonth);

    if (monthDiff !== 0) {
      // Megkeressük a next/previous gombokat
      const nextSvg = calendar.querySelector('svg[aria-label="Next"]');
      const prevSvg = calendar.querySelector('svg[aria-label="Previous"]');
      const nextBtn = nextSvg ? nextSvg.closest('button') : null;
      const prevBtn = prevSvg ? prevSvg.closest('button') : null;

      if (monthDiff > 0 && nextBtn) {
        // Előre navigálás
        for (let i = 0; i < monthDiff; i++) {
          setTimeout(() => {
            nextBtn.click();
            // Styling frissítése minden navigáció után
            if (i === monthDiff - 1) {
              setTimeout(() => {
                styleTourDates();
              }, 300);
            }
          }, i * 100); // Kis késleltetés a smooth navigációért
        }
      } else if (monthDiff < 0 && prevBtn) {
        // Hátra navigálás
        for (let i = 0; i < Math.abs(monthDiff); i++) {
          setTimeout(() => {
            prevBtn.click();
            // Styling frissítése minden navigáció után
            if (i === Math.abs(monthDiff) - 1) {
              setTimeout(() => {
                styleTourDates();
              }, 300);
            }
          }, i * 100); // Kis késleltetés a smooth navigációért
        }
      }
    } else {
      // Ha ugyanabban a hónapban vagyunk, csak a styling frissítése
      setTimeout(() => {
        styleTourDates();
      }, 100);
    }
  }

  // Túra részletek betöltése és nézet renderelése
  function loadTourDetails(tour) {
    // Lookup the tour details from the preloaded toursData (server-rendered)
    // If more details are needed, extend server templates to include them or fetch via protected endpoints.
    const tourDetails = window.toursData.find(t => String(t.id) === String(tour.id)) || {
      id: tour.id,
      name: tour.name,
      datetime: tour.date + ' (időpont megadva)',
      distance: 'Megadva',
      location: tour.location || 'Helyszín megadva',
      currentParticipants: 0,
      maxParticipants: 15,
      price: tour.price + ' Ft',
      difficulty: tour.difficulty || 'Kezdő',
      description: `Gyönyörű túra: ${tour.name}. További részletek hamarosan!`,
      meeting_point: 'Megadva a túra előtt',
      equipment_included: 'Alapfelszerelés biztosítva',
      what_to_bring: 'Kényelmes ruházat, ivóvíz és napvédelem'
    };
    renderReservationView(tourDetails);
    showReservationView();
  }

  // Reservation nézet renderelése
  function renderReservationView(tourDetails) {
    // Túra részletek mentése globálisan a gombok számára
    window.currentTourDetails = tourDetails;

    // Alapértelmezett értékek beállítása ha hiányoznak
    const currentParticipants = tourDetails.currentParticipants || tourDetails.current_participants || 0;
    const maxParticipants = tourDetails.maxParticipants || tourDetails.max_participants || 15;
    const progress = maxParticipants > 0 ? (currentParticipants / maxParticipants) * 100 : 0;

    // Use server-rendered template included in the page (hidden #templates)
    const templatesContainer = document.getElementById('templates');
    if (templatesContainer) {
      const templateHtml = templatesContainer.innerHTML;
      reservationView.innerHTML = templateHtml;
      populateTourDetails(tourDetails, currentParticipants, maxParticipants, progress);
    } else {
      // Fallback to inline HTML
      reservationView.innerHTML = createFallbackReservationHTML(tourDetails, currentParticipants, maxParticipants, progress);
      populateFallbackTourDetails(tourDetails, currentParticipants, maxParticipants, progress);
    }
  }

  // Populate tour details into the loaded template
  function populateTourDetails(tourDetails, currentParticipants, maxParticipants, progress) {
    // Basic tour information
    document.getElementById('tour-name-display').textContent = tourDetails.name;
    document.getElementById('tour-datetime-display').textContent = tourDetails.datetime;
    document.getElementById('tour-distance-display').textContent = tourDetails.distance;
    document.getElementById('tour-difficulty-display').textContent = tourDetails.difficulty;
    document.getElementById('tour-price-display').textContent = tourDetails.price;
    document.getElementById('tour-participants-display').textContent = `${currentParticipants}/${maxParticipants} fő`;
    document.getElementById('tour-progress-bar').style.width = `${progress}%`;

    // Location with coordinates
    const locationElement = document.getElementById('tour-location-display');
    const locationText = tourDetails.location || 'Nem megadott';
    if (locationElement) {
      locationElement.textContent = locationText;
    }

    const resolvedLat = tourDetails.latitude ?? tourDetails.tour_latitude ?? tourDetails.lat ?? null;
    const resolvedLng = tourDetails.longitude ?? tourDetails.tour_longitude ?? tourDetails.lng ?? null;
    const locationTrigger = document.querySelector('[data-reservation-location-trigger]') || document.getElementById('tour-location-trigger');
    if (locationTrigger) {
      if (resolvedLat !== null && resolvedLat !== undefined && resolvedLat !== '') {
        locationTrigger.dataset.mapLat = resolvedLat;
      } else {
        delete locationTrigger.dataset.mapLat;
      }

      if (resolvedLng !== null && resolvedLng !== undefined && resolvedLng !== '') {
        locationTrigger.dataset.mapLng = resolvedLng;
      } else {
        delete locationTrigger.dataset.mapLng;
      }

      locationTrigger.dataset.mapLocation = locationText;
      locationTrigger.dataset.mapTitle = tourDetails.name || tourDetails.title || 'Túra helyszín';
    }

    const descriptionEl = document.getElementById('tour-description-display');
    if (descriptionEl) {
      descriptionEl.innerHTML = formatDescriptionText(tourDetails.description || '');
    }

    // Update map with tour coordinates
    if (typeof window.updateTourMapData === 'function') {
      window.updateTourMapData({
        location: locationText,
        latitude: resolvedLat,
        longitude: resolvedLng,
        title: tourDetails.name || tourDetails.title
      });
    }

    // Optional fields with conditional display
    const meetingPointDisplay = document.getElementById('tour-meeting-point-display');
    const meetingPointText = document.getElementById('meeting-point-text');
    if (tourDetails.meeting_point && tourDetails.meeting_point.trim()) {
      meetingPointText.textContent = tourDetails.meeting_point;
      meetingPointDisplay.classList.remove('hidden');
    } else {
      meetingPointDisplay.classList.add('hidden');
    }

    const equipmentDisplay = document.getElementById('tour-equipment-display');
    const equipmentText = document.getElementById('equipment-text');
    if (tourDetails.equipment_included && tourDetails.equipment_included.trim()) {
      equipmentText.textContent = tourDetails.equipment_included;
      equipmentDisplay.classList.remove('hidden');
    } else {
      equipmentDisplay.classList.add('hidden');
    }

    const bringDisplay = document.getElementById('tour-what-to-bring-display');
    const bringText = document.getElementById('what-to-bring-text');
    if (bringDisplay && bringText) {
      const bringValue = tourDetails.what_to_bring || tourDetails.whatToBring || '';
      if (bringValue && bringValue.trim()) {
        bringText.textContent = bringValue;
        bringDisplay.classList.remove('hidden');
      } else {
        bringDisplay.classList.add('hidden');
      }
    }

  }

  // Populate tour details for fallback HTML
  function populateFallbackTourDetails(tourDetails, currentParticipants, maxParticipants, progress) {
    // For fallback, the data is already injected in the HTML string
    // This function is a placeholder for consistency
  }

  // Fallback HTML creation function
  function createFallbackReservationHTML(tourDetails, currentParticipants, maxParticipants, progress) {
    const fallbackLat = tourDetails.latitude ?? tourDetails.tour_latitude ?? '';
    const fallbackLng = tourDetails.longitude ?? tourDetails.tour_longitude ?? '';
    const locationText = tourDetails.location || 'Nem megadott';
    const mapTitle = tourDetails.name || tourDetails.title || 'Túra helyszín';
    const descriptionHtml = formatDescriptionText(tourDetails.description || '');
    return `
      <div class="flex flex-col lg:flex-row gap-8">
        <div class="flex-1 lg:max-w-md">
          <h2 class="text-2xl font-bold mb-4 text-base-content">Túra részletei</h2>
          <div class="space-y-3">
            <div class="bg-base-100/20 rounded-lg p-3 backdrop-blur-sm">
              <span class="font-semibold text-base-content/80">Túra neve:</span>
              <p class="text-lg font-bold text-base-content">${tourDetails.name}</p>
            <div class="bg-base-100/20 rounded-lg p-3 backdrop-blur-sm">
              <span class="font-semibold text-base-content/80">Dátum és időpont:</span>
              <p class="text-lg font-bold text-base-content">${tourDetails.datetime}</p>
            </div>
            <div class="bg-base-100/20 rounded-lg p-3 backdrop-blur-sm">
              <span class="font-semibold text-base-content/80">Távolság:</span>
              <p class="text-lg font-bold text-base-content">${tourDetails.distance} km</p>
            </div>
            <div class="bg-base-100/20 rounded-lg p-3 backdrop-blur-sm">
              <span class="font-semibold text-base-content/80">Nehézség:</span>
              <p class="text-lg font-bold text-base-content">${tourDetails.difficulty}</p>
            </div>
            <div class="bg-base-100/20 rounded-lg p-3 backdrop-blur-sm">
              <span class="font-semibold text-base-content/80">Ár:</span>
              <p class="text-lg font-bold text-primary">${tourDetails.price}</p>
            </div>
            <div class="bg-base-100/20 rounded-lg p-3 backdrop-blur-sm">
              <span class="font-semibold text-base-content/80">Jelenlegi létszám:</span>
              <p class="text-lg font-bold text-base-content">${currentParticipants}/${maxParticipants} fő</p>
              <div class="w-full bg-base-200 rounded-full h-2 mt-2">
                <div class="bg-primary h-2 rounded-full transition-all duration-300" style="width: ${progress}%"></div>
              </div>
            </div>
          </div>
        </div>
        <div class="flex-1 lg:max-w-lg">
          <h2 class="text-2xl font-bold mb-4 text-base-content">Helyszín</h2>
          <div class="bg-base-100/20 rounded-lg p-3 backdrop-blur-sm mb-4">
            <span class="font-semibold text-base-content/80">Túra helyszíne:</span>
              <p
                id="tour-location-trigger"
                class="text-lg font-bold text-base-content flex flex-wrap items-center gap-3 mt-2 cursor-pointer select-none"
                data-map-overlay-trigger
                data-reservation-location-trigger
                data-map-lat="${fallbackLat ?? ''}"
                data-map-lng="${fallbackLng ?? ''}"
                data-map-location="${locationText}"
                data-map-title="${mapTitle}"
                role="button"
                tabindex="0"
                aria-label="Túra helyszíne a térképen"
                title="Térkép nagyban"
              >
                <span class="inline-flex items-center gap-2 text-sm font-semibold text-primary/80">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" class="w-8 h-8 text-primary" fill="currentColor" aria-hidden="true">
                    <path d="M12 2c-3.314 0-6 2.686-6 6 0 4.743 5.385 11.021 5.614 11.287a.5.5 0 00.772 0C12.615 19.021 18 12.743 18 8c0-3.314-2.686-6-6-6zm0 9.5a2.5 2.5 0 110-5 2.5 2.5 0 010 5z"/>
                  </svg>
                  <span>Kattints a térkép megnyitásához</span>
                </span>
                <span id="tour-location-display" class="ml-auto text-right text-base-content/90">${locationText}</span>
            </p>
          </div>
          <div class="bg-base-100/20 rounded-lg p-3 backdrop-blur-sm mb-4">
            <span class="font-semibold text-base-content/80 block text-right">Leírás:</span>
            <div class="mt-2 md:max-h-[50vh] md:overflow-y-auto pr-2" aria-live="polite" style="overflow-x: hidden; text-align: left;">
              <div class="text-base-content text-left leading-relaxed">${descriptionHtml}</div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  // Globális foglalás függvény
  window.confirmReservation = function (tourId, tourName) {
    // Itt lesz majd a valódi foglalás API hívás
    // Például: POST /api/bookings
    const bookingData = {
      tour_id: tourId,
      customer_email: 'demo@example.com', // Ez majd egy formból jön
      participants_count: 1
    };

    // console.log('Foglalási kérés:', bookingData);

    // Jelenleg csak szimulálás
    alert('Foglalás megerősítve!\nTúra: ' + tourName + '\nID: ' + tourId);

    // Sikeres foglalás után modal bezárása és reset
    const modalToggle = document.getElementById('my_modal_7');
    if (modalToggle) {
      modalToggle.checked = false; // Ez triggereli a reset logikát
    }
  };
});