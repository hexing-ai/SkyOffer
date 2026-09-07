import { describe, expect, it } from "vitest";

import { selectionAdviceResponseSchema } from "@/lib/selection-schema";

describe("selectionAdviceResponseSchema", () => {
  it("fails closed when a program has no field-level official citation", () => {
    const response = {
      schema_version: "selection_advice_response.v1",
      eligibility_profile: {},
      excluded_program_count: 0,
      empty_reason: null,
      disclaimer: "测试",
      meta: {
        request_id: "req_test",
        dataset_id: "alpha",
        dataset_manifest_sha256: "abc",
        model_name: "deepseek-chat",
        prompt_version: "v1",
        generated_at: "2026-09-03T00:00:00Z",
        duration_ms: 1,
      },
      results: [{
        program_ref: "program.test",
        program_name: "Test MSc",
        institution_name: "Test University",
        region: "united_kingdom",
        official_program_url: "https://example.edu/program",
        primary_direction: "computer_science",
        secondary_directions: [],
        recommendation_tier: "verify",
        recommendation_label: "待核验",
        threshold_summary: { met: 0, unmet: 0, missing_information: 1, manual_review: 0, not_applicable: 0 },
        missing_fields: ["grade"],
        high_risk_field_keys: [],
        field_judgments: [{
          field_key: "grade",
          coverage_status: "reviewed",
          status: "missing_information",
          is_critical: true,
          is_high_risk: false,
          display_text: "需要成绩信息",
          reason_codes: ["missing_grade"],
          citations: [],
        }],
        explanation: {
          program_ref: "program.test",
          summary: "待核验",
          strengths: [],
          risks: [],
          next_actions: ["补充成绩"],
        },
      }],
    };

    expect(selectionAdviceResponseSchema.safeParse(response).success).toBe(false);
  });
});
