import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProgramCatalog } from "@/components/ProgramCatalog";
import { ProgramDetail } from "@/components/ProgramDetail";
import type { ProgramCatalogDetailResponse, ProgramCatalogListResponse } from "@/lib/types";
import { requestProgramCatalog, requestProgramDetail } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    requestProgramCatalog: vi.fn(),
    requestProgramDetail: vi.fn(),
  };
});

const baseProgram = {
  program_ref: "program.hk.hku.msc_computer_science",
  official_name: "MSc in Computer Science",
  institution_name: "The University of Hong Kong",
  region: "hong_kong" as const,
  official_program_url: "https://example.edu/program",
  target_academic_year: "2027-28" as const,
  degree_type: "taught_masters" as const,
  primary_direction: "computer_science" as const,
  secondary_directions: [],
  review_status: "domain_reviewed" as const,
  has_unresolved_fields: true,
  reviewed_at: "2026-09-03T07:43:00Z",
  candidate_version_id: "version.phase4.batch8.1.1",
  pack_ref: "pack.hk.hku.msc_computer_science.2027.v1",
  pack_schema_version: "alpha_program_pack.v1" as const,
  pack_canonical_sha256: "a".repeat(64),
  evidence_count: 1,
  coverage: { confirmed: 6, unresolved: 9, total: 15 },
};

const listPayload: ProgramCatalogListResponse = {
  schema_version: "program_catalog_list.v1",
  dataset: {
    dataset_id: "dataset.internal_alpha.2027.v1",
    target_academic_year: "2027-28",
    program_count: 2,
    data_boundary: "internal_candidate_only",
    public_publishable: false,
    manifest_sha256: "b".repeat(64),
  },
  programs: [
    baseProgram,
    {
      ...baseProgram,
      program_ref: "program.uk.manchester.msc_aerospace_engineering",
      official_name: "MSc Aerospace Engineering",
      institution_name: "The University of Manchester",
      region: "united_kingdom",
      primary_direction: "aerospace_engineering",
      candidate_version_id: "version.phase4.batch8.7.1",
    },
  ],
};

const detailPayload: ProgramCatalogDetailResponse = {
  schema_version: "program_catalog_detail.v1",
  dataset: listPayload.dataset,
  program: {
    ...baseProgram,
    fields: [{
      field_key: "requirements.language",
      label: "语言要求",
      group: "申请门槛",
      display_text: "IELTS overall 7.0",
      coverage_status: "confirmed",
      is_critical: true,
      value_schema_version: "program_requirement_field.v2",
      citations: [{
        evidence_id: "evidence.hku.language.2027.v1",
        support_scope: "direct",
        citation_order: 1,
        url: "https://example.edu/language",
        page_title: "Official entry requirements",
        excerpt: "IELTS overall 7.0",
        source_version: "2027 page",
        verified_at: "2026-09-03T07:43:00Z",
        review_due_at: "2026-10-03T07:43:00Z",
        expires_at: "2026-12-03T07:43:00Z",
        freshness: "fresh",
      }],
    }],
  },
};

describe("Program catalog", () => {
  beforeEach(() => {
    vi.mocked(requestProgramCatalog).mockResolvedValue(listPayload);
    vi.mocked(requestProgramDetail).mockResolvedValue(detailPayload);
  });

  it("searches existing programs and links to a real detail route", async () => {
    const user = userEvent.setup();
    render(<ProgramCatalog />);

    expect(await screen.findByRole("heading", { name: "MSc in Computer Science" })).toBeInTheDocument();
    expect(screen.getByText("公开 Beta 数据")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /项目数据库/ })).toHaveAttribute("href", "/programs");
    await user.type(screen.getByLabelText("搜索学校或项目"), "Manchester");
    expect(screen.queryByRole("heading", { name: "MSc in Computer Science" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "MSc Aerospace Engineering" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /查看项目详情与官网依据/ })).toHaveAttribute(
      "href",
      "/programs/program.uk.manchester.msc_aerospace_engineering",
    );
  });

  it("shows a field-level official citation on the detail page", async () => {
    render(<ProgramDetail programRef={baseProgram.program_ref} />);

    expect(await screen.findByRole("heading", { name: "MSc in Computer Science" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "语言要求" })).toBeInTheDocument();
    expect(screen.getByText("IELTS overall 7.0", { selector: ".catalog-field__value" })).toBeInTheDocument();
    await waitFor(() => expect(requestProgramDetail).toHaveBeenCalledWith(baseProgram.program_ref, expect.any(AbortSignal)));
    expect(screen.getByRole("link", { name: /查看官网原文/ })).toHaveAttribute(
      "href",
      "https://example.edu/language",
    );
  });
});
