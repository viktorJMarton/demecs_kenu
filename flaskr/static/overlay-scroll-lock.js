/**
 * Shared, reference-counted page scroll lock for dialogs and overlays.
 * Each overlay owns a token so nested overlays cannot unlock one another.
 */
(function () {
  const locks = new Set();
  const bodyProperties = ['position', 'top', 'left', 'right', 'width', 'overflow'];
  const rootProperties = ['overscroll-behavior'];
  let snapshot = null;

  function captureStyle(style, properties) {
    return properties.map((property) => ({
      property,
      value: style.getPropertyValue(property),
      priority: style.getPropertyPriority(property)
    }));
  }

  function restoreStyle(style, entries) {
    entries.forEach(({ property, value, priority }) => {
      if (value) {
        style.setProperty(property, value, priority);
      } else {
        style.removeProperty(property);
      }
    });
  }

  function lock(token) {
    if (!token || locks.has(token)) return;

    if (locks.size === 0) {
      const scrollX = window.scrollX || window.pageXOffset || 0;
      const scrollY = window.scrollY || window.pageYOffset || 0;
      snapshot = {
        scrollX,
        scrollY,
        body: captureStyle(document.body.style, bodyProperties),
        root: captureStyle(document.documentElement.style, rootProperties)
      };

      document.body.style.position = 'fixed';
      document.body.style.top = `-${scrollY}px`;
      document.body.style.left = `-${scrollX}px`;
      document.body.style.right = '0';
      document.body.style.width = '100%';
      document.body.style.overflow = 'hidden';
      document.documentElement.style.setProperty('overscroll-behavior', 'none');
    }

    locks.add(token);
  }

  function unlock(token) {
    if (!token || !locks.delete(token) || locks.size > 0 || !snapshot) return;

    const previous = snapshot;
    snapshot = null;
    restoreStyle(document.body.style, previous.body);
    restoreStyle(document.documentElement.style, previous.root);
    window.scrollTo(previous.scrollX, previous.scrollY);
  }

  function isLocked(token) {
    return token ? locks.has(token) : locks.size > 0;
  }

  window.overlayScrollLock = { lock, unlock, isLocked };
})();
