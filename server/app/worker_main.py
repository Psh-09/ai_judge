import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.services.llm_provider import get_llm_provider
from app.services.rule_catalog import RuleCatalog
from app.services.worker import run_worker_once

logger = logging.getLogger("worker")

POLL_INTERVAL_SECONDS = 2.0


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    provider = get_llm_provider(settings.llm_provider)
    catalog = RuleCatalog.load(settings.rules_path)
    worker_id = f"worker-{uuid.uuid4()}"

    logger.info("worker started: %s (provider=%s)", worker_id, settings.llm_provider)
    try:
        while True:
            worked = await run_worker_once(session_factory, provider, catalog, worker_id)
            if not worked:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
