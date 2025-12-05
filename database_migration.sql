-- SQL parancsok az adatbázis frissítéséhez
-- Ezeket a parancsokat kell futtatni az adatbázison

-- Új oszlopok hozzáadása a bookings táblához
ALTER TABLE bookings ADD COLUMN tour_latitude REAL;
ALTER TABLE bookings ADD COLUMN tour_longitude REAL;

-- Új oszlopok hozzáadása a tours táblához
ALTER TABLE tours ADD COLUMN tour_latitude REAL;
ALTER TABLE tours ADD COLUMN tour_longitude REAL;

-- Mit hozzon magával tartalom tárolása
ALTER TABLE tours ADD COLUMN what_to_bring TEXT;

-- Mentőmellény méretek tárolása foglalásoknál
ALTER TABLE bookings ADD COLUMN lifejacket_sizes TEXT;