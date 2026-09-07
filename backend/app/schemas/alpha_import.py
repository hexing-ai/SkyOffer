from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from backend.app.schemas.evidence import Identifier, Sha256Hex
from backend.app.schemas.profile_analysis import StrictModel


class AlphaCandidateImportResult(StrictModel):
    schema_version: Literal["alpha_candidate_import_result.v1"]
    pack_ref: Identifier
    pack_canonical_sha256: Sha256Hex
    program_id: Identifier
    program_created: bool
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=50)]
    candidate_version_id: Identifier
    candidate_version_no: Annotated[int, Field(ge=1)]
    candidate_status: Literal["candidate"]
    candidate_content_sha256: Sha256Hex
    publication_current_version_id: Identifier | None
    request_id: Identifier

    @model_validator(mode="after")
    def normalize_evidence_ids(self) -> "AlphaCandidateImportResult":
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("import result evidence IDs cannot contain duplicates")
        self.evidence_ids = sorted(self.evidence_ids)
        return self


class AlphaCandidateBatchItemResult(StrictModel):
    pack_ref: Identifier
    status: Literal["imported", "failed"]
    result: AlphaCandidateImportResult | None
    error_code: Literal["ALPHA_IMPORT_FAILED"] | None
    error_message: str | None

    @model_validator(mode="after")
    def validate_outcome(self) -> "AlphaCandidateBatchItemResult":
        if self.status == "imported":
            if (
                self.result is None
                or self.error_code is not None
                or self.error_message is not None
            ):
                raise ValueError("imported batch item must contain only a result")
        elif self.result is not None or self.error_code is None or not self.error_message:
            raise ValueError("failed batch item must contain only a safe error")
        return self


class AlphaCandidateBatchImportReport(StrictModel):
    schema_version: Literal["alpha_candidate_batch_import_report.v1"]
    attempted_count: Annotated[int, Field(ge=1)]
    imported_count: Annotated[int, Field(ge=0)]
    failed_count: Annotated[int, Field(ge=0)]
    complete: bool
    items: Annotated[list[AlphaCandidateBatchItemResult], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_counts(self) -> "AlphaCandidateBatchImportReport":
        refs = [item.pack_ref for item in self.items]
        if len(refs) != len(set(refs)):
            raise ValueError("batch pack refs must be unique")
        imported = sum(item.status == "imported" for item in self.items)
        failed = len(self.items) - imported
        if (
            self.attempted_count != len(self.items)
            or self.imported_count != imported
            or self.failed_count != failed
            or self.complete != (failed == 0)
        ):
            raise ValueError("batch counts must match item outcomes")
        return self
