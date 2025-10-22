from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from .db import get_db

bp = Blueprint('auth', __name__, url_prefix='/auth')

# Egyszerű admin felhasználók (később DB-ből)
ADMIN_USERS = {
    'admin': generate_password_hash('admin123'),  # admin / admin123
    'kajak_admin': generate_password_hash('kajak2025'),  # kajak_admin / kajak2025
}

def login_required(f):
    """Decorator a bejelentkezés ellenőrzéséhez"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.user:
            flash('A funkció használatához be kell jelentkezned!', 'error')
            # Az eredeti URL mentése, hogy visszatérhessünk
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@bp.before_app_request
def load_logged_in_user():
    """Minden kérés előtt ellenőrzi a bejelentkezést"""
    user_id = session.get('user_id')
    
    if user_id is None:
        g.user = None
    else:
        # Ellenőrizzük, hogy létezik-e még a felhasználó
        if user_id in ADMIN_USERS:
            g.user = {'username': user_id, 'is_admin': True}
        else:
            # Ha nem létezik, törljük a sessiont
            session.clear()
            g.user = None

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Admin bejelentkezés"""
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        error = None

        if not username:
            error = 'Felhasználónév megadása kötelező.'
        elif not password:
            error = 'Jelszó megadása kötelező.'
        elif username not in ADMIN_USERS:
            error = 'Hibás felhasználónév vagy jelszó.'
        elif not check_password_hash(ADMIN_USERS[username], password):
            error = 'Hibás felhasználónév vagy jelszó.'

        if error is None:
            # Sikeres bejelentkezés
            session.clear()
            session['user_id'] = username
            session.permanent = True  # Session megmarad böngésző bezárás után is
            
            flash(f'Üdvözöllek, {username}!', 'success')
            
            # Visszairányítás az eredeti oldalra vagy admin dashboard-ra
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/admin'):
                return redirect(next_page)
            return redirect(url_for('admin.dashboard'))

        flash(error, 'error')

    return render_template('auth/login.html')

@bp.route('/logout')
def logout():
    """Kijelentkezés"""
    username = session.get('user_id', 'Felhasználó')
    session.clear()
    flash(f'Sikeresen kijelentkeztél, {username}!', 'success')
    return redirect(url_for('index'))

@bp.route('/profile')
@login_required
def profile():
    """Admin profil oldal"""
    return render_template('auth/profile.html')

# Jelszó változtatás (opcionális)
@bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Jelszó változtatás"""
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        username = g.user['username']
        error = None
        
        if not check_password_hash(ADMIN_USERS[username], current_password):
            error = 'Hibás jelenlegi jelszó.'
        elif len(new_password) < 6:
            error = 'Az új jelszónak legalább 6 karakter hosszúnak kell lennie.'
        elif new_password != confirm_password:
            error = 'Az új jelszavak nem egyeznek.'
        
        if error is None:
            # Jelszó frissítése (memóriában, későbben DB-ben)
            ADMIN_USERS[username] = generate_password_hash(new_password)
            flash('Jelszó sikeresen megváltoztatva!', 'success')
            return redirect(url_for('auth.profile'))
        
        flash(error, 'error')
    
    return render_template('auth/change_password.html')