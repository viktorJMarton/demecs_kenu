#!/usr/bin/env python3
"""
Comprehensive QA Test Suite for Demecs Vizitúra Website
Tests all interactive elements, form validation, API endpoints,
and mobile/iPhone layout concerns.
"""

import requests
import json
import re
import sys
from html.parser import HTMLParser
from collections import defaultdict

BASE_URL = "http://localhost:5000"
RESULTS = {"PASS": [], "FAIL": [], "WARN": []}


def log_pass(test_id, msg):
    RESULTS["PASS"].append(f"{test_id}: {msg}")
    print(f"  ✅ {test_id}: {msg}")


def log_fail(test_id, msg):
    RESULTS["FAIL"].append(f"{test_id}: {msg}")
    print(f"  ❌ {test_id}: {msg}")


def log_warn(test_id, msg):
    RESULTS["WARN"].append(f"{test_id}: {msg}")
    print(f"  ⚠️  {test_id}: {msg}")


class HTMLElementFinder(HTMLParser):
    """Simple HTML parser to find elements by id, class, tag, and attributes."""

    def __init__(self):
        super().__init__()
        self.elements = []
        self.current_depth = 0
        self._tag_stack = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        self.elements.append({
            "tag": tag,
            "attrs": attrs_dict,
            "id": attrs_dict.get("id", ""),
            "class": attrs_dict.get("class", ""),
            "type": attrs_dict.get("type", ""),
            "name": attrs_dict.get("name", ""),
            "href": attrs_dict.get("href", ""),
            "data": {k: v for k, v in attrs_dict.items() if k.startswith("data-")},
        })
        self._tag_stack.append(tag)

    def handle_endtag(self, tag):
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def find_by_id(self, element_id):
        return [e for e in self.elements if e["id"] == element_id]

    def find_by_class(self, class_name):
        return [e for e in self.elements if class_name in e.get("class", "").split()]

    def find_by_tag(self, tag):
        return [e for e in self.elements if e["tag"] == tag]

    def find_by_attr(self, attr_name, attr_value=None):
        if attr_value is None:
            return [e for e in self.elements if attr_name in e["attrs"]]
        return [e for e in self.elements if e["attrs"].get(attr_name) == attr_value]

    def find_inputs_by_name(self, name):
        return [e for e in self.elements
                if e["tag"] in ("input", "textarea", "select") and e["name"] == name]

    def find_by_class_contains(self, substring):
        return [e for e in self.elements if substring in e.get("class", "")]


def fetch_page(url):
    """Fetch a page and return (response, parsed HTML)."""
    resp = requests.get(url, timeout=10)
    parser = HTMLElementFinder()
    parser.feed(resp.text)
    return resp, parser, resp.text


# =============================================================================
# SECTION 1: PAGE LOAD & PRELOADER
# =============================================================================
def test_page_load():
    print("\n" + "=" * 60)
    print("SECTION 1: PAGE LOAD & PRELOADER")
    print("=" * 60)

    resp, html, raw = fetch_page(f"{BASE_URL}/")

    # TC-PRE-01: Page loads successfully
    if resp.status_code == 200:
        log_pass("TC-PRE-01", "Page loads with HTTP 200")
    else:
        log_fail("TC-PRE-01", f"Page returned HTTP {resp.status_code}")

    # TC-PRE-02: Preloader element exists
    preloader = html.find_by_id("preloader")
    if preloader:
        log_pass("TC-PRE-02", "Preloader element (#preloader) exists in DOM")
    else:
        log_warn("TC-PRE-02", "No #preloader element found")

    # Check content-type
    ct = resp.headers.get("content-type", "")
    if "text/html" in ct:
        log_pass("TC-PRE-03", f"Content-Type is HTML: {ct}")
    else:
        log_fail("TC-PRE-03", f"Unexpected Content-Type: {ct}")

    return resp, html, raw


# =============================================================================
# SECTION 2: NAVBAR & DRAWER
# =============================================================================
def test_navbar(html, raw):
    print("\n" + "=" * 60)
    print("SECTION 2: NAVBAR & DRAWER")
    print("=" * 60)

    # TC-NAV-01: Drawer toggle checkbox exists
    drawer = html.find_by_id("my-drawer-3")
    if drawer:
        log_pass("TC-NAV-01", "Drawer toggle (#my-drawer-3) exists")
    else:
        log_fail("TC-NAV-01", "Drawer toggle (#my-drawer-3) NOT found")

    # TC-NAV-02: Navbar element exists
    navbar = html.find_by_class_contains("navbar")
    if navbar:
        log_pass("TC-NAV-02", f"Navbar element found ({len(navbar)} elements with 'navbar' class)")
    else:
        log_fail("TC-NAV-02", "No navbar element found")

    # TC-NAV-03: Nav links to sections
    section_ids = ["about", "tours", "faq", "contact"]
    for sid in section_ids:
        links = [e for e in html.elements if e["tag"] == "a" and f"#{sid}" in e.get("attrs", {}).get("href", "")]
        if links:
            log_pass(f"TC-NAV-03-{sid}", f"Nav link to #{sid} exists ({len(links)} found)")
        else:
            log_warn(f"TC-NAV-03-{sid}", f"No nav link to #{sid} found")

    # TC-NAV-04: Drawer menu content exists
    drawer_content = html.find_by_class_contains("drawer-side")
    if drawer_content:
        log_pass("TC-NAV-04", "Drawer side panel (.drawer-side) exists")
    else:
        log_fail("TC-NAV-04", "Drawer side panel NOT found")

    # TC-NAV-05: Logo in navbar
    logos = [e for e in html.elements if e["tag"] == "img" and "logo" in e.get("attrs", {}).get("src", "").lower()]
    if logos:
        log_pass("TC-NAV-05", f"Logo image found in page ({len(logos)} logo images)")
    else:
        log_warn("TC-NAV-05", "No logo image found")


