"""Email sending utilities for contact form and booking confirmations."""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Iterable, List, Mapping, Optional
import html as _html
from flask import url_for


class EmailServiceError(RuntimeError):
    """Raised when the email service cannot complete an operation."""


@dataclass
class EmailConfig:
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    sender: str = "demecs.kenu@gmail.com"
    contact_recipient: str = "demecs.kenu@gmail.com"
    use_tls: bool = True

    @classmethod
    def from_env(cls) -> "EmailConfig":
        return cls(
            smtp_host=os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.getenv("EMAIL_SMTP_PORT", "587")),
            smtp_username=os.getenv("EMAIL_SMTP_USERNAME"),
            smtp_password=os.getenv("EMAIL_SMTP_PASSWORD"),
            sender=os.getenv("EMAIL_FROM")
            or os.getenv("EMAIL_SMTP_USERNAME")
            or "demecs.kenu@gmail.com",
            contact_recipient=os.getenv("CONTACT_RECIPIENT", "demecs.kenu@gmail.com"),
            use_tls=os.getenv("EMAIL_SMTP_USE_TLS", "true").lower() != "false",
        )

    @property
    def base_url(self) -> str:
        """Return the base URL for the application, preferring env var."""
        return os.getenv("APP_BASE_URL", "https://demecskenu.hu").rstrip("/")


