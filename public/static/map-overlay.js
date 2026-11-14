(function() {
  const overlay = document.getElementById('tour-map-overlay');
  const mapCanvas = document.getElementById('tour-map-canvas');

  if (!overlay || !mapCanvas) {
    return;
  }

  const DEFAULT_COORDS = { lat: 47.4979, lng: 19.0402 };
  const TILE_LAYER_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  const TILE_ATTRIBUTION = '&copy; OpenStreetMap hozzájárulók';
  const geocodeCache = new Map();

  let overlayRelatedModalBox = null;
  let leafletMap = null;
  let leafletMarker = null;
  let pendingData = { ...DEFAULT_COORDS, location: '', title: 'Túra helyszín' };

  function parseCoordinate(value) {
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function normalizeData(data = {}) {
    return {
      lat: parseCoordinate(data.latitude ?? data.lat ?? data.tour_latitude),
      lng: parseCoordinate(data.longitude ?? data.lng ?? data.tour_longitude),
      location: data.location || data.address || data.mapLocation || '',
      title: data.title || data.name || data.mapTitle || 'Túra helyszín'
    };
  }

  function mergePendingData(update = {}) {
    const normalized = normalizeData(update);
    pendingData = {
      lat: normalized.lat ?? pendingData.lat ?? DEFAULT_COORDS.lat,
      lng: normalized.lng ?? pendingData.lng ?? DEFAULT_COORDS.lng,
      location: normalized.location || pendingData.location,
      title: normalized.title || pendingData.title || 'Túra helyszín'
    };
    return pendingData;
  }

  function ensureLeafletAssets() {
    return new Promise((resolve, reject) => {
      if (window.L) {
        resolve();
        return;
      }

      const existingScript = document.querySelector('script[data-leaflet-loader]');
      if (existingScript) {
        existingScript.addEventListener('load', () => resolve(), { once: true });
        existingScript.addEventListener('error', reject, { once: true });
        return;
      }

      if (!document.querySelector('link[href*="leaflet.css"]')) {
        const css = document.createElement('link');
        css.rel = 'stylesheet';
        css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
        document.head.appendChild(css);
      }

      const script = document.createElement('script');
      script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      script.dataset.leafletLoader = 'true';
      script.onload = () => resolve();
      script.onerror = reject;
      document.body.appendChild(script);
    });
  }

  async function ensureMapReady() {
    await ensureLeafletAssets();
    if (leafletMap) {
      return leafletMap;
    }

    leafletMap = L.map(mapCanvas).setView([pendingData.lat, pendingData.lng], 11);
    L.tileLayer(TILE_LAYER_URL, {
      maxZoom: 19,
      attribution: TILE_ATTRIBUTION
    }).addTo(leafletMap);

    return leafletMap;
  }

  async function geocodeLocation(location) {
    if (!location) return null;

    const cacheKey = location.trim().toLowerCase();
    if (geocodeCache.has(cacheKey)) {
      return geocodeCache.get(cacheKey);
    }

    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(location)}`;
      const response = await fetch(url, {
        headers: {
          'Accept': 'application/json'
        }
      });
      if (!response.ok) return null;
      const results = await response.json();
      if (Array.isArray(results) && results.length) {
        const coords = {
          lat: parseCoordinate(results[0].lat),
          lng: parseCoordinate(results[0].lon)
        };
        if (coords.lat !== null && coords.lng !== null) {
          geocodeCache.set(cacheKey, coords);
          return coords;
        }
      }
    } catch (error) {
      console.error('Geocoding hiba:', error);
    }
    return null;
  }

  async function resolveCoordinates(data) {
    const lat = parseCoordinate(data.lat);
    const lng = parseCoordinate(data.lng);
    if (lat !== null && lng !== null) {
      return { lat, lng };
    }

    if (data.location) {
      const coords = await geocodeLocation(data.location);
      if (coords) {
        return coords;
      }
    }

    return { ...DEFAULT_COORDS };
  }

  function toggleOverlayVisibility(show) {
    if (show) {
      overlay.dataset.state = 'opening';
      overlay.classList.remove('hidden');
      overlay.classList.add('flex');
      overlay.removeAttribute('aria-hidden');
      requestAnimationFrame(() => {
        overlay.dataset.state = 'open';
      });
    } else {
      overlay.dataset.state = 'closed';
      overlay.classList.add('hidden');
      overlay.classList.remove('flex');
      overlay.setAttribute('aria-hidden', 'true');
    }
  }

  function restoreModalContext() {
    if (!overlayRelatedModalBox) return;
    overlayRelatedModalBox.classList.remove('invisible', 'pointer-events-none');
    overlayRelatedModalBox.removeAttribute('aria-hidden');
    try {
      overlayRelatedModalBox.inert = false;
    } catch (error) {
      /* no-op */
    }
    overlayRelatedModalBox = null;
  }

  async function updateMapView(data) {
    const coords = await resolveCoordinates(data);
    const mapInstance = await ensureMapReady();

    mapInstance.setView([coords.lat, coords.lng], 12);

    if (leafletMarker) {
      leafletMarker.remove();
    }

    leafletMarker = L.marker([coords.lat, coords.lng]).addTo(mapInstance)
      .bindPopup(data.title || data.location || 'Túra helyszín');

    setTimeout(() => {
      mapInstance.invalidateSize();
    }, 200);
  }

  async function openOverlay(data) {
    const merged = mergePendingData(data);
    await ensureMapReady();
    toggleOverlayVisibility(true);
    await updateMapView(merged);
  }

  function closeOverlay() {
    toggleOverlayVisibility(false);
    restoreModalContext();
  }

  function extractTriggerData(trigger) {
    return {
      lat: trigger.dataset.mapLat || trigger.getAttribute('data-map-lat'),
      lng: trigger.dataset.mapLng || trigger.getAttribute('data-map-lng'),
      location: trigger.dataset.mapLocation || trigger.getAttribute('data-map-location') || trigger.textContent?.trim(),
      title: trigger.dataset.mapTitle || trigger.getAttribute('data-map-title') || trigger.getAttribute('aria-label') || 'Túra helyszín'
    };
  }

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-map-overlay-trigger]');
    if (!trigger) return;

    event.preventDefault();

    overlayRelatedModalBox = null;
    const modal = trigger.closest('.modal');
    if (modal) {
      overlayRelatedModalBox = modal.querySelector('.modal-box');
      if (overlayRelatedModalBox) {
        overlayRelatedModalBox.classList.add('invisible', 'pointer-events-none');
        overlayRelatedModalBox.setAttribute('aria-hidden', 'true');
        try {
          overlayRelatedModalBox.inert = true;
        } catch (error) {
          /* no-op */
        }
      }
    }

    openOverlay(extractTriggerData(trigger));
  }, true);

  overlay.addEventListener('click', (event) => {
    if (event.target === overlay || event.target.closest('[data-close-map-overlay]')) {
      closeOverlay();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !overlay.classList.contains('hidden')) {
      event.preventDefault();
      closeOverlay();
      return;
    }

    if ((event.key === 'Enter' || event.key === ' ') && document.activeElement && document.activeElement.hasAttribute('data-map-overlay-trigger')) {
      event.preventDefault();
      document.activeElement.click();
    }
  });

  window.tourMapOverlay = {
    ensureReady: () => ensureMapReady(),
    setDefaultData: (data) => mergePendingData(data),
    openWithData: (data) => openOverlay(data)
  };

  window.ensureTourMapInitialized = () => window.tourMapOverlay.ensureReady();
  window.updateTourMapData = (data) => window.tourMapOverlay.setDefaultData(data || {});
})();
