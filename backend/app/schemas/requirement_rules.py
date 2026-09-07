from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from backend.app.schemas.profile_analysis import StrictModel


Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{1,79}$")]
Version = Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0, max_digits=8, decimal_places=3)]


class ApplicantRegion(StrEnum):
    CHINA_MAINLAND = "china_mainland"
    HONG_KONG = "hong_kong"
    OTHER = "other"


class DegreeLevel(StrEnum):
    BACHELOR = "bachelor"
    MASTER = "master"
    OTHER = "other"


class DegreeStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    AWARDED = "awarded"


class SubjectTag(StrEnum):
    COMPUTER_SCIENCE = "computer_science"
    ARTIFICIAL_INTELLIGENCE = "artificial_intelligence"
    DATA_SCIENCE = "data_science"
    AUTOMATION = "automation"
    AEROSPACE_ENGINEERING = "aerospace_engineering"
    MECHANICAL_ENGINEERING = "mechanical_engineering"
    ELECTRONIC_ENGINEERING = "electronic_engineering"
    OTHER = "other"


class InstitutionTag(StrEnum):
    CHINA_MAINLAND_RECOGNIZED = "china_mainland_recognized"
    CHINA_MAINLAND_PRIORITY = "china_mainland_priority"
    UK_RECOGNIZED = "uk_recognized"
    OTHER_RECOGNIZED = "other_recognized"


class CourseTag(StrEnum):
    MATHEMATICS = "mathematics"
    STATISTICS = "statistics"
    PROGRAMMING = "programming"
    DATA_STRUCTURES = "data_structures"
    DATABASES = "databases"
    MACHINE_LEARNING = "machine_learning"
    CONTROL = "control"
    AEROSPACE = "aerospace"


class LanguageTestType(StrEnum):
    IELTS = "ielts"
    TOEFL = "toefl"
    PTE = "pte"


class LanguageComponent(StrEnum):
    LISTENING = "listening"
    READING = "reading"
    WRITING = "writing"
    SPEAKING = "speaking"


class AcademicRecord(StrictModel):
    value: Annotated[Decimal, Field(ge=0, max_digits=8, decimal_places=3)]
    scale: Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=3)]
    degree_classification: Annotated[str | None, Field(default=None, max_length=80)]

    @model_validator(mode="after")
    def value_must_fit_scale(self) -> "AcademicRecord":
        if self.value > self.scale:
            raise ValueError("academic value cannot exceed scale")
        return self


class CourseFact(StrictModel):
    course_ref: Identifier
    tags: Annotated[frozenset[CourseTag], Field(min_length=1, max_length=8)]


class LanguageResult(StrictModel):
    test_type: LanguageTestType
    total: Annotated[Decimal | None, Field(default=None, ge=0, max_digits=8, decimal_places=3)]
    components: Annotated[
        dict[LanguageComponent, Decimal | None], Field(default_factory=dict, max_length=4)
    ]


class MaterialFacts(StrictModel):
    portfolio: bool | None = None
    interview: bool | None = None
    recommendation_letters: bool | None = None


class ApplicantEligibilityInput(StrictModel):
    schema_version: Literal["applicant_eligibility_input.v1"]
    profile_ref: Identifier
    applicant_region: ApplicantRegion | None = None
    degree_level: DegreeLevel | None = None
    degree_status: DegreeStatus | None = None
    graduation_year: Annotated[int | None, Field(default=None, ge=2000, le=2040)]
    degree_subject_tags: Annotated[
        frozenset[SubjectTag], Field(default_factory=frozenset, max_length=16)
    ]
    institution_tags: Annotated[
        frozenset[InstitutionTag], Field(default_factory=frozenset, max_length=16)
    ]
    academic_record: AcademicRecord | None = None
    course_tags: Annotated[list[CourseFact], Field(default_factory=list, max_length=100)]
    language_results: Annotated[
        list[LanguageResult], Field(default_factory=list, max_length=12)
    ]
    work_experience_months: Annotated[int | None, Field(default=None, ge=0, le=1200)]
    materials: MaterialFacts = Field(default_factory=MaterialFacts)

    @model_validator(mode="after")
    def unique_course_refs(self) -> "ApplicantEligibilityInput":
        refs = [course.course_ref for course in self.course_tags]
        if len(refs) != len(set(refs)):
            raise ValueError("course_ref values must be unique")
        return self


class FactPath(StrEnum):
    APPLICANT_REGION = "applicant_region"
    DEGREE_LEVEL = "degree_level"
    DEGREE_STATUS = "degree_status"
    GRADUATION_YEAR = "graduation_year"
    DEGREE_SUBJECT_TAGS = "degree_subject_tags"
    INSTITUTION_TAGS = "institution_tags"
    ACADEMIC_VALUE = "academic_record.value"
    WORK_EXPERIENCE_MONTHS = "work_experience_months"
    MATERIAL_PORTFOLIO = "materials.portfolio"
    MATERIAL_INTERVIEW = "materials.interview"
    MATERIAL_RECOMMENDATION_LETTERS = "materials.recommendation_letters"


