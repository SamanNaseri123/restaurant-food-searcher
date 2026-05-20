"""Database bootstrap — ensures PostgreSQL extensions and triggers exist.

The local Docker image runs `init.sql` once on first volume creation, but a
hosted database (Railway, Render, etc.) gets a fresh empty database. This module
makes the app self-sufficient: it creates the required extensions and the
menu search-vector trigger on every startup (all operations are idempotent).
"""
import logging

from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

# Required PostgreSQL extensions. Order matters: postgis must exist before
# create_all() because the `restaurants` table has a Geometry column.
_EXTENSIONS = ("postgis", "pg_trgm", "uuid-ossp")

# Trigger function that populates menu_items.search_vector on insert/update.
# Weights: name='A' (highest), description='B', category='C'.
_TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION menu_items_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.description, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.category, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_DROP_TRIGGER_SQL = (
    "DROP TRIGGER IF EXISTS menu_items_search_vector_trigger ON menu_items"
)

_CREATE_TRIGGER_SQL = """
CREATE TRIGGER menu_items_search_vector_trigger
    BEFORE INSERT OR UPDATE ON menu_items
    FOR EACH ROW EXECUTE FUNCTION menu_items_search_vector_update()
"""


async def ensure_extensions(conn: AsyncConnection) -> None:
    """Create required PostgreSQL extensions. Run BEFORE Base.metadata.create_all()."""
    for ext in _EXTENSIONS:
        await conn.exec_driver_sql(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')
    logger.info(f"Ensured extensions: {', '.join(_EXTENSIONS)}")


async def ensure_search_trigger(conn: AsyncConnection) -> None:
    """Create the menu_items search-vector trigger. Run AFTER create_all()
    (the menu_items table must already exist)."""
    await conn.exec_driver_sql(_TRIGGER_FUNCTION_SQL)
    await conn.exec_driver_sql(_DROP_TRIGGER_SQL)
    await conn.exec_driver_sql(_CREATE_TRIGGER_SQL)
    logger.info("Ensured menu_items search-vector trigger")
