-- Tisztítás: dobjuk a meglévő táblákat teljes újrainicializáláshoz
DROP TABLE IF EXISTS tour_images;
DROP TABLE IF EXISTS payment_transactions;
DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS tours;
DROP TABLE IF EXISTS tour_locations;
DROP TABLE IF EXISTS page_sections;

-- Adatbázis séma a túrák és foglalások kezeléséhez

CREATE TABLE IF NOT EXISTS tour_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    latitude REAL,
    longitude REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Helyszínekhez tartozó képek táblája
CREATE TABLE IF NOT EXISTS location_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    alt_text TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (location_id) REFERENCES tour_locations (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_location_images_location_id ON location_images(location_id);



CREATE TABLE IF NOT EXISTS tours (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    date DATE NOT NULL,
    time TIME NOT NULL,
    duration INTEGER, -- perc
    max_participants INTEGER DEFAULT 15,
    price INTEGER NOT NULL, -- Ft
    difficulty TEXT CHECK(difficulty IN ('Kezdő', 'Haladó')),
    location TEXT,
    tour_location_id INTEGER,
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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tour_location_id) REFERENCES tour_locations (id)
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tour_id INTEGER NOT NULL,
    order_ref TEXT UNIQUE NOT NULL,
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    customer_phone TEXT,
    participants_count INTEGER DEFAULT 1,
    lifejacket_sizes TEXT,
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
    invoice_name TEXT NOT NULL DEFAULT '',
    invoice_country TEXT NOT NULL DEFAULT 'hu',
    invoice_city TEXT NOT NULL DEFAULT '',
    invoice_zip TEXT NOT NULL DEFAULT '',
    invoice_address TEXT NOT NULL DEFAULT '',
    invoice_company TEXT,
    invoice_state TEXT,
    tour_latitude REAL,
    tour_longitude REAL,
    FOREIGN KEY (tour_id) REFERENCES tours (id)
);

-- SimplePay tranzakciók táblája
CREATE TABLE IF NOT EXISTS payment_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    order_ref TEXT UNIQUE NOT NULL,
    transaction_id TEXT,
    status TEXT CHECK(status IN ('init', 'pending', 'success', 'fail', 'timeout', 'cancelled', 'refund_pending', 'refunded')) DEFAULT 'init',
    amount INTEGER NOT NULL,
    currency TEXT DEFAULT 'HUF',
    payment_method TEXT DEFAULT 'simplepay',
    request_data TEXT, -- JSON
    response_data TEXT, -- JSON
    error_message TEXT,
    simplepay_payment_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (booking_id) REFERENCES bookings (id)
);

