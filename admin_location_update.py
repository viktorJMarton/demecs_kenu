# Ez a kód az admin.py fájlba kerül
# Az update_booking_status függvény után

@bp.route('/bookings/<int:booking_id>/update-location', methods=['POST'])
@login_required
def update_booking_location(booking_id):
    """Foglalás túra helyszín frissítése"""
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    
    db = get_db()
    
    # Koordináták validálása
    try:
        if latitude and longitude:
            lat = float(latitude)
            lng = float(longitude)
            
            # Koordináták ellenőrzése (valid range)
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                flash('Érvénytelen koordináták!', 'error')
                return redirect(url_for('admin.booking_detail', booking_id=booking_id))
        else:
            lat = None
            lng = None
    except ValueError:
        flash('Érvénytelen koordináta formátum!', 'error')
        return redirect(url_for('admin.booking_detail', booking_id=booking_id))
    
    # Koordináták frissítése az adatbázisban
    db.execute('''
        UPDATE bookings 
        SET tour_latitude = ?, tour_longitude = ?
        WHERE id = ?
    ''', (lat, lng, booking_id))
    
    db.commit()
    
    if lat and lng:
        flash('Túra helyszín sikeresen mentve!', 'success')
    else:
        flash('Túra helyszín törölve!', 'info')
    
    return redirect(url_for('admin.booking_detail', booking_id=booking_id))