"""CSV and plain-text views of the stored settlement snapshots."""

import csv
from io import StringIO
from unicodedata import normalize

from werkzeug.utils import secure_filename


_COLUMNS = (
    ("Foglalásazonosító", "booking_id", None),
    ("Eredeti ár (Ft)", "original_amount", "original_amount_total"),
    ("Kedvezmény (Ft)", "discount_amount", "discount_amount_total"),
    ("Fizetett összeg (Ft)", "paid_amount", "paid_amount_total"),
    ("Jutalék (Ft)", "commission_amount", "commission_amount_total"),
)


def settlement_export_filename(header, extension):
    partner = secure_filename(header["partner_name_snapshot"])[:70] or f'partner-{header["partner_id"]}'
    return secure_filename(f'{partner}-{header["period_start"]}-{header["period_end"]}-{header["id"]}.{extension}')


def _snapshot_metadata(header):
    return (
        ("Elszámolási azonosító", header["settlement_ref"]),
        ("Partner", header["partner_name_snapshot"]),
        ("Időszak kezdete", str(header["period_start"])),
        ("Időszak vége", str(header["period_end"])),
        ("Számlázási név", header["partner_billing_name_snapshot"] or ""),
        ("Számlázási cím", header["partner_billing_address_snapshot"] or ""),
        ("Adószám", header["partner_tax_number_snapshot"] or ""),
    )


def _single_line(value):
    return " ".join(value.split())


def _csv_text(value):
    value = _single_line(value)
    # Quoting alone does not stop text cells from being read as formulas.
    if normalize("NFKC", value).lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def settlement_csv(header, items):
    out = StringIO(newline="")
    writer = csv.writer(out, delimiter=";")
    writer.writerow(("Sor típusa", "Mező vagy érték", *(label for label, _, _ in _COLUMNS)))
    for label, value in _snapshot_metadata(header):
        writer.writerow(("Adat", label, _csv_text(value), "", "", "", ""))
    for item in items:
        writer.writerow(("Tétel", "", *(item[key] for _, key, _ in _COLUMNS)))
    writer.writerow(("Összesen", "", "", *(header[key] for _, _, key in _COLUMNS[1:])))
    return out.getvalue().encode("utf-8-sig")


def settlement_txt(header, items):
    lines = ["Partnerelszámolás", ""]
    lines.extend(f"{label}: {_single_line(value)}" for label, value in _snapshot_metadata(header))
    lines.extend(("", "Tételek"))
    for item in items:
        lines.append(
            f'#{item["booking_id"]} | ' + " | ".join(
                f"{label}: {item[key]}" for label, key, _ in _COLUMNS[1:]
            )
        )
    lines.extend(("", "Összesen"))
    lines.extend(f"{label}: {header[key]}" for label, _, key in _COLUMNS[1:])
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")
