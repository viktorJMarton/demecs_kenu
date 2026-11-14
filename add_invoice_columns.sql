-- Adds persistent storage for invoice data captured during bookings
ALTER TABLE bookings ADD COLUMN invoice_name TEXT NOT NULL DEFAULT '';
ALTER TABLE bookings ADD COLUMN invoice_country TEXT NOT NULL DEFAULT 'hu';
ALTER TABLE bookings ADD COLUMN invoice_city TEXT NOT NULL DEFAULT '';
ALTER TABLE bookings ADD COLUMN invoice_zip TEXT NOT NULL DEFAULT '';
ALTER TABLE bookings ADD COLUMN invoice_address TEXT NOT NULL DEFAULT '';
ALTER TABLE bookings ADD COLUMN invoice_company TEXT;
ALTER TABLE bookings ADD COLUMN invoice_state TEXT;
