from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.responses import JSONResponse

from app.config import get_settings
from app.errors import ApiError
from app.routers import cases, health, rules
from app.services.rule_catalog import RuleCatalog

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rule_catalog = RuleCatalog.load(settings.rules_path)
    yield


app = FastAPI(title="Code Court API", lifespan=lifespan)


@app.exception_handler(ApiError)
async def handle_api_error(request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


app.include_router(health.router)
app.include_router(rules.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