class RuleNodeBase(StrictModel):
    node_id: Identifier


class AllRule(RuleNodeBase):
    operator: Literal["all"]
    children: Annotated[list["RuleNode"], Field(min_length=1, max_length=100)]


class AnyRule(RuleNodeBase):
    operator: Literal["any"]
    children: Annotated[list["RuleNode"], Field(min_length=1, max_length=100)]


class NumericMinRule(RuleNodeBase):
    operator: Literal["numeric_min"]
    fact_path: Literal[
        FactPath.GRADUATION_YEAR,
        FactPath.ACADEMIC_VALUE,
        FactPath.WORK_EXPERIENCE_MONTHS,
    ]
    minimum: NonNegativeDecimal
    scale: Annotated[Decimal | None, Field(default=None, gt=0)]

    @model_validator(mode="after")
    def scale_only_applies_to_academic_value(self) -> "NumericMinRule":
        if self.fact_path == FactPath.ACADEMIC_VALUE and self.scale is None:
            raise ValueError("scale is required for academic_record.value")
        if self.scale is not None and self.fact_path != FactPath.ACADEMIC_VALUE:
            raise ValueError("scale is only valid for academic_record.value")
        return self


class NumericMaxRule(RuleNodeBase):
    operator: Literal["numeric_max"]
    fact_path: Literal[
        FactPath.GRADUATION_YEAR,
        FactPath.ACADEMIC_VALUE,
        FactPath.WORK_EXPERIENCE_MONTHS,
    ]
    maximum: NonNegativeDecimal
    scale: Annotated[Decimal | None, Field(default=None, gt=0)]

    @model_validator(mode="after")
    def scale_only_applies_to_academic_value(self) -> "NumericMaxRule":
        if self.fact_path == FactPath.ACADEMIC_VALUE and self.scale is None:
            raise ValueError("scale is required for academic_record.value")
        if self.scale is not None and self.fact_path != FactPath.ACADEMIC_VALUE:
            raise ValueError("scale is only valid for academic_record.value")
        return self


class EnumInRule(RuleNodeBase):
    operator: Literal["enum_in"]
    fact_path: Literal[
        FactPath.APPLICANT_REGION,
        FactPath.DEGREE_LEVEL,
        FactPath.DEGREE_STATUS,
    ]
    allowed_values: Annotated[frozenset[str], Field(min_length=1, max_length=50)]

    @model_validator(mode="after")
    def allowed_values_must_match_fact_enum(self) -> "EnumInRule":
        enum_by_path = {
            FactPath.APPLICANT_REGION: ApplicantRegion,
            FactPath.DEGREE_LEVEL: DegreeLevel,
            FactPath.DEGREE_STATUS: DegreeStatus,
        }
        valid = {item.value for item in enum_by_path[self.fact_path]}
        invalid = self.allowed_values.difference(valid)
        if invalid:
            raise ValueError(f"allowed_values contain invalid values: {sorted(invalid)}")
        return self


class SetIntersectsRule(RuleNodeBase):
    operator: Literal["set_intersects"]
    fact_path: Literal[FactPath.DEGREE_SUBJECT_TAGS, FactPath.INSTITUTION_TAGS]
    accepted_values: Annotated[frozenset[str], Field(min_length=1, max_length=50)]
    minimum_matches: Annotated[int, Field(default=1, ge=1, le=50)]

    @model_validator(mode="after")
    def accepted_values_must_match_fact_enum(self) -> "SetIntersectsRule":
        enum_type = (
            SubjectTag
            if self.fact_path == FactPath.DEGREE_SUBJECT_TAGS
            else InstitutionTag
        )
        valid = {item.value for item in enum_type}
        invalid = self.accepted_values.difference(valid)
        if invalid:
            raise ValueError(f"accepted_values contain invalid values: {sorted(invalid)}")
        if self.minimum_matches > len(self.accepted_values):
            raise ValueError("minimum_matches cannot exceed accepted_values count")
        return self


class CourseGroupRule(RuleNodeBase):
    operator: Literal["course_group"]
    accepted_tags: Annotated[frozenset[CourseTag], Field(min_length=1, max_length=20)]
    minimum_courses: Annotated[int, Field(default=1, ge=1, le=50)]


