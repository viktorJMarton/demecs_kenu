import functools
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash
from flaskr.db import get_db

bp = Blueprint('auth', __name__, url_prefix='/auth')

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
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
    else:
        user = get_db().execute(
            'SELECT * FROM admins WHERE id = ?', (user_id,)
        ).fetchone()
        
        if user:
            g.user = dict(user)
            g.user['is_admin'] = True
        else:
            session.clear()
            g.user = None

@bp.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        error = None
        user = db.execute(
            'SELECT * FROM admins WHERE username = ?', (username,)
        ).fetchone()

        if user is None:
            error = 'Hibás felhasználónév vagy jelszó.'
        elif not check_password_hash(user['password_hash'], password):
            error = 'Hibás felhasználónév vagy jelszó.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
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
        db = get_db()
        error = None

        if not check_password_hash(g.user['password_hash'], current_password):
            error = 'Hibás jelenlegi jelszó.'
        elif new_password != confirm_password:
            error = 'Az új jelszavak nem egyeznek.'
        elif len(new_password) < 6:
            error = 'A jelszónak legalább 6 karakter hosszúnak kell lennie.'

        if error is None:
            db.execute(
                'UPDATE admins SET password_hash = ? WHERE id = ?',
                (generate_password_hash(new_password), g.user['id'])
            )
            db.commit()
            flash('Jelszó sikeresen megváltoztatva!', 'success')
            return redirect(url_for('auth.profile'))

        flash(error, 'error')

    return render_template('auth/change_password.html')
