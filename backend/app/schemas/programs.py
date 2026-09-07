from __future__ import annotations

from datetime import datetime
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from backend.app.db.models import ProgramRegion
from backend.app.schemas.evidence import (
    ActorRef,
    Identifier,
    normalize_aware_utc,
    normalize_official_domain,
    normalize_official_domain_aliases,
    normalize_official_url,
)
from backend.app.schemas.profile_analysis import StrictModel


class ProgramCreateRequest(StrictModel):
    official_name: Annotated[str, Field(min_length=1, max_length=300)]
    institution_name: Annotated[str, Field(min_length=1, max_length=300)]
    region: ProgramRegion
    official_program_url: Annotated[str, Field(min_length=1, max_length=2048)]
    registered_official_domain: Annotated[str, Field(min_length=3, max_length=253)]
    official_domain_aliases: Annotated[list[str], Field(max_length=10)] = Field(
        default_factory=list
    )
    created_by: ActorRef
    creation_note: Annotated[str, Field(min_length=1, max_length=1000)]

    @field_validator("official_program_url")
    @classmethod
    def normalize_program_url(cls, value: str) -> str:
        return normalize_official_url(value)

    @field_validator("registered_official_domain")
    @classmethod
    def normalize_registered_domain(cls, value: str) -> str:
        return normalize_official_domain(value)

    @model_validator(mode="after")
    def official_url_belongs_to_registered_domain(self) -> "ProgramCreateRequest":
        self.official_domain_aliases = normalize_official_domain_aliases(
            self.official_domain_aliases,
            registered_domain=self.registered_official_domain,
        )
        host = normalize_official_domain(
            urlsplit(self.official_program_url).hostname or ""
        )
        if host != self.registered_official_domain and not host.endswith(
            f".{self.registered_official_domain}"
        ):
            raise ValueError(
                "official_program_url must belong to registered_official_domain"
            )
        return self


class ProgramRecord(StrictModel):
    id: Identifier
    official_name: str
    institution_name: str
    region: ProgramRegion
    official_program_url: str
    registered_official_domain: str
    official_domain_aliases: list[str] = Field(default_factory=list)
    created_by: ActorRef
    created_at: datetime

    @field_validator("created_at", mode="after")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return normalize_aware_utc(value)
