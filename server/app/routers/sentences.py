import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.dependencies import get_current_user_id
from app.schemas.case import SentenceToggleRequest, SentenceToggleResponse
from app.services.sentence import toggle_sentence

router = APIRouter(tags=["sentences"])


@router.patch(
    "/sentences/{sentence_id}", operation_id="toggleSentence", response_model=SentenceToggleResponse
)
async def patch_sentence(
    sentence_id: uuid.UUID,
    body: SentenceToggleRequest,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    return await toggle_sentence(
        session, sentence_id=sentence_id, user_id=user_id, completed=body.completed
    )