class EmailService:
    """Lightweight SMTP wrapper for the Demecs Kenu Vizitúra  site."""

    def __init__(self, config: EmailConfig):
        self._config = config

    @classmethod
    def from_env(cls) -> "EmailService":
        return cls(EmailConfig.from_env())

    # Core helpers ---------------------------------------------------------
    def _build_message(
        self,
        subject: str,
        body: str,
        recipients: Iterable[str],
        reply_to: Optional[str] = None,
    ) -> EmailMessage:
        targets = [addr.strip() for addr in recipients if addr and addr.strip()]
        if not targets:
            raise EmailServiceError("At least one valid recipient address is required")

        msg = EmailMessage()
        msg["Subject"] = subject.strip() or "Demecs Kenu Vizitúra"
        msg["From"] = self._config.sender
        msg["To"] = ", ".join(targets)
        if reply_to:
            msg["Reply-To"] = reply_to.strip()
        msg.set_content(body)
        return msg

    def _send(self, message: EmailMessage) -> None:
        try:
            with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port, timeout=30) as server:
                if self._config.use_tls:
                    server.starttls()
                if self._config.smtp_username:
                    server.login(
                        self._config.smtp_username,
                        self._config.smtp_password or "",
                    )
                server.send_message(message)
        except Exception as exc:  # pragma: no cover - network failures
            raise EmailServiceError(f"SMTP send failed: {exc}") from exc

    # Public API -----------------------------------------------------------
    def send_contact_message(self, name: str, email: str, message: str) -> None:
        subject = f"Kapcsolati űrlap: {name or 'Névtelen érdeklődő'}"
        body_lines: List[str] = [
            "Új üzenet érkezett a kapcsolatfelvételi űrlapról:",
            "",
            f"Név: {name or 'Nincs megadva'}",
            f"Email: {email or 'Nincs megadva'}",
            "",
            "Üzenet:",
            message or "(Üres)",
        ]
        msg = self._build_message(
            subject=subject,
            body="\n".join(body_lines),
            recipients=[self._config.contact_recipient],
            reply_to=email or None,
        )
        self._send(msg)

    def send_booking_confirmation(
        self,
        booking: Mapping[str, object],
        tour: Optional[Mapping[str, object]] = None,
    ) -> None:
        """Send confirmation to customer and notification to the admin inbox."""

        tour_title = (tour or {}).get("title") or booking.get("tour_title") or "Ismeretlen túra"
        tour_date = (tour or {}).get("date") or booking.get("tour_date")
        tour_time = (tour or {}).get("time") or booking.get("tour_time")
        participants = booking.get("participants_count") or booking.get("participants") or "?"
        order_ref = booking.get("order_ref") or "n/a"
        base_lines = [
            f"Túra: {tour_title}",
            f"Időpont: {tour_date or '-'} {tour_time or ''}",
            f"Résztvevők: {participants}",
            f"Foglalási azonosító: {order_ref}",
            "_______________________________________________",
            "Foglalási adatok:",
            f"Név: {booking.get('customer_name', '-')}",
            f"Email: {booking.get('customer_email', '-')}",
            f"Telefon: {booking.get('customer_phone', '-')}",
        ]

        # Plain text body (fallback)
        plain_body = "\n".join([
            "Kedves Túrázó!",
            "",
            "Köszönjük a foglalást. Az alábbi részleteket rögzítettük:",
            "",
            *base_lines,
            "",
            f"Ha kérdésed van, írj bátran: {self._config.contact_recipient}",
        ])

        # HTML template – fill with escaped values
        guest_name = _html.escape(str(booking.get('customer_name') or '').strip()) or 'Vendég'
        booking_id = _html.escape(str(order_ref))
        date_val = _html.escape(str(tour_date or '-'))
        time_val = _html.escape(str(tour_time or ''))
        service_name = _html.escape(str((tour or {}).get('title') or booking.get('tour_title') or tour_title or 'Túra'))
        guests = _html.escape(str(booking.get('participants_count') or booking.get('participants') or '?'))
        total_price = _html.escape(str(booking.get('total_price') or booking.get('total') or '-'))
        currency = _html.escape(str(booking.get('currency') or 'Ft'))
        customer_note = _html.escape(str(booking.get('customer_notes') or booking.get('notes') or ''))
        calendar_link = _html.escape(str(booking.get('calendar_link') or '#'))
        
        # Google Maps link generation
        lat = (tour or {}).get("latitude") or (tour or {}).get("tour_latitude") or booking.get("tour_latitude") or booking.get("tour_lat_final")
        lng = (tour or {}).get("longitude") or (tour or {}).get("tour_longitude") or booking.get("tour_longitude") or booking.get("tour_lng_final")
        
        google_maps_link = ""
        google_maps_row = ""
        if lat and lng:
            google_maps_link = f"https://maps.google.com/?q={lat},{lng}"
            google_maps_row = (
                f'<tr><td style="color:#6b7280;width:40%;font-weight:600;padding:6px 8px;">Helyszín</td>'
                f'<td style="padding:6px 8px;color:#111827;">'
                f'<a href="{google_maps_link}" target="_blank" style="color:#0ea5e9;text-decoration:none;font-weight:600;">'
                f'📍 Térkép megnyitása'
                f'</a></td></tr>'
            )

        # Use configured base URL for logo to ensure it works in emails
        logo_url = f"{self._config.base_url}/static/logo.svg"
        
        html_body = f"""<!doctype html>
<html lang=\"hu\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"> <title>Foglalás visszaigazolás</title></head>
<body style=\"margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;\">
<span style=\"display:none;visibility:hidden;mso-hide:all;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;\">Foglalásod sikeresen rögzítettük — az alábbiakban a részletek és a módosításhoz szükséges link található.</span>
<div style=\"width:100%;background:#f4f6f8;padding:24px 12px;\">
<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"max-width:680px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 6px 18px rgba(13,26,38,0.08);\">
<tr><td>
<div style=\"padding:20px 28px;display:flex;align-items:center;gap:12px;\">
  <img src=\"{logo_url}\" alt=\"Demecs Kenu Vízitúra\" style=\"width:56px;height:56px;border-radius:10px;object-fit:contain;\">
  <div>
    <div style=\"font-size:18px;font-weight:700;color:#0b1220;\">Demecs Kenu Vízitúra</div>
    <div style=\"font-size:13px;color:#6b7280;\">Foglalás visszaigazolás</div>
  </div>
</div>
<div style=\"padding:22px 28px 8px 28px;\">
  <div style=\"font-size:20px;font-weight:700;margin:6px 0 8px;color:#0b1220;\">Köszönjük, {guest_name} — foglalásod rögzítve!</div>
  <p style=\"font-size:15px;color:#374151;margin:0 0 16px;\">A foglalásod sikeresen megtörtént. Lent megtalálod a foglalás részleteit </p>

  <div style=\"background:#f8fafc;border-radius:10px;padding:14px;margin-bottom:16px;\">
    <table role=\"presentation\" width=\"100%\" style=\"border-collapse:collapse;\">
      <tr><td style=\"color:#6b7280;width:40%;font-weight:600;padding:6px 8px;\">Foglalás azonosító</td><td style=\"padding:6px 8px;color:#111827;\">{booking_id}</td></tr>
      <tr><td style=\"color:#6b7280;width:40%;font-weight:600;padding:6px 8px;\">Dátum</td><td style=\"padding:6px 8px;color:#111827;\">{date_val} — {time_val}</td></tr>
      <tr><td style=\"color:#6b7280;width:40%;font-weight:600;padding:6px 8px;\">Szolgáltatás</td><td style=\"padding:6px 8px;color:#111827;\">{service_name}</td></tr>
      {google_maps_row}
      <tr><td style=\"color:#6b7280;width:40%;font-weight:600;padding:6px 8px;\">Vendégek száma</td><td style=\"padding:6px 8px;color:#111827;\">{guests}</td></tr>
      <tr><td style=\"color:#6b7280;width:40%;font-weight:600;padding:6px 8px;\">Összeg</td><td style=\"padding:6px 8px;color:#111827;\">{total_price} {currency}</td></tr>
    </table>
  </div>

 

  <p style=\"font-size:14px;color:#374151;margin:0 28px 16px;\">Megjegyzés: {customer_note}</p>
</div>

<div style=\"padding:0 28px 12px;\"><hr style=\"border:none;border-top:1px solid #eef2f7;margin:0 0 12px;\"><p style=\"font-size:14px;color:#6b7280;margin:0 0 10px;\">Ha kérdésed van, válaszolj erre az e-mailre, vagy vedd fel velünk a kapcsolatot a <a href=\"mailto:{self._config.contact_recipient}\">{self._config.contact_recipient}</a> címen.</p></div>

<div style=\"font-size:13px;color:#6b7280;padding:18px 28px 28px;\"><div style=\"margin-bottom:8px;\">Demecs Kenu Vízitúra<br>Magyarország</div><div>© 2025 Demecs Kenu Vízitúra. Minden jog fenntartva.</div></div>

</td></tr></table></div></body></html>"""

        # Send to customer (if email present) as multipart alternative
        customer_email = (booking.get("customer_email") or "").strip()
        if customer_email:
            customer_msg = EmailMessage()
            customer_msg["Subject"] = f"Foglalás visszaigazolása – {tour_title}"
            customer_msg["From"] = self._config.sender
            customer_msg["To"] = customer_email
            customer_msg["Reply-To"] = self._config.contact_recipient
            customer_msg.set_content(plain_body)
            customer_msg.add_alternative(html_body, subtype="html")
            self._send(customer_msg)

        # Admin notification (keep plaintext for admin inbox; HTML optional)
        invoice_lines = [
            "",
            "Számlázási adatok:",
            f"Név: {booking.get('invoice_name', '-')}",
            f"Cégnév: {booking.get('invoice_company', '-')}",
            f"Cím: {booking.get('invoice_address', '-')}",
            f"Irányítószám: {booking.get('invoice_zip', '-')}",
            f"Város: {booking.get('invoice_city', '-')}",
            f"Ország: {booking.get('invoice_country', '-')}",
            f"Állam/megye: {booking.get('invoice_state', '-')}",
        ]

        # Add any customer notes / special requirements to the admin notification
        admin_extra_lines: List[str] = []
        customer_note_val = (booking.get('customer_notes') or '').strip()
        special_req_val = (booking.get('special_requirements') or '').strip()
        if customer_note_val:
            admin_extra_lines.extend(["", "Megjegyzés:", customer_note_val])
        if special_req_val and special_req_val != customer_note_val:
            admin_extra_lines.extend(["", "Különleges igények:", special_req_val])

        admin_msg = self._build_message(
            subject=f"Új foglalás érkezett – {tour_title}",
            body="\n".join([
                "Új foglalás adatai:",
                "",
                *base_lines,
                *invoice_lines,
                *admin_extra_lines,
            ]),
            recipients=[self._config.contact_recipient],
        )
        self._send(admin_msg)

    def send_booking_cancellation(
        self,
        booking: Mapping[str, object],
        tour: Optional[Mapping[str, object]] = None,
        cancel_reason: Optional[str] = None,
        notify_customer: bool = True,
    ) -> None:
        """Send a cancellation notification.

        Uses a simple plain-text body similar to the confirmation template but
        clearly states the booking was cancelled and includes the admin-provided
        reason if present.
        """
        tour_title = (tour or {}).get("title") or booking.get("tour_title") or "Ismeretlen túra"
        tour_date = (tour or {}).get("date") or booking.get("tour_date")
        tour_time = (tour or {}).get("time") or booking.get("tour_time")
        order_ref = booking.get("order_ref") or "n/a"

        plain_lines: List[str] = [
            f"Kedves {booking.get('customer_name', 'Vendég')}",
            "",
            f"Sajnálattal értesítünk, hogy a következő foglalásodat lemondtuk:",
            f"Túra: {tour_title}",
            f"Időpont: {tour_date or '-'} {tour_time or ''}",
            f"Foglalási azonosító: {order_ref}",
            "",
        ]

        if cancel_reason:
            plain_lines.extend(["Lemondás oka:", cancel_reason, ""])

        plain_lines.extend([
            "Ha kérdésed van, kérlek válaszolj erre az emailre vagy vedd fel velünk a kapcsolatot:",
            f"{self._config.contact_recipient}",
        ])

        plain_body = "\n".join(plain_lines)

        # HTML body similar style to confirmation but clearly a cancellation
        guest_name = _html.escape(str(booking.get('customer_name') or '').strip()) or 'Vendég'
        booking_id = _html.escape(str(order_ref))
        date_val = _html.escape(str(tour_date or '-'))
        time_val = _html.escape(str(tour_time or ''))
        service_name = _html.escape(str((tour or {}).get('title') or booking.get('tour_title') or tour_title or 'Túra'))
        html_body = ""
        cancel_reason_html = _html.escape(str(cancel_reason or ''))
        # Use configured base URL for logo to ensure it works in emails
        logo_url = f"{self._config.base_url}/static/logo.svg"

        # Build optional reason block separately to avoid backslashes inside
        # an f-string expression (Python disallows backslashes in f-string
        # expression parts). We create this small HTML fragment and then
        # inject it into the larger template.
        if cancel_reason_html:
                reason_block = (
                        '<div style="padding:0 28px 16px;"><strong>Lemondás oka:</strong>'
                        f'<p style="margin:6px 0;">{cancel_reason_html}</p></div>'
                )
        else:
                reason_block = ""

        html_body = f"""<!doctype html>
<html lang=\"hu\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Foglalás lemondva</title></head>
<body style=\"margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;\">
<span style=\"display:none;visibility:hidden;mso-hide:all;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;\">A túrafoglalásodat lemondtuk – a részletek alább olvashatók.</span>
<div style=\"width:100%;background:#f4f6f8;padding:24px 12px;\">
<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"max-width:680px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 6px 18px rgba(13,26,38,0.08);\">
<tr><td>
<div style=\"padding:20px 28px;display:flex;align-items:center;gap:12px;\">
    <img src=\"{logo_url}\" alt=\"Demecs Kenu Vízitúra\" style=\"width:56px;height:56px;border-radius:10px;object-fit:contain;\">
    <div>
        <div style=\"font-size:18px;font-weight:700;color:#0b1220;\">Demecs Kenu Vízitúra</div>
        <div style=\"font-size:13px;color:#6b7280;\">Foglalás lemondva</div>
    </div>
</div>
<div style=\"padding:22px 28px 8px 28px;\">
    <div style=\"font-size:20px;font-weight:700;margin:6px 0 8px;color:#0b1220;\">Kedves {guest_name}, foglalásod törlésre került.</div>
    <p style=\"font-size:15px;color:#374151;margin:0 0 16px;\">Az alábbi részleteket rögzítettük. Ha kérdésed van, válaszolj erre az üzenetre.</p>

    <div style=\"background:#fef2f2;border-radius:10px;padding:14px;margin-bottom:16px;border:1px solid #fecaca;\">
        <table role=\"presentation\" width=\"100%\" style=\"border-collapse:collapse;\">
            <tr><td style=\"color:#6b7280;width:40%;font-weight:600;padding:6px 8px;\">Foglalás azonosító</td><td style=\"padding:6px 8px;color:#111827;\">{booking_id}</td></tr>
            <tr><td style=\"color:#6b7280;width:40%;font-weight:600;padding:6px 8px;\">Dátum</td><td style=\"padding:6px 8px;color:#111827;\">{date_val} — {time_val}</td></tr>
            <tr><td style=\"color:#6b7280;width:40%;font-weight:600;padding:6px 8px;\">Túra</td><td style=\"padding:6px 8px;color:#111827;\">{service_name}</td></tr>
        </table>
    </div>

    {reason_block}

    <p style=\"font-size:14px;color:#374151;margin:0 0 16px;\">Bármilyen kérdés esetén írj nekünk: <a href=\"mailto:{self._config.contact_recipient}\">{self._config.contact_recipient}</a>.</p>
</div>

<div style=\"font-size:13px;color:#6b7280;padding:18px 28px 28px;\"><div style=\"margin-bottom:8px;\">Demecs Kenu Vízitúra<br>Magyarország</div><div>© 2025 Demecs Kenu Vízitúra. Minden jog fenntartva.</div></div>

</td></tr></table></div></body></html>"""

        # send to customer
        customer_email = (booking.get("customer_email") or "").strip()
        if notify_customer:
            if not customer_email:
                raise EmailServiceError("Cannot notify customer: email address is missing.")

            try:
                customer_msg = EmailMessage()
                customer_msg["Subject"] = f"Foglalás lemondva – {tour_title}"
                customer_msg["From"] = self._config.sender
                customer_msg["To"] = customer_email
                customer_msg.set_content(plain_body)
                customer_msg.add_alternative(html_body, subtype="html")
                self._send(customer_msg)
            except Exception as exc:  # pragma: no cover - network
                raise EmailServiceError(f"Failed to send cancellation email to customer: {exc}") from exc

        # notify admin inbox (plain text)
        admin_extra_notice: List[str] = []
        if not notify_customer:
            admin_extra_notice.extend([
                "",
                "Megjegyzés: A vendég nem kapott értesítő e-mailt (lezajlott túra).",
            ])

        admin_msg = self._build_message(
            subject=f"Foglalás lemondva – {tour_title}",
            body="\n".join([
                "A következő foglalást az admin lemondta:",
                "",
                *plain_lines,
                *admin_extra_notice,
            ]),
            recipients=[self._config.contact_recipient],
        )
        self._send(admin_msg)


_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    global _email_service
    if _email_service is None:
        _email_service = EmailService.from_env()
    return _email_service
