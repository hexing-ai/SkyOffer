import type { Metadata } from "next";

import { ProgramDetail } from "@/components/ProgramDetail";
import programRefs from "@/demo/program-refs.json";

export function generateStaticParams() {
  return programRefs.map((program_ref) => ({ program_ref }));
}

export const metadata: Metadata = {
  title: "项目详情 · SkyOffer",
  description: "查看项目申请门槛、核验日期、数据版本和字段级官网依据。",
};

export default async function ProgramDetailPage({
  params,
}: {
  params: Promise<{ program_ref: string }>;
}) {
  const { program_ref: programRef } = await params;
  return <ProgramDetail programRef={programRef} />;
}