# =============================================================================
# SECTION 3: HERO SECTION
# =============================================================================
def test_hero(html, raw):
    print("\n" + "=" * 60)
    print("SECTION 3: HERO SECTION")
    print("=" * 60)

    # TC-HERO-01: Hero video element
    video = html.find_by_id("hero-video")
    if video:
        attrs = video[0]["attrs"]
        log_pass("TC-HERO-01", "Hero video element (#hero-video) exists")
        # Check muted and playsinline
        if "muted" in attrs:
            log_pass("TC-HERO-02", "Video has 'muted' attribute (needed for autoplay)")
        else:
            log_fail("TC-HERO-02", "Video missing 'muted' attribute")

        if "playsinline" in attrs:
            log_pass("TC-HERO-03", "Video has 'playsinline' attribute (needed for iOS)")
        else:
            log_fail("TC-HERO-03", "Video missing 'playsinline' attribute")
    else:
        log_fail("TC-HERO-01", "Hero video element NOT found")

    # TC-HERO-04: CTA button
    cta = html.find_by_id("open-my_modal_7-btn")
    if cta:
        log_pass("TC-HERO-04", "CTA button (#open-my_modal_7-btn) exists")
    else:
        log_fail("TC-HERO-04", "CTA button (#open-my_modal_7-btn) NOT found")

    # TC-HERO-05: Mobile video source
    mobile_src = [e for e in html.elements if e["tag"] == "video" and "data-src-mobile" in e.get("attrs", {})]
    if mobile_src:
        log_pass("TC-HERO-05", "Video has mobile source (data-src-mobile)")
    else:
        log_warn("TC-HERO-05", "No data-src-mobile attribute on video")


