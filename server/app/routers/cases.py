import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from app.db import get_session
from app.errors import ApiError
from app.models import Case
from app.schemas.case import CaseDetail, CaseProgress, CaseSubmissionResult, CreateCaseRequest
from app.services.case_read import build_case_detail, case_progress_dict
from app.services.case_submission import TEMP_USER_ID, submit_case

router = APIRouter(tags=["cases"])


async def _get_owned_case(session: AsyncSession, case_id: uuid.UUID) -> Case:
    case = await session.get(Case, case_id)
    if case is None or case.user_id != TEMP_USER_ID:
        raise ApiError(404, "CASE_NOT_FOUND", "사건을 찾을 수 없습니다.")
    return case


@router.post("/cases", operation_id="createCase")
async def create_case(body: CreateCaseRequest, session: AsyncSession = Depends(get_session)):
    status_code, result = await submit_case(
        session, code=body.code, language=body.language, force_retrial=body.force_retrial
    )
    payload = CaseSubmissionResult(**result)
    return JSONResponse(
        status_code=status_code, content=payload.model_dump(mode="json", exclude_none=True)
    )


@router.get("/cases/{case_id}", operation_id="getCase", response_model=CaseDetail)
async def get_case(case_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_session)):
    case = await _get_owned_case(session, case_id)
    catalog = request.app.state.rule_catalog
    return await build_case_detail(session, catalog, case)


@router.get("/cases/{case_id}/progress", operation_id="getCaseProgress", response_model=CaseProgress)
async def get_case_progress(case_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    case = await _get_owned_case(session, case_id)
    return case_progress_dict(case)
