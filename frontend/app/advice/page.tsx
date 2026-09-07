import type { Metadata } from "next";

import { SelectionPlanner } from "@/components/SelectionPlanner";
import { DemoAdvice } from "@/components/DemoAdvice";
import { DEMO_MODE } from "@/lib/demo-mode";

export const metadata: Metadata = {
  title: "选校建议 · SkyOffer",
  description: "填写学业背景与申请目标，对照官网要求，获取有依据的硕士选校建议。",
};

export default function AdvicePage() {
  return DEMO_MODE ? <DemoAdvice /> : <SelectionPlanner />;
}
