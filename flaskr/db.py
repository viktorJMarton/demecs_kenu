import sqlite3
import click
import os
from flask import current_app, g

def get_db():
    """Adatbázis kapcsolat lekérése"""
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config.get('DATABASE', 'kajak_kenu.db'),
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
        
        # Automatikusan inicializáljuk az adatbázist, ha még nincs
        try:
            g.db.execute('SELECT 1 FROM tours LIMIT 1')
        except sqlite3.OperationalError:
            # Táblák nem léteznek, inicializáljuk
            init_db()
    
    return g.db

def close_db(e=None):
    """Adatbázis kapcsolat bezárása"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Adatbázis inicializálása a schema.sql fájlból"""
    db = get_db()
    schema_path = os.path.join(current_app.root_path, 'schema.sql')
    with open(schema_path, 'r', encoding='utf8') as f:
        db.executescript(f.read())

@click.command('init-db')
def init_db_command():
    """CLI parancs az adatbázis inicializálásához"""
    init_db()
    click.echo('Adatbázis inicializálva.')

def init_app(app):
    """App inicializálás - teardown és CLI parancsok regisztrálása"""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)