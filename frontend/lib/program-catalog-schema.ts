import { z } from "zod";

const directionSchema = z.enum([
  "computer_science",
  "artificial_intelligence",
  "aerospace_engineering",
  "low_altitude_economy",
]);

const datasetSchema = z.object({
  dataset_id: z.string(),
  target_academic_year: z.literal("2027-28"),
  program_count: z.number().int().positive(),
  data_boundary: z.literal("internal_candidate_only"),
  public_publishable: z.literal(false),
  manifest_sha256: z.string().regex(/^[0-9a-f]{64}$/),
});

const programItemSchema = z.object({
  program_ref: z.string(),
  official_name: z.string(),
  institution_name: z.string(),
  region: z.enum(["hong_kong", "united_kingdom"]),
  official_program_url: z.string().url(),
  target_academic_year: z.literal("2027-28"),
  degree_type: z.literal("taught_masters"),
  primary_direction: directionSchema,
  secondary_directions: z.array(directionSchema),
  review_status: z.literal("domain_reviewed"),
  has_unresolved_fields: z.boolean(),
  reviewed_at: z.string(),
  candidate_version_id: z.string(),
  pack_ref: z.string(),
  pack_schema_version: z.literal("alpha_program_pack.v1"),
  pack_canonical_sha256: z.string().regex(/^[0-9a-f]{64}$/),
  evidence_count: z.number().int().positive(),
  coverage: z.object({
    confirmed: z.number().int().nonnegative(),
    unresolved: z.number().int().nonnegative(),
    total: z.number().int().positive(),
  }),
});

const fieldSchema = z.object({
  field_key: z.string(),
  label: z.string(),
  group: z.enum(["项目概况", "专业方向", "申请门槛"]),
  display_text: z.string(),
  coverage_status: z.enum([
    "confirmed",
    "manual_review",
    "not_yet_published",
    "not_found_in_reviewed_sources",
    "not_applicable",
  ]),
  is_critical: z.boolean(),
  value_schema_version: z.string(),
  citations: z.array(z.object({
    evidence_id: z.string(),
    support_scope: z.enum(["direct", "applicability", "definition", "coverage"]),
    citation_order: z.number().int().positive(),
    url: z.string().url(),
    page_title: z.string(),
    excerpt: z.string(),
    source_version: z.string(),
    verified_at: z.string(),
    review_due_at: z.string(),
    expires_at: z.string(),
    freshness: z.enum(["fresh", "review_due", "expired", "source_unavailable"]),
  })).min(1),
});

export const programCatalogListSchema = z.object({
  schema_version: z.literal("program_catalog_list.v1"),
  dataset: datasetSchema,
  programs: z.array(programItemSchema),
});

export const programCatalogDetailSchema = z.object({
  schema_version: z.literal("program_catalog_detail.v1"),
  dataset: datasetSchema,
  program: programItemSchema.extend({ fields: z.array(fieldSchema).min(1) }),
});
