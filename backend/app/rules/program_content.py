from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from backend.app.rules.canonical import content_hash
from backend.app.schemas.candidates import (
    ProgramFieldPayloadAny,
    ProgramRequirementFieldV1,
)


CONTENT_SCHEMA_VERSION = "program_version_content.v1"
ENGINE_CONTRACT_VERSION = "requirement_engine.v1"


def field_fact_projection(payload: ProgramFieldPayloadAny) -> dict[str, Any]:
    """Return the stable fact-only projection used by candidate content hashes."""
    projected = payload.model_dump(mode="python", exclude_none=False)
    if isinstance(payload, ProgramRequirementFieldV1):
        requirement = dict(projected["requirement"])
        requirement.pop("display_text", None)
        requirement.pop("evidence_fixture_ids", None)
        projected["requirement"] = requirement
        return projected
    projected.pop("reviewed_source_ids", None)
    projected.pop("review_note", None)
    if payload.schema_version == "program_requirement_field.v2":
        for requirement in projected["requirements"]:
            requirement.pop("display_text", None)
            requirement.pop("evidence_fixture_ids", None)
    elif payload.schema_version == "program_taxonomy_field.v1":
        value = projected.get("value")
        if isinstance(value, dict) and payload.field_key == "taxonomy.low_altitude_basis":
            value.pop("rationale_zh", None)
            for course in value.get("courses", []):
                course.pop("evidence_id", None)
    return projected


def field_value_hash(payload: ProgramFieldPayloadAny) -> str:
    return content_hash(field_fact_projection(payload))


def program_content_envelope(
    fields: Iterable[object],
    evidence_snapshot_sha256_by_id: Mapping[str, str],
) -> dict[str, Any]:
    """Build the deterministic repository-compatible semantic content envelope."""
    content_fields: list[dict[str, Any]] = []
    for field in sorted(fields, key=lambda item: str(getattr(item, "field_key"))):
        payload = getattr(field, "value_payload")
        evidence_content = []
        for link in sorted(
            getattr(field, "evidence_links"),
            key=lambda item: (
                item.evidence_id,
                item.support_scope.value
                if hasattr(item.support_scope, "value")
                else str(item.support_scope),
            ),
        ):
            evidence_content.append(
                {
                    "evidence_id": link.evidence_id,
                    "snapshot_sha256": evidence_snapshot_sha256_by_id[
                        link.evidence_id
                    ],
                    "support_scope": link.support_scope,
                }
            )
        content_fields.append(
            {
                "field_key": field.field_key,
                "value_schema_version": field.value_schema_version,
                "value_payload": field_fact_projection(payload),
                "value_sha256": getattr(
                    field, "value_sha256", field_value_hash(payload)
                ),
                "is_critical": field.is_critical,
                "evidence": evidence_content,
            }
        )
    return {
        "content_schema_version": CONTENT_SCHEMA_VERSION,
        "rule_contracts": [ENGINE_CONTRACT_VERSION],
        "fields": content_fields,
    }


def program_content_hash(
    fields: Iterable[object],
    evidence_snapshot_sha256_by_id: Mapping[str, str],
) -> str:
    return content_hash(
        program_content_envelope(fields, evidence_snapshot_sha256_by_id)
    )
