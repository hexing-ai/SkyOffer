from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from backend.app.rules.canonical import content_hash
from backend.app.rules.evaluator import RequirementEngine
from backend.app.schemas.alpha_program_pack import AlphaProgramPackV1
from backend.app.schemas.evidence import belongs_to_official_domains
from backend.app.schemas.historical_reference import (
    HistoricalCitation,
    HistoricalFieldJudgment,
    HistoricalProgramReference,
    HistoricalReferenceAvailability,
    HistoricalReferenceDataset,
    HistoricalReferenceResult,
    HistoricalReferenceSummary,
)
from backend.app.schemas.requirement_evaluation import RequirementStatus
from backend.app.schemas.requirement_rules import ApplicantEligibilityInput, RequirementRuleSet


DEFAULT_HISTORICAL_REFERENCE_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "alpha_v1"
    / "historical_references"
    / "historical_reference_2026_27.v1.json"
)
HISTORICAL_REFERENCE_DISCLAIMER = (
    "以下仅按 2026/27 官方门槛计算历史参考，不代表 2027/28 要求，也不参与 2027 推荐分层。"
)


def load_historical_reference_dataset(
    path: Path = DEFAULT_HISTORICAL_REFERENCE_PATH,
) -> HistoricalReferenceDataset:
    return HistoricalReferenceDataset.model_validate_json(path.read_text(encoding="utf-8"))


def validate_historical_reference_dataset(
    dataset: HistoricalReferenceDataset,
    packs_by_program_ref: dict[str, AlphaProgramPackV1],
) -> None:
    for entry in dataset.programs:
        pack = packs_by_program_ref.get(entry.program_ref)
        if pack is None:
            raise ValueError(f"historical reference Program is not in Alpha: {entry.program_ref}")
        for source in entry.sources:
            if source.snapshot_sha256 != hashlib.sha256(
                source.excerpt.encode("utf-8")
            ).hexdigest():
                raise ValueError(f"historical source hash mismatch: {source.source_id}")
            host = urlsplit(source.url).hostname or ""
            if not belongs_to_official_domains(
                host,
                registered_domain=pack.program.registered_official_domain,
                aliases=pack.program.official_domain_aliases,
            ):
                raise ValueError(f"historical source is outside official domains: {source.source_id}")


def evaluate_historical_reference(
    entry: HistoricalProgramReference | None,
    profile: ApplicantEligibilityInput,
    engine: RequirementEngine,
) -> HistoricalReferenceResult | None:
    if entry is None:
        return None
    if entry.availability == HistoricalReferenceAvailability.LIMITED or not entry.fields:
        return HistoricalReferenceResult(
            academic_year="2026-27",
            availability=entry.availability,
            reference_status="unavailable",
            reference_label="资料不足",
            summary=HistoricalReferenceSummary(
                met=0, unmet=0, missing_information=0, manual_review=0
            ),
            field_judgments=[],
            limitation_note=entry.limitation_note,
            disclaimer=HISTORICAL_REFERENCE_DISCLAIMER,
        )

    requirements = [field.requirement for field in entry.fields]
    digest = content_hash(entry.program_ref)[:16]
    evaluation = engine.evaluate(
        profile,
        RequirementRuleSet(
            schema_version="requirement_rule_set.v1",
            ruleset_id=f"ruleset.history.{digest}",
            ruleset_version="1.0.0",
            engine_contract_version="requirement_engine.v1",
            synthetic_program_ref=entry.program_ref,
            requirements=requirements,
        ),
    )
    result_by_id = {item.requirement_id: item for item in evaluation.requirement_results}
    source_by_id = {item.source_id: item for item in entry.sources}
    judgments: list[HistoricalFieldJudgment] = []
    for field in entry.fields:
        result = result_by_id[field.requirement.requirement_id]
        judgments.append(
            HistoricalFieldJudgment(
                field_key=field.field_key,
                status=result.status,
                display_text=field.display_text,
                reason_code=result.reason_code,
                citations=[
                    HistoricalCitation(
                        source_id=source.source_id,
                        field_key=field.field_key,
                        academic_year=entry.academic_year,
                        url=source.url,
                        page_title=source.page_title,
                        excerpt=source.excerpt,
                        source_version=source.source_version,
                        verified_at=source.verified_at,
                        snapshot_sha256=source.snapshot_sha256,
                    )
                    for source in (source_by_id[source_id] for source_id in field.source_ids)
                ],
            )
        )
    counts = Counter(item.status.value for item in evaluation.requirement_results)
    if counts[RequirementStatus.UNMET.value]:
        reference_status, reference_label = "unmet", "未满足"
    elif all(
        item.status in {RequirementStatus.MET, RequirementStatus.NOT_APPLICABLE}
        for item in evaluation.requirement_results
    ):
        reference_status, reference_label = "met", "满足"
    else:
        reference_status, reference_label = "partial", "部分满足"
    return HistoricalReferenceResult(
        academic_year="2026-27",
        availability=entry.availability,
        reference_status=reference_status,
        reference_label=reference_label,
        summary=HistoricalReferenceSummary(
            met=counts[RequirementStatus.MET.value],
            unmet=counts[RequirementStatus.UNMET.value],
            missing_information=counts[RequirementStatus.MISSING_INFORMATION.value],
            manual_review=counts[RequirementStatus.MANUAL_REVIEW.value],
        ),
        field_judgments=judgments,
        limitation_note=entry.limitation_note,
        disclaimer=HISTORICAL_REFERENCE_DISCLAIMER,
    )
