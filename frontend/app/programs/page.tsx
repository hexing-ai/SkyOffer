import type { Metadata } from "next";

import { ProgramCatalog } from "@/components/ProgramCatalog";

export const metadata: Metadata = {
  title: "项目数据库 · SkyOffer",
  description: "搜索授课型硕士项目并查看字段级官网依据。",
};

export default function ProgramsPage() {
  return <ProgramCatalog />;
}