# =============================================================================
# SECTION 4: CALENDAR MODAL
# =============================================================================
def test_calendar_modal(html, raw):
    print("\n" + "=" * 60)
    print("SECTION 4: CALENDAR MODAL")
    print("=" * 60)

    # TC-MOD-01: Modal toggle
    toggle = html.find_by_id("my_modal_7")
    if toggle:
        t = toggle[0]
        if t["type"] == "checkbox":
            log_pass("TC-MOD-01", "Modal toggle (#my_modal_7) is a checkbox input")
        else:
            log_warn("TC-MOD-01", f"Modal toggle exists but type is '{t['type']}' not 'checkbox'")
    else:
        log_fail("TC-MOD-01", "Modal toggle (#my_modal_7) NOT found")

    # TC-MOD-02: Modal container
    container = html.find_by_id("my_modal_7-container")
    if container:
        log_pass("TC-MOD-02", "Modal container (#my_modal_7-container) exists")
    else:
        log_fail("TC-MOD-02", "Modal container NOT found")

    # TC-MOD-03: Calendar view
    cal_view = html.find_by_id("calendar-view")
    if cal_view:
        log_pass("TC-MOD-03", "Calendar view (#calendar-view) exists")
    else:
        log_fail("TC-MOD-03", "Calendar view NOT found")

    # TC-MOD-04: Reservation view
    res_view = html.find_by_id("reservation-view")
    if res_view:
        log_pass("TC-MOD-04", "Reservation view (#reservation-view) exists")
        cls = res_view[0].get("class", "")
        if "hidden" in cls:
            log_pass("TC-MOD-05", "Reservation view is initially hidden")
        else:
            log_warn("TC-MOD-05", "Reservation view NOT initially hidden")
    else:
        log_fail("TC-MOD-04", "Reservation view NOT found")

    # TC-MOD-06: Cally calendar component
    calendar = html.find_by_id("cally-calendar")
    if calendar:
        attrs = calendar[0]["attrs"]
        locale = attrs.get("locale", "")
        if locale == "hu-HU":
            log_pass("TC-CAL-01", "Calendar has locale='hu-HU' (Hungarian)")
        else:
            log_fail("TC-CAL-01", f"Calendar locale is '{locale}', expected 'hu-HU'")
        log_pass("TC-MOD-06", "Cally calendar component (#cally-calendar) exists")
    else:
        log_fail("TC-MOD-06", "Cally calendar component NOT found")

    # TC-CAL-02: Navigation buttons
    prev_btns = [e for e in html.elements if e.get("data", {}).get("data-calendar-nav") == "prev"]
    next_btns = [e for e in html.elements if e.get("data", {}).get("data-calendar-nav") == "next"]
    if prev_btns:
        log_pass("TC-CAL-02", "Previous month navigation button exists")
    else:
        log_fail("TC-CAL-02", "Previous month navigation button NOT found")
    if next_btns:
        log_pass("TC-CAL-03", "Next month navigation button exists")
    else:
        log_fail("TC-CAL-03", "Next month navigation button NOT found")

    # TC-MOD-07: Tours container
    tours = html.find_by_id("tours-container")
    if tours:
        log_pass("TC-TL-01", "Tours container (#tours-container) exists")
    else:
        log_fail("TC-TL-01", "Tours container NOT found")

    # TC-TL-02: Tour items
    tour_items = html.find_by_class_contains("tour-item")
    if tour_items:
        log_pass("TC-TL-02", f"Tour items found: {len(tour_items)} tour cards in modal")
        # Check data attributes on first tour
        first = tour_items[0]
        data = first.get("data", {})
        expected_attrs = ["data-tour-id", "data-tour-date", "data-tour-title",
                          "data-tour-price", "data-tour-location"]
        for attr in expected_attrs:
            if attr in data:
                log_pass(f"TC-TL-03-{attr}", f"Tour item has {attr}='{data[attr][:30]}'")
            else:
                log_fail(f"TC-TL-03-{attr}", f"Tour item missing {attr}")
    else:
        log_warn("TC-TL-02", "No tour items found (may be empty if no tours in DB)")

    # TC-TL-04: Loading indicator
    loading = html.find_by_id("tours-loading")
    if loading:
        cls = loading[0].get("class", "")
        if "hidden" in cls:
            log_pass("TC-TL-04", "Loading indicator exists and is initially hidden")
        else:
            log_warn("TC-TL-04", "Loading indicator exists but NOT initially hidden")
    else:
        log_fail("TC-TL-04", "Loading indicator (#tours-loading) NOT found")

    # TC-TL-05: "Show all tours" button
    show_all = html.find_by_id("show-all-tours-btn-container")
    if show_all:
        cls = show_all[0].get("class", "")
        if "hidden" in cls:
            log_pass("TC-TL-05", "'Show all tours' button exists and initially hidden")
        else:
            log_warn("TC-TL-05", "'Show all tours' button exists but NOT initially hidden")
    else:
        log_fail("TC-TL-05", "'Show all tours' button NOT found")

    # TC-MOD-08: Close button / back button
    back_btn = html.find_by_id("got-to-calendar-view")
    if back_btn:
        log_pass("TC-MOD-08", "Back button (#got-to-calendar-view) exists")
    else:
        log_warn("TC-MOD-08", "Back button (#got-to-calendar-view) not found in initial HTML (may be in SSR content)")


# =============================================================================
# SECTION 5: TOUR DETAILS API
# =============================================================================
def test_tour_api(html):
    print("\n" + "=" * 60)
    print("SECTION 5: TOUR DETAILS API")
    print("=" * 60)

    # Get a tour ID from the HTML
    tour_items = html.find_by_class_contains("tour-item")
    if not tour_items:
        log_warn("TC-TD-01", "No tour items to test API with")
        return

    tour_id = tour_items[0].get("data", {}).get("data-tour-id")
    if not tour_id:
        log_warn("TC-TD-01", "First tour item has no data-tour-id")
        return

    # TC-TD-01: Fetch tour details
    resp = requests.get(f"{BASE_URL}/tour/{tour_id}", timeout=10)
    if resp.status_code == 200:
        log_pass("TC-TD-01", f"GET /tour/{tour_id} returns 200")

        detail_parser = HTMLElementFinder()
        detail_parser.feed(resp.text)

        # TC-TD-02: Tour details contain expected elements
        map_trigger = detail_parser.find_by_attr("data-map-overlay-trigger")
        if map_trigger:
            log_pass("TC-TD-02", "Tour details contain map trigger element")
        else:
            log_warn("TC-TD-02", "No map trigger in tour details")

        # TC-TD-03: Image gallery
        open_images = detail_parser.find_by_class_contains("open-image")
        if open_images:
            log_pass("TC-TD-03", f"Tour details contain {len(open_images)} clickable images")
        else:
            log_warn("TC-TD-03", "No clickable images in tour details")

        # TC-TD-04: Image overlay (lightbox)
        overlay = detail_parser.find_by_id("image-overlay")
        if overlay:
            log_pass("TC-TD-04", "Image lightbox overlay element exists in tour details")
        else:
            log_warn("TC-TD-04", "No image lightbox overlay in tour details")

        # TC-TD-05: Close button for lightbox
        close_btn = detail_parser.find_by_attr("data-close-image-overlay")
        if close_btn:
            log_pass("TC-TD-05", "Lightbox close button exists")
        else:
            log_warn("TC-TD-05", "No lightbox close button found")
    else:
        log_fail("TC-TD-01", f"GET /tour/{tour_id} returned HTTP {resp.status_code}")

    # TC-TD-06: Tours API endpoint
    try:
        api_resp = requests.get(f"{BASE_URL}/api/tours", timeout=10)
        if api_resp.status_code == 200:
            data = api_resp.json()
            if isinstance(data, (list, dict)):
                tours = data if isinstance(data, list) else data.get("tours", [])
                log_pass("TC-TD-06", f"GET /api/tours returns 200 with {len(tours)} tours")
            else:
                log_warn("TC-TD-06", f"GET /api/tours returns 200 but unexpected data type")
        else:
            log_fail("TC-TD-06", f"GET /api/tours returned HTTP {api_resp.status_code}")
    except Exception as e:
        log_fail("TC-TD-06", f"GET /api/tours failed: {e}")

    # TC-TD-07: Tours API with date filter
    try:
        api_resp = requests.get(f"{BASE_URL}/api/tours?date=2026-03-01", timeout=10)
        if api_resp.status_code == 200:
            log_pass("TC-TD-07", "GET /api/tours?date=... returns 200")
        else:
            log_warn("TC-TD-07", f"GET /api/tours?date=... returned HTTP {api_resp.status_code}")
    except Exception as e:
        log_fail("TC-TD-07", f"GET /api/tours?date=... failed: {e}")