class LanguageMinimumRule(RuleNodeBase):
    operator: Literal["language_minimum"]
    test_type: LanguageTestType
    total_min: Annotated[Decimal | None, Field(default=None, ge=0)]
    component_mins: Annotated[
        dict[LanguageComponent, NonNegativeDecimal], Field(default_factory=dict, max_length=4)
    ]

    @model_validator(mode="after")
    def at_least_one_threshold(self) -> "LanguageMinimumRule":
        if self.total_min is None and not self.component_mins:
            raise ValueError("language rule needs a total or component threshold")
        return self


class DurationMinMonthsRule(RuleNodeBase):
    operator: Literal["duration_min_months"]
    fact_path: Literal[FactPath.WORK_EXPERIENCE_MONTHS]
    minimum_months: Annotated[int, Field(ge=0, le=1200)]


class BooleanIsRule(RuleNodeBase):
    operator: Literal["boolean_is"]
    fact_path: Literal[
        FactPath.MATERIAL_PORTFOLIO,
        FactPath.MATERIAL_INTERVIEW,
        FactPath.MATERIAL_RECOMMENDATION_LETTERS,
    ]
    expected: bool


class ManualReviewRule(RuleNodeBase):
    operator: Literal["manual_review"]
    reason_code: Literal[
        "OFFICIAL_RULE_AMBIGUOUS",
        "OFFICIAL_RULE_NOT_PUBLISHED",
        "OFFICIAL_RULE_NOT_FOUND",
        "OFFICIAL_RULE_REQUIRES_CASE_REVIEW",
    ] = "OFFICIAL_RULE_AMBIGUOUS"


class CaseRule(RuleNodeBase):
    operator: Literal["case"]
    selector_path: Literal[FactPath.APPLICANT_REGION]
    cases: Annotated[dict[str, "RuleNode"], Field(min_length=1, max_length=20)]
    default: "RuleNode | None" = None

    @model_validator(mode="after")
    def case_keys_must_match_selector_enum(self) -> "CaseRule":
        valid = {item.value for item in ApplicantRegion}
        invalid = set(self.cases).difference(valid)
        if invalid:
            raise ValueError(f"case keys contain invalid values: {sorted(invalid)}")
        return self


RuleNode: TypeAlias = Annotated[
    AllRule
    | AnyRule
    | NumericMinRule
    | NumericMaxRule
    | EnumInRule
    | SetIntersectsRule
    | CourseGroupRule
    | LanguageMinimumRule
    | DurationMinMonthsRule
    | BooleanIsRule
    | ManualReviewRule
    | CaseRule,
    Field(discriminator="operator"),
]


class RequirementFixture(StrictModel):
    requirement_id: Identifier
    requirement_type: Literal[
        "degree",
        "academic",
        "subject",
        "course",
        "language",
        "work_experience",
        "material",
    ]
    is_hard: bool
    applicability: RuleNode | None = None
    rule: RuleNode
    evidence_fixture_ids: Annotated[list[Identifier], Field(min_length=1, max_length=20)]
    display_text: Annotated[str, Field(min_length=1, max_length=500)]


class RequirementRuleSet(StrictModel):
    schema_version: Literal["requirement_rule_set.v1"]
    ruleset_id: Identifier
    ruleset_version: Version
    engine_contract_version: Literal["requirement_engine.v1"]
    synthetic_program_ref: Identifier
    requirements: Annotated[list[RequirementFixture], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def validate_tree(self) -> "RequirementRuleSet":
        requirement_ids = [item.requirement_id for item in self.requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise PydanticCustomError(
                "rule_invalid", "requirement_id values must be unique"
            )

        node_ids: set[str] = set()
        node_count = 0

        def walk(node: RuleNode, depth: int) -> None:
            nonlocal node_count
            if depth > 20:
                raise PydanticCustomError(
                    "rule_invalid", "rule tree exceeds maximum depth"
                )
            node_count += 1
            if node_count > 5000:
                raise PydanticCustomError(
                    "rule_invalid", "rule set exceeds maximum node count"
                )
            if node.node_id in node_ids:
                raise PydanticCustomError(
                    "rule_invalid", "duplicate node_id: {node_id}", {"node_id": node.node_id}
                )
            node_ids.add(node.node_id)
            if isinstance(node, (AllRule, AnyRule)):
                for child in node.children:
                    walk(child, depth + 1)
            elif isinstance(node, CaseRule):
                for child in node.cases.values():
                    walk(child, depth + 1)
                if node.default is not None:
                    walk(node.default, depth + 1)

        for requirement in self.requirements:
            if requirement.applicability is not None:
                walk(requirement.applicability, 1)
            walk(requirement.rule, 1)
        return self


AllRule.model_rebuild()
AnyRule.model_rebuild()
CaseRule.model_rebuild()
RequirementFixture.model_rebuild()
RequirementRuleSet.model_rebuild()
