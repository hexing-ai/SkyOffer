import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { buildPayload, INITIAL_VALUES, SelectionPlanner } from "@/components/SelectionPlanner";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, requestSelectionAdvice: vi.fn(() => new Promise(() => undefined)) };
});

describe("SelectionPlanner", () => {
  it("renders a single-workspace first step without an empty result panel", () => {
    render(<SelectionPlanner />);

    expect(screen.getByRole("heading", { name: "选校建议" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "填写学业背景" })).toBeInTheDocument();
    expect(screen.getByText(/当前覆盖 20 个项目/)).toBeInTheDocument();
    expect(screen.getByText(/20 项公开 Beta/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "继续" })).toBeEnabled();
    expect(screen.queryByText("2027 入学 · 授课型硕士")).not.toBeInTheDocument();
    expect(screen.queryByText("填写信息后查看建议")).not.toBeInTheDocument();
  });

  it("keeps values while moving through the three form steps", async () => {
    const user = userEvent.setup();
    render(<SelectionPlanner />);

    await user.type(screen.getByLabelText(/本科院校/), "示例大学");
    await user.type(screen.getByLabelText(/本科专业/), "自动化");
    await user.type(screen.getByLabelText(/当前成绩/), "85");
    await user.click(screen.getByRole("button", { name: "继续" }));

    expect(screen.getByRole("heading", { name: "填写语言与经历" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "继续" }));

    expect(screen.getByRole("heading", { name: "选择申请目标" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成选校建议" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /学业背景/ }));
    expect(screen.getByDisplayValue("示例大学")).toBeInTheDocument();
  });

  it("replaces the form with a full-width loading state after submission", async () => {
    const user = userEvent.setup();
    render(<SelectionPlanner />);

    await user.type(screen.getByLabelText(/本科院校/), "示例大学");
    await user.type(screen.getByLabelText(/本科专业/), "自动化");
    await user.type(screen.getByLabelText(/当前成绩/), "85");
    await user.click(screen.getByRole("button", { name: "继续" }));
    await user.click(screen.getByRole("button", { name: "继续" }));
    await user.click(screen.getByRole("button", { name: "生成选校建议" }));

    expect(await screen.findByRole("heading", { name: "正在分析申请条件" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "选择申请目标" })).not.toBeInTheDocument();
  });

  it("builds the backend v1 contract without guessing optional facts", () => {
    const payload = buildPayload({
      ...INITIAL_VALUES,
      institution: "示例大学",
      major: "自动化",
      gradeValue: "85",
    });

    expect(payload.schema_version).toBe("selection_advice_request.v1");
    expect(payload.profile.target_regions).toEqual(["hong_kong", "united_kingdom"]);
    expect(payload.profile.language_scores).toEqual([]);
    expect(payload.rule_facts.work_experience_months).toBeNull();
    expect(payload.rule_facts.institution_recognition).toBe("unknown");
  });

  it("rejects an empty target scope before any request is sent", () => {
    expect(() => buildPayload({ ...INITIAL_VALUES, targetDirections: [] })).toThrow(
      "请至少选择一个目标地区和一个专业方向。",
    );
  });
});