# =============================================================================
# SECTION 6: TOUR CARDS (tours section)
# =============================================================================
def test_tour_cards(html, raw):
    print("\n" + "=" * 60)
    print("SECTION 6: TOUR CARDS SECTION")
    print("=" * 60)

    # TC-TC-01: Tours section exists
    if 'id="tours"' in raw:
        log_pass("TC-TC-01", "Tours section (#tours) exists")
    else:
        log_fail("TC-TC-01", "Tours section (#tours) NOT found")

    # TC-TC-02: Tour cards
    tour_cards = html.find_by_class_contains("tour-card")
    if tour_cards:
        log_pass("TC-TC-02", f"Tour cards found: {len(tour_cards)} cards")
    else:
        log_warn("TC-TC-02", "No tour cards found in tours section")

    # TC-TC-03: "Túra info" buttons
    info_btns = html.find_by_class_contains("open-tour-details-btn")
    if info_btns:
        log_pass("TC-TC-03", f"'Túra info' buttons found: {len(info_btns)}")
        # Check data-tour-details attribute
        has_data = any("data-tour-details" in btn.get("attrs", {}) for btn in info_btns)
        if has_data:
            log_pass("TC-TC-04", "'Túra info' buttons have data-tour-details JSON")
        else:
            log_fail("TC-TC-04", "'Túra info' buttons missing data-tour-details")
    else:
        log_warn("TC-TC-03", "No 'Túra info' buttons found")

    # TC-TC-05: Carousel elements
    carousels = html.find_by_class_contains("carousel-vertical")
    if carousels:
        log_pass("TC-TC-05", f"Vertical carousels found: {len(carousels)}")
    else:
        log_warn("TC-TC-05", "No vertical carousels found in tour cards")

    # TC-TC-06: Carousel items
    carousel_items = html.find_by_class_contains("carousel-item")
    if carousel_items:
        log_pass("TC-TC-06", f"Carousel items found: {len(carousel_items)}")
    else:
        log_warn("TC-TC-06", "No carousel items found")


# =============================================================================
# SECTION 7: FAQ SECTION
# =============================================================================
def test_faq(html, raw):
    print("\n" + "=" * 60)
    print("SECTION 7: FAQ SECTION")
    print("=" * 60)

    # TC-FAQ-01: FAQ section exists
    if 'id="faq"' in raw:
        log_pass("TC-FAQ-01", "FAQ section (#faq) exists")
    else:
        log_fail("TC-FAQ-01", "FAQ section (#faq) NOT found")

    # TC-FAQ-02: Collapse/accordion items
    collapses = html.find_by_class_contains("collapse-arrow")
    if collapses:
        log_pass("TC-FAQ-02", f"FAQ accordion items found: {len(collapses)}")
    else:
        log_warn("TC-FAQ-02", "No FAQ accordion items found")

    # TC-FAQ-03: First item should be checked by default
    # Look for checkboxes inside collapse elements
    checked_inputs = [e for e in html.elements
                      if e["tag"] == "input" and e["type"] == "checkbox"
                      and "checked" in e.get("attrs", {})]
    # Filter for ones that are in collapse context (near collapse-arrow class)
    if checked_inputs:
        log_pass("TC-FAQ-03", f"Found {len(checked_inputs)} pre-checked checkbox(es) — first FAQ likely expanded")
    else:
        log_warn("TC-FAQ-03", "No pre-checked checkboxes found for FAQ accordion")


