import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models import Case, Judgment, Sentence

_NOT_FOUND = ApiError(404, "SENTENCE_NOT_FOUND", "형량 항목을 찾을 수 없습니다.")


async def _load_owned_sentence(
    session: AsyncSession, sentence_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[Sentence, Case]:
    sentence = await session.get(Sentence, sentence_id)
    if sentence is None:
        raise _NOT_FOUND
    judgment = await session.get(Judgment, sentence.judgment_id)
    case = await session.get(Case, judgment.case_id) if judgment is not None else None
    if case is None or case.user_id != user_id:
        # 404 (403 아님) — 사건 상세 조회와 동일하게 존재 여부를 노출하지 않는다.
        raise _NOT_FOUND
    return sentence, case


async def _compute_progress(session: AsyncSession, case_id: uuid.UUID) -> dict:
    # 재심(다른 judgment revision)은 아직 도달 불가능하므로 case의 모든 judgment를 합산한다.
    base = select(Sentence).join(Judgment, Sentence.judgment_id == Judgment.id).where(
        Judgment.case_id == case_id
    )
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    done_stmt = base.where(Sentence.completed_at.is_not(None))
    done = (await session.execute(select(func.count()).select_from(done_stmt.subquery()))).scalar_one()
    return {"done": done, "total": total}


async def toggle_sentence(
    session: AsyncSession, *, sentence_id: uuid.UUID, user_id: uuid.UUID, completed: bool
) -> dict:
    sentence, case = await _load_owned_sentence(session, sentence_id, user_id)
    sentence.completed_at = datetime.now(timezone.utc) if completed else None
    await session.commit()

    progress = await _compute_progress(session, case.id)
    return {"sentence_id": sentence.id, "completed_at": sentence.completed_at, "progress": progress}
