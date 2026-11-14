import sqlite3
import click
import os
from flask import current_app, g

from .affiliate_migration import migrate_affiliate_schema

def get_db():
    """Adatbázis kapcsolat lekérése"""
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config.get('DATABASE', 'kajak_kenu.db'),
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
        # SQLite does not enforce declared foreign keys unless enabled on each
        # connection. Affiliate financial and idempotency guarantees depend on it.
        g.db.execute('PRAGMA foreign_keys = ON')
        g.db.execute('PRAGMA busy_timeout = 5000')
        
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
    migrate_affiliate_schema(db)

@click.command('init-db')
def init_db_command():
    """CLI parancs az adatbázis inicializálásához"""
    init_db()
    click.echo('Adatbázis inicializálva.')


@click.command('migrate-affiliate-db')
def migrate_affiliate_db_command():
    """Add or verify the idempotent affiliate data foundation."""
    migrate_affiliate_schema(get_db())
    click.echo('Affiliate adatbázis-migráció kész.')

def init_app(app):
    """App inicializálás - teardown és CLI parancsok regisztrálása"""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(migrate_affiliate_db_command)
