# Ez a kód az admin.py fájlban a booking_detail függvénybe kerül
# A booking lekérési query frissítése:

booking = db.execute('''
    SELECT b.*, t.title as tour_title, t.date as tour_date, t.time as tour_time,
           t.location, t.meeting_point, t.duration, t.difficulty
    FROM bookings b
    JOIN tours t ON b.tour_id = t.id
    WHERE b.id = ?
''', (booking_id,)).fetchone()

# Helyette ezt kell használni:

booking = db.execute('''
    SELECT b.*, t.title as tour_title, t.date as tour_date, t.time as tour_time,
           t.location, t.meeting_point, t.duration, t.difficulty
    FROM bookings b
    JOIN tours t ON b.tour_id = t.id
    WHERE b.id = ?
''', (booking_id,)).fetchone()