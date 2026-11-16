import sqlite3
import click
import os
from flask import current_app, g
from flask.cli import with_appcontext

from .affiliate_migration import migrate_affiliate_schema
from .affiliate_retention import (
    MAX_RETENTION_BATCH_SIZE,
    aggregate_expired_affiliate_clicks,
)
from .affiliate_usage import MAX_CLEANUP_BATCH_SIZE, cleanup_expired_affiliate_usages

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


@click.command('cleanup-affiliate-usages')
@click.option(
    '--batch-size',
    type=click.IntRange(min=1, max=MAX_CLEANUP_BATCH_SIZE),
    default=100,
    show_default=True,
    help='Maximum number of expired pending usages released in one transaction.',
)
@with_appcontext
def cleanup_affiliate_usages_command(batch_size):
    """Release one bounded batch of expired affiliate reservations."""
    result = cleanup_expired_affiliate_usages(get_db(), batch_size=batch_size)
    click.echo(
        "Affiliate usage cleanup complete: "
        f"released={result.released_count}, has_more={'yes' if result.has_more else 'no'}"
    )


@click.command('aggregate-affiliate-clicks')
@click.option(
    '--batch-size',
    type=click.IntRange(min=1, max=MAX_RETENTION_BATCH_SIZE),
    default=250,
    show_default=True,
    help='Maximum number of expired detail rows aggregated atomically.',
)
@with_appcontext
def aggregate_affiliate_clicks_command(batch_size):
    """Replace expired click details with anonymous monthly rollups."""
    result = aggregate_expired_affiliate_clicks(
        get_db(), batch_size=batch_size
    )
    click.echo(
        "Affiliate click aggregation complete: "
        f"months={len(result.aggregated_months)}, "
        f"deleted={result.deleted_detail_rows}, "
        f"has_more={'yes' if result.has_more else 'no'}"
    )

def init_app(app):
    """App inicializálás - teardown és CLI parancsok regisztrálása"""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(migrate_affiliate_db_command)
    app.cli.add_command(cleanup_affiliate_usages_command)
    app.cli.add_command(aggregate_affiliate_clicks_command)
