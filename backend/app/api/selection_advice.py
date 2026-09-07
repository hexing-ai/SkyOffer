from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.phase3_dependencies import phase3_session
from backend.app.schemas.selection_advice import (
    SelectionAdviceRequest,
    SelectionAdviceResponse,
)


router = APIRouter(prefix="/api/v1", tags=["selection-advice-mvp"])


@router.post("/selection-advice", response_model=SelectionAdviceResponse)
async def selection_advice(
    payload: SelectionAdviceRequest,
    request: Request,
    session: Annotated[Session, Depends(phase3_session)],
) -> SelectionAdviceResponse:
    return await request.app.state.selection_advice_service.advise(
        payload,
        session=session,
        request_id=request.state.request_id,
    )
