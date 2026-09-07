import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ProfileEditor } from "@/components/ProfileEditor";
import { SelectionPlanner } from "@/components/SelectionPlanner";
import { loadApplicationProfile } from "@/lib/applicant-profile";

describe("application profile Lite", () => {
  it("saves locally and automatically fills the selection form", async () => {
    const user = userEvent.setup();
    const view = render(<ProfileEditor />);

    await user.type(screen.getByLabelText("本科院校"), "示例航空大学");
    await user.type(screen.getByLabelText("本科专业"), "航空工程");
    await user.type(screen.getByLabelText("当前成绩"), "86");
    await user.click(screen.getByRole("button", { name: "保存申请档案" }));

    await waitFor(() => expect(loadApplicationProfile()?.values.institution).toBe("示例航空大学"));
    expect(screen.getByRole("link", { name: /生成选校建议/ })).toHaveAttribute("href", "/advice");

    view.unmount();
    render(<SelectionPlanner />);

    expect(await screen.findByText("已自动填入申请档案")).toBeInTheDocument();
    expect(screen.getByDisplayValue("示例航空大学")).toBeInTheDocument();
    expect(screen.getByDisplayValue("航空工程")).toBeInTheDocument();
    expect(screen.getByDisplayValue("86")).toBeInTheDocument();
  });
});
