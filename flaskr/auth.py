import json
import os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

bp = Blueprint('auth', __name__, url_prefix='/auth')

def _load_admin_users():
    """Load admin credentials from environment variables."""
    users = {}
    raw_json = os.getenv('ADMIN_USERS_JSON')
    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError('ADMIN_USERS_JSON must be valid JSON.') from exc

        if isinstance(parsed, dict):
            parsed = [{'username': key, 'password': value} for key, value in parsed.items()]
        elif not isinstance(parsed, list):
            raise RuntimeError('ADMIN_USERS_JSON must be a list of user objects or username/password pairs.')

        for entry in parsed:
            if not isinstance(entry, dict):
                raise RuntimeError('Each entry in ADMIN_USERS_JSON must be an object with username/password fields.')
            username = entry.get('username')
            password_hash = entry.get('password_hash')
            password = entry.get('password')
            if not username:
                continue
            if password_hash:
                users[username] = password_hash
            elif password:
                users[username] = generate_password_hash(password)

    env_username = os.getenv('ADMIN_USERNAME')
    if env_username:
        password_hash = os.getenv('ADMIN_PASSWORD_HASH')
        password = os.getenv('ADMIN_PASSWORD')
        if password_hash:
            users[env_username] = password_hash
        elif password:
            users[env_username] = generate_password_hash(password)

    if not users:
        raise RuntimeError(
            'No admin users configured. Set ADMIN_USERS_JSON or ADMIN_USERNAME/ADMIN_PASSWORD in the environment.'
        )

    return users


# Admin felhasználók környezeti változókból betöltve
ADMIN_USERS = _load_admin_users()

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
            return redirect(url_for('admin_dashboard.dashboard'))

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