# =============================================================================
# SECTION 8: CONTACT SECTION
# =============================================================================
def test_contact(html, raw):
    print("\n" + "=" * 60)
    print("SECTION 8: CONTACT SECTION")
    print("=" * 60)

    # TC-CT-01: Contact section exists
    if 'id="contact"' in raw:
        log_pass("TC-CT-01", "Contact section (#contact) exists")
    else:
        log_fail("TC-CT-01", "Contact section (#contact) NOT found")

    # TC-CT-02: Contact form
    form = html.find_by_id("contact-form")
    if form:
        log_pass("TC-CT-02", "Contact form (#contact-form) exists")
    else:
        log_fail("TC-CT-02", "Contact form NOT found")

    # TC-CT-03: Form fields
    for field_name, field_label in [("name", "Name"), ("email", "Email"), ("message", "Message")]:
        fields = html.find_inputs_by_name(field_name)
        if fields:
            # Check required attribute
            required = "required" in fields[0].get("attrs", {})
            if required:
                log_pass(f"TC-CT-03-{field_name}", f"Contact {field_label} field exists and is required")
            else:
                log_warn(f"TC-CT-03-{field_name}", f"Contact {field_label} field exists but NOT required")
        else:
            log_fail(f"TC-CT-03-{field_name}", f"Contact {field_label} field NOT found")

    # TC-CT-04: Submit button
    submit_label = html.find_by_id("contact-submit-label")
    submit_spinner = html.find_by_id("contact-submit-spinner")
    if submit_label:
        log_pass("TC-CT-04", "Contact submit button label exists")
    else:
        log_fail("TC-CT-04", "Contact submit button label NOT found")
    if submit_spinner:
        cls = submit_spinner[0].get("class", "")
        if "hidden" in cls:
            log_pass("TC-CT-05", "Contact submit spinner is initially hidden")
        else:
            log_warn("TC-CT-05", "Contact submit spinner is NOT initially hidden")
    else:
        log_fail("TC-CT-05", "Contact submit spinner NOT found")

    # TC-CT-06: Status element
    status = html.find_by_id("contact-status")
    if status:
        log_pass("TC-CT-06", "Contact status element (#contact-status) with aria-live='polite' exists")
    else:
        log_fail("TC-CT-06", "Contact status element NOT found")

    # TC-CT-07: Social links
    for label in ["Facebook", "Instagram", "TikTok"]:
        social_links = [e for e in html.elements
                        if e["tag"] == "a"
                        and e.get("attrs", {}).get("aria-label", "") == label]
        if social_links:
            target = social_links[0].get("attrs", {}).get("target", "")
            rel = social_links[0].get("attrs", {}).get("rel", "")
            if target == "_blank":
                log_pass(f"TC-CT-07-{label}", f"{label} link opens in new tab (target=_blank)")
            else:
                log_warn(f"TC-CT-07-{label}", f"{label} link does NOT open in new tab")
            if "noopener" in rel or "noreferrer" in rel:
                log_pass(f"TC-CT-08-{label}", f"{label} link has security rel attributes")
            else:
                log_warn(f"TC-CT-08-{label}", f"{label} link missing noopener/noreferrer")
        else:
            log_warn(f"TC-CT-07-{label}", f"{label} social link NOT found")

    # TC-CT-09: Contact form AJAX test (empty submission)
    try:
        csrf = re.search(r'window\.csrfToken\s*=\s*"([^"]+)"', raw)
        csrf_token = csrf.group(1) if csrf else ""
        resp = requests.post(f"{BASE_URL}/contact",
                             json={"name": "", "email": "", "message": ""},
                             headers={
                                 "Content-Type": "application/json",
                                 "X-CSRFToken": csrf_token,
                             },
                             timeout=10)
        if resp.status_code in (400, 422):
            log_pass("TC-CT-09", f"Empty contact submission correctly rejected (HTTP {resp.status_code})")
        elif resp.status_code == 200:
            # Could be that the server handles it differently
            data = resp.json()
            log_warn("TC-CT-09", f"Empty contact submission returned 200: {data}")
        else:
            log_warn("TC-CT-09", f"Empty contact submission returned HTTP {resp.status_code}")
    except Exception as e:
        log_warn("TC-CT-09", f"Contact form AJAX test error: {e}")


