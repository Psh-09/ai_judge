from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from app.config import get_settings
from app.errors import ApiError
from app.routers import auth, cases, health, rules
from app.services.csrf import CSRF_HEADER_NAME, CSRF_HEADER_VALUE, requires_csrf_check
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


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    if requires_csrf_check(request.method, request.url.path):
        if request.headers.get(CSRF_HEADER_NAME) != CSRF_HEADER_VALUE:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "CSRF_CHECK_FAILED",
                        "message": f"{CSRF_HEADER_NAME} 헤더가 없거나 값이 올바르지 않습니다.",
                        "details": {},
                    }
                },
            )
    return await call_next(request)


app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(rules.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
