import { z } from "zod";

const requirementStatus = z.enum([
  "met",
  "unmet",
  "missing_information",
  "manual_review",
  "not_applicable",
]);

const citationSchema = z.object({
  evidence_id: z.string(),
  field_key: z.string(),
  url: z.string().url(),
  page_title: z.string(),
  excerpt: z.string(),
  source_version: z.string(),
  verified_at: z.string(),
  review_due_at: z.string(),
  freshness: z.enum(["fresh", "review_due", "expired", "source_unavailable"]),
});

const fieldJudgmentSchema = z.object({
  field_key: z.string(),
  coverage_status: z.string(),
  status: requirementStatus,
  is_critical: z.boolean(),
  is_high_risk: z.boolean(),
  display_text: z.string(),
  reason_codes: z.array(z.string()),
  citations: z.array(citationSchema).min(1),
});

const historicalCitationSchema = z.object({
  source_id: z.string(),
  field_key: z.string(),
  academic_year: z.literal("2026-27"),
  url: z.string().url(),
  page_title: z.string(),
  excerpt: z.string(),
  source_version: z.string(),
  verified_at: z.string(),
  snapshot_sha256: z.string().regex(/^[a-f0-9]{64}$/),
});

const historicalReferenceSchema = z.object({
  academic_year: z.literal("2026-27"),
  availability: z.enum(["evaluable", "limited"]),
  reference_status: z.enum(["met", "partial", "unmet", "unavailable"]),
  reference_label: z.enum(["满足", "部分满足", "未满足", "资料不足"]),
  summary: z.object({
    met: z.number().int().nonnegative(),
    unmet: z.number().int().nonnegative(),
    missing_information: z.number().int().nonnegative(),
    manual_review: z.number().int().nonnegative(),
  }),
  field_judgments: z.array(z.object({
    field_key: z.string(),
    status: requirementStatus,
    display_text: z.string(),
    reason_code: z.string(),
    citations: z.array(historicalCitationSchema).min(1),
  })),
  limitation_note: z.string().nullable(),
  disclaimer: z.literal("以下仅按 2026/27 官方门槛计算历史参考，不代表 2027/28 要求，也不参与 2027 推荐分层。"),
});

const programAdviceSchema = z.object({
  program_ref: z.string(),
  program_name: z.string(),
  institution_name: z.string(),
  region: z.enum(["hong_kong", "united_kingdom"]),
  official_program_url: z.string().url(),
  primary_direction: z.string(),
  secondary_directions: z.array(z.string()),
  recommendation_tier: z.enum(["sprint", "target", "relative_safe", "verify"]),
  recommendation_label: z.enum(["冲刺", "主申", "相对稳妥", "待核验"]),
  threshold_summary: z.object({
    met: z.number().int().nonnegative(),
    unmet: z.number().int().nonnegative(),
    missing_information: z.number().int().nonnegative(),
    manual_review: z.number().int().nonnegative(),
    not_applicable: z.number().int().nonnegative(),
  }),
  missing_fields: z.array(z.string()),
  high_risk_field_keys: z.array(z.string()),
  field_judgments: z.array(fieldJudgmentSchema),
  historical_reference: historicalReferenceSchema.nullish(),
  explanation: z.object({
    program_ref: z.string(),
    summary: z.string(),
    strengths: z.array(z.string()),
    risks: z.array(z.string()),
    next_actions: z.array(z.string()),
  }),
});

export const selectionAdviceResponseSchema = z.object({
  schema_version: z.literal("selection_advice_response.v1"),
  eligibility_profile: z.record(z.string(), z.unknown()),
  results: z.array(programAdviceSchema),
  excluded_program_count: z.number().int().nonnegative(),
  empty_reason: z.string().nullable(),
  disclaimer: z.string(),
  meta: z.object({
    request_id: z.string(),
    dataset_id: z.string(),
    dataset_manifest_sha256: z.string(),
    model_name: z.string(),
    prompt_version: z.string(),
    generated_at: z.string(),
    duration_ms: z.number().int().nonnegative(),
  }),
});
