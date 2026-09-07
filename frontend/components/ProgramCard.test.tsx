import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ProgramCard } from "@/components/ProgramCard";
import type { ProgramAdvice } from "@/lib/types";

const PROGRAM: ProgramAdvice = {
  program_ref: "program.hk.hku.msc_computer_science",
  program_name: "MSc in Computer Science",
  institution_name: "The University of Hong Kong",
  region: "hong_kong",
  official_program_url: "https://example.edu/program",
  primary_direction: "computer_science",
  secondary_directions: [],
  recommendation_tier: "target",
  recommendation_label: "主申",
  threshold_summary: {
    met: 1,
    unmet: 0,
    missing_information: 0,
    manual_review: 1,
    not_applicable: 0,
  },
  missing_fields: [],
  high_risk_field_keys: [],
  field_judgments: [],
  historical_reference: {
    academic_year: "2026-27",
    availability: "evaluable",
    reference_status: "partial",
    reference_label: "部分满足",
    summary: { met: 1, unmet: 0, missing_information: 0, manual_review: 1 },
    field_judgments: [{
      field_key: "requirements.degree",
      status: "met",
      display_text: "2026/27：须持有学士学位。",
      reason_code: "ENUM_ALLOWED",
      citations: [{
        source_id: "history.hku.cs",
        field_key: "requirements.degree",
        academic_year: "2026-27",
        url: "https://example.edu/history",
        page_title: "2026 entry requirements",
        excerpt: "Applicants shall hold a Bachelor's degree.",
        source_version: "2026/27 official page",
        verified_at: "2026-09-04T00:00:00Z",
        snapshot_sha256: "a".repeat(64),
      }],
    }],
    limitation_note: null,
    disclaimer: "以下仅按 2026/27 官方门槛计算历史参考，不代表 2027/28 要求，也不参与 2027 推荐分层。",
  },
  explanation: {
    program_ref: "program.hk.hku.msc_computer_science",
    summary: "测试说明",
    strengths: [],
    risks: [],
    next_actions: [],
  },
};

describe("ProgramCard", () => {
  it("links selection results to the corresponding catalog detail", () => {
    render(<ProgramCard program={PROGRAM} index={0} />);

    expect(screen.getByRole("link", { name: /查看项目详情/ })).toHaveAttribute(
      "href",
      "/programs/program.hk.hku.msc_computer_science",
    );
  });

  it("labels historical results as non-decisive and exposes their citations", async () => {
    const user = userEvent.setup();
    render(<ProgramCard program={PROGRAM} index={0} />);

    expect(screen.getByText("2026/27 官方历史参考")).toBeInTheDocument();
    expect(screen.getByText("不参与 2027 推荐分层")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "查看历史门槛" }));
    expect(screen.getByText(/以下仅按 2026\/27 官方门槛/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /2026 entry requirements/ })).toHaveAttribute(
      "href",
      "https://example.edu/history",
    );
  });
});