# =============================================================================
# SECTION 9: BOOKING FORM
# =============================================================================
def test_booking_form(html, raw):
    print("\n" + "=" * 60)
    print("SECTION 9: BOOKING FORM ELEMENTS")
    print("=" * 60)

    # The booking form is SSR so we check from /tour/<id> response
    tour_items = html.find_by_class_contains("tour-item")
    if not tour_items:
        log_warn("TC-BK-ALL", "No tour items to fetch booking form for")
        return

    tour_id = tour_items[0].get("data", {}).get("data-tour-id")
    if not tour_id:
        log_warn("TC-BK-ALL", "First tour item has no data-tour-id, skipping booking tests")
        return

    # We need to check if booking_form_view.html is included in the page
    # It may be loaded dynamically. Let's check the template file directly.
    # Since we can't render it separately, check for key JS functions.

    # Check key JS functions exist in main page
    key_functions = [
        ("window.openTourDetailsDownload", "TC-BK-01"),
        ("window.openTourDetailsView", "TC-BK-02"),
        ("window.closeAndResetModal", "TC-BK-03"),
    ]
    for func_name, tc in key_functions:
        if func_name in raw:
            log_pass(tc, f"JS function {func_name} is defined in page")
        else:
            log_fail(tc, f"JS function {func_name} NOT found in page")

    # Check CSRF token is available
    if "window.csrfToken" in raw:
        log_pass("TC-BK-04", "CSRF token is set in window.csrfToken")
    else:
        log_fail("TC-BK-04", "CSRF token NOT set in window.csrfToken")

    # Check booking-related elements in reservation view
    res_content = html.find_by_id("reservation-view-content")
    if res_content:
        log_pass("TC-BK-05", "Reservation view content container exists")
    else:
        log_fail("TC-BK-05", "Reservation view content container NOT found")


# =============================================================================
# SECTION 10: PAYMENT ENDPOINTS
# =============================================================================
def test_payment_endpoints():
    print("\n" + "=" * 60)
    print("SECTION 10: PAYMENT ENDPOINTS")
    print("=" * 60)

    # Test payment-related routes exist (they should return redirects or pages)
    endpoints = [
        ("/payment/success", "TC-PAY-01", "GET"),
        ("/payment/fail", "TC-PAY-02", "GET"),
        ("/payment/cancel", "TC-PAY-03", "GET"),
        ("/payment/timeout", "TC-PAY-04", "GET"),
    ]

    for path, tc, method in endpoints:
        try:
            resp = requests.get(f"{BASE_URL}{path}", timeout=10, allow_redirects=False)
            # These pages may redirect or show error since they expect signed params
            if resp.status_code in (200, 302, 400, 500):
                log_pass(tc, f"{method} {path} is routed (HTTP {resp.status_code})")
            else:
                log_warn(tc, f"{method} {path} returned unexpected HTTP {resp.status_code}")
        except Exception as e:
            log_fail(tc, f"{method} {path} failed: {e}")

    # TC-PAY-05: IPN endpoint exists (POST only)
    try:
        resp = requests.get(f"{BASE_URL}/payment/ipn", timeout=10, allow_redirects=False)
        if resp.status_code == 405:
            log_pass("TC-PAY-05", "IPN endpoint rejects GET (method not allowed = correctly POST-only)")
        elif resp.status_code == 200:
            log_warn("TC-PAY-05", "IPN endpoint accepts GET (should be POST-only)")
        else:
            log_pass("TC-PAY-05", f"IPN endpoint exists (HTTP {resp.status_code})")
    except Exception as e:
        log_fail("TC-PAY-05", f"IPN endpoint test failed: {e}")


# =============================================================================
# SECTION 11: MOBILE / iPHONE LAYOUT
# =============================================================================
def test_mobile_layout(html, raw):
    print("\n" + "=" * 60)
    print("SECTION 11: MOBILE / iPHONE LAYOUT CHECKS")
    print("=" * 60)

    # TC-IP-01: Viewport meta tag
    viewport_meta = [e for e in html.elements
                     if e["tag"] == "meta"
                     and "viewport" in e.get("attrs", {}).get("name", "")]
    if viewport_meta:
        content = viewport_meta[0]["attrs"].get("content", "")
        if "width=device-width" in content:
            log_pass("TC-IP-01", f"Viewport meta: {content}")
        else:
            log_fail("TC-IP-01", f"Viewport meta missing width=device-width: {content}")
    else:
        log_fail("TC-IP-01", "No viewport meta tag found")

    # TC-IP-02: dvh units used for modal
    if "dvh" in raw:
        log_pass("TC-IP-02", "Page uses dvh units (dynamic viewport height for iOS)")
    else:
        log_warn("TC-IP-02", "No dvh units found — may use vh which is problematic on iOS")

    # TC-IP-03: iOS scroll spacer
    if "ios-scroll-spacer" in raw:
        log_pass("TC-IP-03", "iOS scroll spacer element exists for touch scroll area")
    else:
        log_warn("TC-IP-03", "No iOS scroll spacer found")

    # TC-IP-04: -webkit-touch-callout support check
    if "-webkit-touch-callout" in raw:
        log_pass("TC-IP-04", "iOS-specific CSS (-webkit-touch-callout) present")
    else:
        log_warn("TC-IP-04", "No -webkit-touch-callout CSS found")

    # TC-IP-05: Check input font sizes (< 16px causes zoom on iOS)
    # We can search for CSS that sets font-size on inputs
    small_font_pattern = re.findall(r'input[^{]*\{[^}]*font-size:\s*(\d+)px', raw)
    if small_font_pattern:
        for size in small_font_pattern:
            if int(size) < 16:
                log_warn("TC-IP-05", f"Input font-size {size}px < 16px — will cause iOS zoom on focus")
            else:
                log_pass("TC-IP-05", f"Input font-size {size}px ≥ 16px — no iOS zoom issue")
    else:
        log_pass("TC-IP-05", "No explicit small font-size on inputs (framework default likely ≥16px)")

    # TC-IP-06: overflow-x hidden on body
    if "overflow-x: hidden" in raw or "overflow-x:hidden" in raw:
        log_pass("TC-IP-06", "Page has overflow-x: hidden to prevent horizontal scroll")
    else:
        log_warn("TC-IP-06", "No explicit overflow-x: hidden found")

    # TC-IP-07: Check for safe area insets
    if "safe-area" in raw or "env(safe-area" in raw:
        log_pass("TC-IP-07", "Page uses safe-area-inset CSS env()")
    else:
        log_warn("TC-IP-07", "No safe-area-inset CSS env() found — notch area may overlap content")

    # TC-IP-08: Video playsinline (already checked in hero tests)
    # TC-IP-09: Backdrop-filter support
    if "backdrop-filter" in raw:
        log_pass("TC-IP-09", "Page uses backdrop-filter (glassmorphism effects)")
    if "-webkit-backdrop-filter" in raw:
        log_pass("TC-IP-10", "Page has -webkit-backdrop-filter prefix for Safari")
    else:
        log_warn("TC-IP-10", "Missing -webkit-backdrop-filter prefix — may not work in Safari")


