-- SQL parancsok az adatbázis frissítéséhez
-- Ezeket a parancsokat kell futtatni az adatbázison

-- Új oszlopok hozzáadása a bookings táblához
ALTER TABLE bookings ADD COLUMN tour_latitude REAL;
ALTER TABLE bookings ADD COLUMN tour_longitude REAL;

-- Új oszlopok hozzáadása a tours táblához
ALTER TABLE tours ADD COLUMN tour_latitude REAL;
ALTER TABLE tours ADD COLUMN tour_longitude REAL;