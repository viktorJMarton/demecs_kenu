-- Adatbázis séma a túrák és foglalások kezeléséhez

CREATE TABLE IF NOT EXISTS tours (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    date DATE NOT NULL,
    time TIME NOT NULL,
    duration INTEGER, -- perc
    max_participants INTEGER DEFAULT 15,
    price INTEGER NOT NULL, -- Ft
    difficulty TEXT CHECK(difficulty IN ('Könnyű', 'Közepes', 'Nehéz')),
    location TEXT,
    distance REAL, -- km
    meeting_point TEXT,
    equipment_included TEXT,
    what_to_bring TEXT,
    cancellation_policy TEXT,
    image_url TEXT,
    tour_latitude REAL,
    tour_longitude REAL,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tour_id INTEGER NOT NULL,
    order_ref TEXT UNIQUE NOT NULL,
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    customer_phone TEXT,
    participants_count INTEGER DEFAULT 1,
    total_price INTEGER NOT NULL,
    payment_status TEXT CHECK(payment_status IN ('pending', 'paid', 'failed', 'cancelled', 'refunded')) DEFAULT 'pending',
    payment_method TEXT,
    transaction_id TEXT,
    customer_notes TEXT,
    special_requirements TEXT,
    emergency_contact TEXT,
    booking_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    payment_date TIMESTAMP,
    cancellation_date TIMESTAMP,
    admin_notes TEXT,
    tour_latitude REAL,
    tour_longitude REAL,
    FOREIGN KEY (tour_id) REFERENCES tours (id)
);

-- Index-ek a gyorsabb kereséshez
CREATE INDEX IF NOT EXISTS idx_tours_date ON tours(date);
CREATE INDEX IF NOT EXISTS idx_tours_active ON tours(is_active);
CREATE INDEX IF NOT EXISTS idx_bookings_tour_id ON bookings(tour_id);
CREATE INDEX IF NOT EXISTS idx_bookings_order_ref ON bookings(order_ref);
CREATE INDEX IF NOT EXISTS idx_bookings_payment_status ON bookings(payment_status);
CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(booking_date);

-- Minta adatok beszúrása
INSERT OR IGNORE INTO tours (id, title, description, date, time, duration, max_participants, price, difficulty, location, distance, meeting_point) VALUES
(1, 'Tisza-tavi Kaland', 'Gyönyörű túra a Tisza-tavon, tökéletes kezdőknek és haladóknak egyaránt.', '2025-10-15', '09:00', 180, 15, 8500, 'Könnyű', 'Tisza-tó, Tiszafüred', 12.5, 'Tiszafüred, Fürdő utca parkoló'),
(2, 'Duna-menti Felfedező', 'Izgalmas túra a Duna mentén, vadregényes tájak felfedezésével.', '2025-10-18', '10:30', 240, 12, 12000, 'Közepes', 'Duna, Szentendre', 18.0, 'Szentendre, Duna-part'),
(3, 'Éjszakai Evezés', 'Különleges esti túra csillagos ég alatt, romantikus hangulatban.', '2025-10-20', '19:00', 120, 8, 15000, 'Könnyű', 'Tisza-tó, Abádszalók', 8.0, 'Abádszalók, strand parkoló');

-- Minta foglalások
INSERT OR IGNORE INTO bookings (tour_id, order_ref, customer_name, customer_email, customer_phone, participants_count, total_price, payment_status) VALUES
(1, 'ORDER-ABC123-1728123456', 'Kovács János', 'kovacs.janos@email.com', '+36301234567', 2, 17000, 'paid'),
(2, 'ORDER-DEF456-1728234567', 'Nagy Mária', 'nagy.maria@email.com', '+36309876543', 1, 12000, 'pending'),
(1, 'ORDER-GHI789-1728345678', 'Szabó Péter', 'szabo.peter@email.com', '+36307654321', 3, 25500, 'paid');