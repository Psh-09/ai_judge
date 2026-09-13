import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models import Appeal, Case, CaseStatus
from app.services.case_read import case_progress_dict

MIN_REBUTTAL_LENGTH = 20


async def submit_appeal(
    session: AsyncSession, *, case_id: uuid.UUID, user_id: uuid.UUID, rebuttal: str
) -> dict:
    case = await session.get(Case, case_id)
    if case is None or case.user_id != user_id:
        # 403이 아니라 404 — 사건 존재 여부 자체를 노출하지 않는다.
        raise ApiError(404, "CASE_NOT_FOUND", "사건을 찾을 수 없습니다.")

    if case.status != CaseStatus.SENTENCED or case.appeal_used:
        raise ApiError(409, "APPEAL_ALREADY_USED", "이미 항소를 사용한 사건입니다.")

    if len(rebuttal.strip()) < MIN_REBUTTAL_LENGTH:
        raise ApiError(
            400,
            "REBUTTAL_TOO_SHORT",
            "항소 사유는 20자 이상 입력해야 합니다.",
            {"min_length": MIN_REBUTTAL_LENGTH},
        )

    session.add(Appeal(case_id=case_id, rebuttal=rebuttal))
    # 성공/실패와 무관하게 접수 즉시 소진한다 (plan.md §4).
    case.appeal_used = True
    case.status = CaseStatus.QUEUED_REJUDGMENT
    await session.commit()

    return case_progress_dict(case)
