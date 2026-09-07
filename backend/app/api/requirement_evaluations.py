from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, Request

from backend.app.schemas.requirement_evaluation import (
    RequirementEvaluationRequest,
    RequirementEvaluationResponse,
)


router = APIRouter(prefix="/api/v1", tags=["phase-two"])


@router.post(
    "/requirement-evaluations", response_model=RequirementEvaluationResponse
)
async def evaluate_requirements(
    payload: RequirementEvaluationRequest, request: Request
) -> RequirementEvaluationResponse:
    started = perf_counter()
    evaluation = request.app.state.requirement_engine.evaluate(
        profile=payload.profile,
        rule_set=payload.rule_set,
    )
    duration_ms = max(0, round((perf_counter() - started) * 1000))
    request.app.state.logger.info(
        "requirement_evaluation_completed request_id=%s evaluation_id=%s "
        "profile_hash=%s ruleset=%s@%s ruleset_hash=%s engine=%s duration_ms=%s",
        request.state.request_id,
        evaluation.evaluation_id,
        evaluation.profile_hash,
        evaluation.ruleset_id,
        evaluation.ruleset_version,
        evaluation.ruleset_hash,
        evaluation.engine_version,
        duration_ms,
    )
    return RequirementEvaluationResponse(
        **evaluation.model_dump(),
        request_id=request.state.request_id,
        duration_ms=duration_ms,
    )
