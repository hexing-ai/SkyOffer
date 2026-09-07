import type { Metadata } from "next";

import { ProfileEditor } from "@/components/ProfileEditor";
import { DemoProfile } from "@/components/DemoProfile";
import { DEMO_MODE } from "@/lib/demo-mode";

export const metadata: Metadata = {
  title: "申请档案 · SkyOffer",
  description: "在当前浏览器中保存申请背景，并自动填入选校建议。",
};

export default function ProfilePage() {
  return DEMO_MODE ? <DemoProfile /> : <ProfileEditor />;
}
