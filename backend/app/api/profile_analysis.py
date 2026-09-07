from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.schemas.profile_analysis import (
    ApplicantAnalysisInput,
    ApplicantAnalysisOutput,
)


router = APIRouter(prefix="/api/v1", tags=["phase-one"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "model_configuration": "ready" if settings.model_is_configured else "missing",
    }


@router.post("/profile-analysis", response_model=ApplicantAnalysisOutput)
async def profile_analysis(
    profile: ApplicantAnalysisInput, request: Request
) -> ApplicantAnalysisOutput:
    return await request.app.state.profile_analysis_service.analyze(
        profile=profile,
        request_id=request.state.request_id,
    )