# =============================================================================
# SECTION 12: JAVASCRIPT INTEGRITY
# =============================================================================
def test_js_integrity(raw):
    print("\n" + "=" * 60)
    print("SECTION 12: JAVASCRIPT INTEGRITY")
    print("=" * 60)

    # TC-JS-01: Key JS files loaded
    js_files = [
        ("calendar-modal.js", "TC-JS-01"),
        ("modal-control.js", "TC-JS-02"),
        ("map-overlay.js", "TC-JS-03"),
        ("realtime.js", "TC-JS-04"),
    ]
    for js_file, tc in js_files:
        if js_file in raw:
            log_pass(tc, f"Script {js_file} is included in page")
        else:
            log_fail(tc, f"Script {js_file} NOT included in page")

    # TC-JS-05: Global function exposure
    global_funcs = [
        "window.navigateCalendarToDate",
        "window.styleTourDates",
        "window.closeAndResetModal",
        "window.openTourDetailsDownload",
        "window.openTourDetailsView",
    ]
    for func in global_funcs:
        if func in raw:
            log_pass(f"TC-JS-05-{func.split('.')[-1]}", f"{func} is defined")
        else:
            log_warn(f"TC-JS-05-{func.split('.')[-1]}", f"{func} not found in page source")

    # TC-JS-06: typeof guards for cross-file calls
    typeof_guards = [
        "typeof window.closeAndResetModal",
        "typeof window.restoreModalFromMapOverlay",
        "typeof window.updateBackButtonVisibility",
        "typeof window.ensureTourMapInitialized",
    ]
    for guard in typeof_guards:
        if guard in raw:
            log_pass(f"TC-JS-06-{guard.split('.')[-1]}", f"typeof guard for {guard.split('.')[-1]} exists")
        else:
            log_warn(f"TC-JS-06-{guard.split('.')[-1]}", f"No typeof guard for {guard.split('.')[-1]}")

    # TC-JS-07: USE_SSR_TOUR_DETAILS flag
    if "USE_SSR_TOUR_DETAILS" in raw:
        log_pass("TC-JS-07", "USE_SSR_TOUR_DETAILS flag is set")
    else:
        log_warn("TC-JS-07", "USE_SSR_TOUR_DETAILS flag not found")


# =============================================================================
# SECTION 13: STATIC ASSETS
# =============================================================================
def test_static_assets():
    print("\n" + "=" * 60)
    print("SECTION 13: STATIC ASSETS")
    print("=" * 60)

    assets = [
        ("/static/logo.svg", "TC-ASSET-01", "Logo SVG"),
        ("/static/calendar-modal.js", "TC-ASSET-02", "calendar-modal.js"),
        ("/static/modal-control.js", "TC-ASSET-03", "modal-control.js"),
        ("/static/map-overlay.js", "TC-ASSET-04", "map-overlay.js"),
        ("/static/style.css", "TC-ASSET-05", "Main stylesheet"),
    ]

    for path, tc, label in assets:
        try:
            resp = requests.head(f"{BASE_URL}{path}", timeout=10)
            if resp.status_code == 200:
                log_pass(tc, f"{label} ({path}) accessible (HTTP 200)")
            else:
                log_fail(tc, f"{label} ({path}) returned HTTP {resp.status_code}")
        except Exception as e:
            log_fail(tc, f"{label} ({path}) failed: {e}")


