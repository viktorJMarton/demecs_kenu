import functools
import json
import os
import re
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app
)
from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint('auth', __name__, url_prefix='/auth')

def get_env_file_path():
    """Get the path to the .env file"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')

def get_admin_users():
    """Load admin users from .env file (preferred) or environment variable"""
    # Try reading from file first to get latest changes without restart
    env_path = get_env_file_path()
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('ADMIN_USERS_JSON='):
                        # Extract JSON part
                        admin_json = line.strip().split('=', 1)[1]
                        return json.loads(admin_json)
        except Exception as e:
            current_app.logger.warning(f"Failed to read ADMIN_USERS_JSON from .env file: {e}")

    # Fallback to environment variable
    admin_json = os.getenv('ADMIN_USERS_JSON', '[]')
    try:
        return json.loads(admin_json)
    except json.JSONDecodeError:
        current_app.logger.error("Failed to parse ADMIN_USERS_JSON")
        return []

def find_user_by_username(username):
    """Find admin user by username"""
    users = get_admin_users()
    for user in users:
        if user.get('username') == username:
            return user
    return None

def update_admin_password(username, new_password_hash):
    """Update admin password in .env file"""
    env_path = get_env_file_path()
    
    # Read current .env file
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            env_content = f.read()
    except FileNotFoundError:
        current_app.logger.error(".env file not found")
        return False
    
    # Parse current ADMIN_USERS_JSON
    users = get_admin_users()
    
    # Update the password hash for the user
    updated = False
    for user in users:
        if user.get('username') == username:
            user['password_hash'] = new_password_hash
            updated = True
            break
    
    if not updated:
        return False
    
    # Serialize updated users back to JSON
    new_admin_json = json.dumps(users, ensure_ascii=False)
    
    # Replace ADMIN_USERS_JSON line in .env file
    # Match the line starting with ADMIN_USERS_JSON=
    pattern = r'^ADMIN_USERS_JSON=.*$'
    replacement = f'ADMIN_USERS_JSON={new_admin_json}'
    
    new_content = re.sub(pattern, replacement, env_content, flags=re.MULTILINE)
    
    # Write back to .env file
    try:
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        # Update the environment variable in the current process
        os.environ['ADMIN_USERS_JSON'] = new_admin_json
        
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to update .env file: {e}")
        return False

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash('A funkció használatához be kell jelentkezned!', 'error')
            return redirect(url_for('auth.login', next=request.url))

        return view(**kwargs)

    return wrapped_view

@bp.before_app_request
def load_logged_in_user():
    username = session.get('username')

    if username is None:
        g.user = None
    else:
        user = find_user_by_username(username)
        
        if user:
            g.user = {
                'username': user['username'],
                'password_hash': user['password_hash'],
                'is_admin': True
            }
        else:
            session.clear()
            g.user = None

@bp.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        error = None
        
        user = find_user_by_username(username)

        if user is None:
            error = 'Hibás felhasználónév vagy jelszó.'
        elif not check_password_hash(user['password_hash'], password):
            error = 'Hibás felhasználónév vagy jelszó.'

        if error is None:
            session.clear()
            session['username'] = username
            session.permanent = True
            flash(f'Üdvözöllek, {username}!', 'success')
            
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/admin'):
                return redirect(next_page)
            return redirect(url_for('admin_dashboard.dashboard'))

        flash(error, 'error')

    return render_template('auth/login.html')

@bp.route('/logout')
def logout():
    username = g.user['username'] if g.user else 'Felhasználó'
    session.clear()
    flash(f'Sikeresen kijelentkeztél, {username}!', 'success')
    return redirect(url_for('index'))

@bp.route('/profile')
@login_required
def profile():
    """Admin profil oldal"""
    return render_template('auth/profile.html')

@bp.route('/change-password', methods=('GET', 'POST'))
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        error = None

        if not check_password_hash(g.user['password_hash'], current_password):
            error = 'Hibás jelenlegi jelszó.'
        elif new_password != confirm_password:
            error = 'Az új jelszavak nem egyeznek.'
        elif len(new_password) < 6:
            error = 'A jelszónak legalább 6 karakter hosszúnak kell lennie.'

        if error is None:
            new_password_hash = generate_password_hash(new_password)
            
            # Update password in .env file
            if update_admin_password(g.user['username'], new_password_hash):
                # Update current session user object
                g.user['password_hash'] = new_password_hash
                flash('Jelszó sikeresen megváltoztatva! A változtatás a következő újraindításkor lép érvénybe.', 'success')
                return redirect(url_for('auth.profile'))
            else:
                error = 'Hiba történt a jelszó mentése során. Ellenőrizd a .env fájl írási jogosultságait.'

        flash(error, 'error')

    return render_template('auth/change_password.html')
