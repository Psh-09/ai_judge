from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.routers import health, rules
from app.services.rule_catalog import RuleCatalog

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rule_catalog = RuleCatalog.load(settings.rules_path)
    yield


app = FastAPI(title="Code Court API", lifespan=lifespan)

app.include_router(health.router)
app.include_router(rules.router, prefix="/api/v1")
