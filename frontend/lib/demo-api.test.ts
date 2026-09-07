import { afterEach, expect, it, vi } from "vitest";
import type { SelectionAdviceRequest } from "@/lib/types";

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.resetModules(); });

it("rejects personal analysis in the public demo before any network request", async () => {
  vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "1");
  vi.resetModules();
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const { requestSelectionAdvice } = await import("@/lib/api");
  await expect(requestSelectionAdvice({} as SelectionAdviceRequest)).rejects.toMatchObject({ code: "DEMO_READ_ONLY" });
  expect(fetch).not.toHaveBeenCalled();
});
