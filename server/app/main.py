import asyncio
import contextlib
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings
from app.db import async_session_factory
from app.errors import ApiError
from app.routers import auth, cases, health, rules, sentences
from app.services.csrf import CSRF_HEADER_NAME, CSRF_HEADER_VALUE, requires_csrf_check
from app.services.llm_provider import get_llm_provider
from app.services.rule_catalog import RuleCatalog
from app.services.worker import run_worker_loop

logger = logging.getLogger(__name__)

settings = get_settings()
settings.validate_for_production()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rule_catalog = RuleCatalog.load(settings.rules_path)

    # 정석은 워커를 별도 프로세스(app/worker_main.py)로 띄우는 것이다. 이 폴백은 그게
    # 불가능한 환경(예: 무료 플랜 등 추가 프로세스를 둘 수 없는 배포 환경)을 위한 것이며,
    # API 프로세스와 부하·장애가 뒤섞이고 워커가 죽어도 API가 알아채지 못하는 한계가 있다.
    worker_task: asyncio.Task | None = None
    if settings.run_worker_in_app:
        provider = get_llm_provider(settings.llm_provider)
        worker_id = f"inapp-worker-{uuid.uuid4()}"
        logger.info("RUN_WORKER_IN_APP=true: starting in-process worker loop (%s)", worker_id)
        worker_task = asyncio.create_task(
            run_worker_loop(async_session_factory, provider, app.state.rule_catalog, worker_id)
        )

    yield

    if worker_task is not None:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task


app = FastAPI(title="Code Court API", lifespan=lifespan)

if settings.cors_allowed_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origin_list,
        allow_credentials=True,  # 쿠키 기반 인증이라 필요
        allow_methods=["*"],
        allow_headers=["*"],
    )


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
app.include_router(sentences.router, prefix="/api/v1")
