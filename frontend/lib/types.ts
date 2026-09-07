export type Region = "hong_kong" | "united_kingdom";
export type Direction =
  | "computer_science"
  | "artificial_intelligence"
  | "aerospace_engineering"
  | "low_altitude_economy";

export type RecommendationTier = "sprint" | "target" | "relative_safe" | "verify";
export type RequirementStatus =
  | "met"
  | "unmet"
  | "missing_information"
  | "manual_review"
  | "not_applicable";

export interface SelectionAdviceRequest {
  schema_version: "selection_advice_request.v1";
  profile: {
    schema_version: "applicant_analysis_input.v1";
    request_language: "zh-CN";
    education_status: "undergraduate" | "graduated" | "other";
    graduation_year: number;
    undergraduate_institution: string;
    undergraduate_major: string;
    degree_type: string;
    grading_scale: number;
    grade_value: number;
    core_courses: string[];
    language_scores: Array<{
      test_type: "IELTS" | "TOEFL" | "PTE";
      total_score: number;
      component_scores: Partial<Record<"listening" | "reading" | "writing" | "speaking", number>>;
      test_date: null;
    }>;
    experiences: Array<{ type: "project"; title: string; description: string }>;
    target_regions: Region[];
    target_directions: Direction[];
    career_goal: string | null;
    budget_note: null;
  };
  rule_facts: {
    institution_recognition: "unknown" | "mainland_recognized" | "mainland_priority";
    work_experience_months: number | null;
    materials: {
      portfolio: boolean | null;
      interview: boolean | null;
      recommendation_letters: boolean | null;
    };
  };
}

export interface OfficialCitation {
  evidence_id: string;
  field_key: string;
  url: string;
  page_title: string;
  excerpt: string;
  source_version: string;
  verified_at: string;
  review_due_at: string;
  freshness: "fresh" | "review_due" | "expired" | "source_unavailable";
}

export interface FieldJudgment {
  field_key: string;
  coverage_status: string;
  status: RequirementStatus;
  is_critical: boolean;
  is_high_risk: boolean;
  display_text: string;
  reason_codes: string[];
  citations: OfficialCitation[];
}

export interface HistoricalCitation {
  source_id: string;
  field_key: string;
  academic_year: "2026-27";
  url: string;
  page_title: string;
  excerpt: string;
  source_version: string;
  verified_at: string;
  snapshot_sha256: string;
}

export interface HistoricalFieldJudgment {
  field_key: string;
  status: RequirementStatus;
  display_text: string;
  reason_code: string;
  citations: HistoricalCitation[];
}

export interface HistoricalReferenceResult {
  academic_year: "2026-27";
  availability: "evaluable" | "limited";
  reference_status: "met" | "partial" | "unmet" | "unavailable";
  reference_label: "满足" | "部分满足" | "未满足" | "资料不足";
  summary: {
    met: number;
    unmet: number;
    missing_information: number;
    manual_review: number;
  };
  field_judgments: HistoricalFieldJudgment[];
  limitation_note: string | null;
  disclaimer: "以下仅按 2026/27 官方门槛计算历史参考，不代表 2027/28 要求，也不参与 2027 推荐分层。";
}

export interface ProgramAdvice {
  program_ref: string;
  program_name: string;
  institution_name: string;
  region: Region;
  official_program_url: string;
  primary_direction: string;
  secondary_directions: string[];
  recommendation_tier: RecommendationTier;
  recommendation_label: "冲刺" | "主申" | "相对稳妥" | "待核验";
  threshold_summary: Record<RequirementStatus, number>;
  missing_fields: string[];
  high_risk_field_keys: string[];
  field_judgments: FieldJudgment[];
  historical_reference?: HistoricalReferenceResult | null;
  explanation: {
    program_ref: string;
    summary: string;
    strengths: string[];
    risks: string[];
    next_actions: string[];
  };
}

export interface SelectionAdviceResponse {
  schema_version: "selection_advice_response.v1";
  eligibility_profile: Record<string, unknown>;
  results: ProgramAdvice[];
  excluded_program_count: number;
  empty_reason: string | null;
  disclaimer: string;
  meta: {
    request_id: string;
    dataset_id: string;
    dataset_manifest_sha256: string;
    model_name: string;
    prompt_version: string;
    generated_at: string;
    duration_ms: number;
  };
}

export type RequestState = "idle" | "submitting" | "succeeded" | "empty" | "failed";

export interface FormValues {
  educationStatus: "undergraduate" | "graduated" | "other";
  graduationYear: string;
  institution: string;
  institutionRecognition: "unknown" | "mainland_recognized" | "mainland_priority";
  major: string;
  degreeType: string;
  gradeValue: string;
  gradingScale: string;
  courses: string;
  languageType: "" | "IELTS" | "TOEFL" | "PTE";
  languageTotal: string;
  listening: string;
  reading: string;
  writing: string;
  speaking: string;
  workMonths: string;
  experienceTitle: string;
  experienceDescription: string;
  targetRegions: Region[];
  targetDirections: Direction[];
  careerGoal: string;
  portfolio: "" | "true" | "false";
  interview: "" | "true" | "false";
  recommendation: "" | "true" | "false";
}

export type ProgramReviewStatus = "domain_reviewed";
export type ProgramCoverageStatus =
  | "confirmed"
  | "manual_review"
  | "not_yet_published"
  | "not_found_in_reviewed_sources"
  | "not_applicable";

export interface ProgramCatalogDataset {
  dataset_id: string;
  target_academic_year: "2027-28";
  program_count: number;
  data_boundary: "internal_candidate_only";
  public_publishable: false;
  manifest_sha256: string;
}

export interface ProgramCoverageSummary {
  confirmed: number;
  unresolved: number;
  total: number;
}

export interface ProgramCatalogItem {
  program_ref: string;
  official_name: string;
  institution_name: string;
  region: Region;
  official_program_url: string;
  target_academic_year: "2027-28";
  degree_type: "taught_masters";
  primary_direction: Direction;
  secondary_directions: Direction[];
  review_status: ProgramReviewStatus;
  has_unresolved_fields: boolean;
  reviewed_at: string;
  candidate_version_id: string;
  pack_ref: string;
  pack_schema_version: "alpha_program_pack.v1";
  pack_canonical_sha256: string;
  evidence_count: number;
  coverage: ProgramCoverageSummary;
}

export interface ProgramFieldCitation {
  evidence_id: string;
  support_scope: "direct" | "applicability" | "definition" | "coverage";
  citation_order: number;
  url: string;
  page_title: string;
  excerpt: string;
  source_version: string;
  verified_at: string;
  review_due_at: string;
  expires_at: string;
  freshness: "fresh" | "review_due" | "expired" | "source_unavailable";
}

export interface ProgramCatalogField {
  field_key: string;
  label: string;
  group: "项目概况" | "专业方向" | "申请门槛";
  display_text: string;
  coverage_status: ProgramCoverageStatus;
  is_critical: boolean;
  value_schema_version: string;
  citations: ProgramFieldCitation[];
}

export interface ProgramCatalogListResponse {
  schema_version: "program_catalog_list.v1";
  dataset: ProgramCatalogDataset;
  programs: ProgramCatalogItem[];
}

export interface ProgramCatalogDetailResponse {
  schema_version: "program_catalog_detail.v1";
  dataset: ProgramCatalogDataset;
  program: ProgramCatalogItem & { fields: ProgramCatalogField[] };
}