-- Képek táblája (már létezik, de ha nem, akkor ezt is hozzá kell adni)
CREATE TABLE IF NOT EXISTS tour_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tour_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    alt_text TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tour_id) REFERENCES tours (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS page_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index-ek a gyorsabb kereséshez
CREATE INDEX IF NOT EXISTS idx_tours_date ON tours(date);
CREATE INDEX IF NOT EXISTS idx_tours_active ON tours(is_active);
CREATE INDEX IF NOT EXISTS idx_bookings_tour_id ON bookings(tour_id);
CREATE INDEX IF NOT EXISTS idx_bookings_order_ref ON bookings(order_ref);
CREATE INDEX IF NOT EXISTS idx_bookings_payment_status ON bookings(payment_status);
CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(booking_date);
CREATE INDEX IF NOT EXISTS idx_payment_transactions_booking_id ON payment_transactions(booking_id);
CREATE INDEX IF NOT EXISTS idx_payment_transactions_order_ref ON payment_transactions(order_ref);
CREATE INDEX IF NOT EXISTS idx_payment_transactions_status ON payment_transactions(status);
CREATE INDEX IF NOT EXISTS idx_tour_images_tour_id ON tour_images(tour_id);
CREATE INDEX IF NOT EXISTS idx_tour_locations_name ON tour_locations(name);

-- Minta adatok beszúrása
INSERT OR IGNORE INTO tour_locations (id, name, description, latitude, longitude) VALUES
(1, 'Tisza-tó, Tiszafüred', 'Nyugodt indulópont árnyas öblökkel és sekély parttal.', 47.6150, 20.6710),
(2, 'Duna, Szentendre', 'Hangulatos kisváros romantikus rakparttal és szigetkerülő körrel.', 47.6680, 19.0750),
(3, 'Tisza-tó, Abádszalók', 'Homokos part, ahol a naplemente evezés alatt is mesés.', 47.4875, 20.5930);

INSERT OR IGNORE INTO page_sections (slug, label, content) VALUES
('hero', 'Hero szekció', '{"headline": "Hello There", "subheadline": "Provident cupiditate voluptatem et in. Quaerat fugiat ut assumenda excepturi exercitationem quasi.", "cta_label": "Túranaptár megnyitása", "cta_target": "modal:my_modal_7", "video_url": "/static/hero-bg.mp4"}'),
('faq', 'Gyakran Ismételt Kérdések', '{"items": [{"question": "Hogyan tudok foglalni?", "answer": "Válassz egy túrát az oldalon, töltsd ki az űrlapot, és erősítsd meg a foglalást."}, {"question": "Milyen felszerelést biztosítotok?", "answer": "Minden túrán biztosítjuk a kajakot, evezőt, mentőmellényt és a szükséges kiegészítőket."}, {"question": "Lehet-e lemondani a túrát?", "answer": "A túra előtt legalább 48 órával díjmentesen lemondhatod vagy átfoglalhatod az időpontot."}]}');

INSERT OR IGNORE INTO tours (id, title, description, date, time, duration, max_participants, price, difficulty, location, distance, meeting_point) VALUES
(1, 'Tisza-tavi Kaland', 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maemper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. emper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. emper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. emper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. emper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. emper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. emper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. emper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. emper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. emper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. ecenas ligula massa, varius a, semper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper conguLorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper congue, euismod non, mi. Proin porttitor, orci nec nonummy molestie, enim est eleifend mi, non fermentum diam nisl sit amet erat. Duis semper. Duis arcu massa, scelerisque vitae, consequat in, pretium a, enim. Pellentesque congue. Ut in risus volutpat libero pharetra tempor. Cras vestibulum bibendum augue. Praesent egestas leo in pede. Praesent blandit odio eu enim. Pellentesque sed dui ut augue blandit sodales. Vestibulum ante ipsum primis in faucibus orci luctus et ultrices posuere cubilia Curae; Aliquam nibh. Mauris ac mauris sed pede pellentesque fermentum. Maecenas adipiscing ante non diam sodales hendrerit. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper congue, euismod non, mi. Proin porttitor, orci nec nonummy molestie, enim est eleifend mi, non fermentum diam nisl sit amet erat. Duis semper. Duis arcu massa, scelerisque vitae, consequat in, pretium a, enim. Pellentesque congue. Ut in risus volutpat libero pharetra tempor. Cras vestibulum bibendum augue. Praesent egestas leo in pede. Praesent blandit odio eu enim. Pellentesque sed dui ut augue blandit sodales. Vestibulu Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed non risus. Suspendisse lectus tortor, dignissim sit amet, adipiscing nec, ultricies sed, dolor. Cras elementum ultrices diam. Maecenas ligula massa, varius a, semper congue, euismod non, mi. Proin porttitor, orci nec nonummy molestie, enim est eleifend mi, non fermentum diam nisl sit amet erat. Duis semper. Duis arcu massa, scelerisque vitae, consequat in, pretium a, enim. Pellentesque congue. Ut in risus volutpat libero pharetra tempor. Cras vestibulum bibendum augue. Praesent egestas leo in pede. Praesent blandit odio eu enim. Pellentesque sed dui ut augue blandit sodales. Vestibulu', '2025-10-15', '09:00', 180, 15, 8500, 'Kezdő', 'Tisza-tó, Tiszafüred', 12.5, 'Tiszafüred, Fürdő utca parkoló'),
(2, 'Duna-menti Felfedező', 'Izgalmas túra a Duna mentén, vadregényes tájak felfedezésével.', '2025-10-18', '10:30', 240, 12, 12000, 'Haladó', 'Duna, Szentendre', 18.0, 'Szentendre, Duna-part'),
(3, 'Éjszakai Evezés', 'Különleges esti túra csillagos ég alatt, romantikus hangulatban.', '2025-10-20', '19:00', 120, 8, 15000, 'Kezdő', 'Tisza-tó, Abádszalók', 8.0, 'Abádszalók, strand parkoló');

-- Minta foglalások
INSERT OR IGNORE INTO bookings (
    tour_id,
    order_ref,
    customer_name,
    customer_email,
    customer_phone,
    participants_count,
    lifejacket_sizes,
    total_price,
    payment_status
) VALUES
(1, 'ORDER-ABC123-1728123456', 'Kovács János', 'kovacs.janos@email.com', '+36301234567', 2, '["50-70 kg", "70-90 kg"]', 17000, 'paid'),
(2, 'ORDER-DEF456-1728234567', 'Nagy Mária', 'nagy.maria@email.com', '+36309876543', 1, '["30-50 kg"]', 12000, 'pending'),
(1, 'ORDER-GHI789-1728345678', 'Szabó Péter', 'szabo.peter@email.com', '+36307654321', 3, '["20-30 kg", "30-50 kg", "50-70 kg"]', 25500, 'paid');