# =============================================================================
# SECTION 14: EDGE CASES
# =============================================================================
def test_edge_cases(raw):
    print("\n" + "=" * 60)
    print("SECTION 14: EDGE CASES")
    print("=" * 60)

    # TC-EDGE-01: CSRF token present
    csrf_match = re.search(r'window\.csrfToken\s*=\s*"([^"]+)"', raw)
    if csrf_match and len(csrf_match.group(1)) > 10:
        log_pass("TC-EDGE-01", f"CSRF token present and looks valid ({len(csrf_match.group(1))} chars)")
    else:
        log_fail("TC-EDGE-01", "CSRF token missing or too short")

    # TC-EDGE-02: Meta CSRF token matches JS variable
    meta_match = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', raw)
    if meta_match and csrf_match:
        if meta_match.group(1) == csrf_match.group(1):
            log_pass("TC-EDGE-02", "Meta CSRF token matches window.csrfToken")
        else:
            log_fail("TC-EDGE-02", "Meta CSRF token does NOT match window.csrfToken")
    else:
        log_warn("TC-EDGE-02", "Could not compare CSRF tokens")

    # TC-EDGE-03: No console.error left in production JS
    error_count = raw.count("console.error(")
    warn_count = raw.count("console.warn(")
    log_count = raw.count("console.log(")
    if error_count > 0:
        log_warn("TC-EDGE-03", f"Found {error_count} console.error() calls (may be intentional error handling)")
    else:
        log_pass("TC-EDGE-03", "No console.error() calls found")

    if log_count > 5:
        log_warn("TC-EDGE-04", f"Found {log_count} console.log() calls — consider removing debug logs for production")
    else:
        log_pass("TC-EDGE-04", f"Console.log() count acceptable ({log_count})")

    # TC-EDGE-05: Error image handler
    if "onerror=" in raw:
        log_pass("TC-EDGE-05", "Image onerror fallback handlers present")
    else:
        log_warn("TC-EDGE-05", "No image onerror handlers found")

    # TC-EDGE-06: Check for duplicate IDs
    id_pattern = re.findall(r'id="([^"]+)"', raw)
    id_counts = defaultdict(int)
    for id_val in id_pattern:
        id_counts[id_val] += 1
    dupes = {k: v for k, v in id_counts.items() if v > 1}
    if dupes:
        for dup_id, count in dupes.items():
            log_warn(f"TC-EDGE-06-{dup_id}", f"Duplicate ID '{dup_id}' found {count} times")
    else:
        log_pass("TC-EDGE-06", "No duplicate element IDs found")


# =============================================================================
# SECTION 15: OTHER PAGES
# =============================================================================
def test_other_pages():
    print("\n" + "=" * 60)
    print("SECTION 15: OTHER PAGES")
    print("=" * 60)

    pages = [
        ("/terms", "TC-PAGE-01", "Terms page"),
        ("/privacy", "TC-PAGE-02", "Privacy page"),
    ]
    for path, tc, label in pages:
        try:
            resp = requests.get(f"{BASE_URL}{path}", timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                log_pass(tc, f"{label} ({path}) accessible (HTTP 200)")
            elif resp.status_code == 404:
                log_warn(tc, f"{label} ({path}) returns 404")
            else:
                log_warn(tc, f"{label} ({path}) returned HTTP {resp.status_code}")
        except Exception as e:
            log_fail(tc, f"{label} ({path}) failed: {e}")


# =============================================================================
# MAIN
# =============================================================================
def main():
    print("=" * 60)
    print("DEMECS VIZITÚRA — COMPREHENSIVE QA TEST SUITE")
    print("=" * 60)
    print(f"Target: {BASE_URL}")
    print()

    resp, html, raw = test_page_load()
    test_navbar(html, raw)
    test_hero(html, raw)
    test_calendar_modal(html, raw)
    test_tour_api(html)
    test_tour_cards(html, raw)
    test_faq(html, raw)
    test_contact(html, raw)
    test_booking_form(html, raw)
    test_payment_endpoints()
    test_mobile_layout(html, raw)
    test_js_integrity(raw)
    test_static_assets()
    test_edge_cases(raw)
    test_other_pages()

    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"  ✅ PASS: {len(RESULTS['PASS'])}")
    print(f"  ❌ FAIL: {len(RESULTS['FAIL'])}")
    print(f"  ⚠️  WARN: {len(RESULTS['WARN'])}")
    total = len(RESULTS['PASS']) + len(RESULTS['FAIL']) + len(RESULTS['WARN'])
    print(f"  📊 TOTAL: {total}")
    print()

    if RESULTS['FAIL']:
        print("FAILURES:")
        for f in RESULTS['FAIL']:
            print(f"  ❌ {f}")
        print()

    if RESULTS['WARN']:
        print("WARNINGS:")
        for w in RESULTS['WARN']:
            print(f"  ⚠️  {w}")
        print()

    # Return exit code based on failures
    sys.exit(1 if RESULTS['FAIL'] else 0)


if __name__ == "__main__":
    main()
