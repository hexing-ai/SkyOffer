import { describe, expect, it } from "vitest";

import {
  APPLICATION_PROFILE_STORAGE_KEY,
  INITIAL_VALUES,
  clearApplicationProfile,
  loadApplicationProfile,
  saveApplicationProfile,
} from "@/lib/applicant-profile";

describe("applicant profile storage", () => {
  it("round-trips the versioned profile contract", () => {
    const savedAt = new Date("2026-09-04T10:00:00.000Z");
    saveApplicationProfile(
      { ...INITIAL_VALUES, institution: "示例大学", major: "自动化" },
      window.localStorage,
      savedAt,
    );

    expect(loadApplicationProfile(window.localStorage)).toEqual({
      schema_version: "applicant_profile.v1",
      saved_at: savedAt.toISOString(),
      values: { ...INITIAL_VALUES, institution: "示例大学", major: "自动化" },
    });
    clearApplicationProfile(window.localStorage);
    expect(loadApplicationProfile(window.localStorage)).toBeNull();
  });

  it("fails closed when stored data does not match the v1 schema", () => {
    window.localStorage.setItem(
      APPLICATION_PROFILE_STORAGE_KEY,
      JSON.stringify({ schema_version: "applicant_profile.v0", values: {} }),
    );

    expect(loadApplicationProfile(window.localStorage)).toBeNull();
  });
});
