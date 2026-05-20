from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, discover, favorites, search, subscriptions
from app.core.config import settings
from app.core.database import Base, engine
from app.core.db_bootstrap import ensure_extensions, ensure_search_trigger
# Import models so SQLAlchemy registers them with Base.metadata
from app.models import favorite as _favorite_models  # noqa: F401
from app.models import user as _user_models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        # Extensions first — postgis must exist before create_all (Geometry column)
        await ensure_extensions(conn)
        await conn.run_sync(Base.metadata.create_all)
        # Trigger last — needs the menu_items table to exist
        await ensure_search_trigger(conn)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(subscriptions.router)
app.include_router(favorites.router)
app.include_router(search.router)
app.include_router(discover.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
