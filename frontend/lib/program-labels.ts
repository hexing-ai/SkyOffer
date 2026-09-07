import type { Direction, ProgramCoverageStatus, Region } from "@/lib/types";

export const REGION_LABELS: Record<Region, string> = {
  hong_kong: "香港",
  united_kingdom: "英国",
};

export const DIRECTION_LABELS: Record<Direction, string> = {
  computer_science: "计算机科学",
  artificial_intelligence: "人工智能",
  aerospace_engineering: "航空工程",
  low_altitude_economy: "低空经济",
};

export const COVERAGE_LABELS: Record<ProgramCoverageStatus, string> = {
  confirmed: "官网已确认",
  manual_review: "待人工核验",
  not_yet_published: "官网尚未发布",
  not_found_in_reviewed_sources: "已核验来源未找到",
  not_applicable: "不适用",
};

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));
}
