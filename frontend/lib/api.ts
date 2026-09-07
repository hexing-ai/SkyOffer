import { selectionAdviceResponseSchema } from "@/lib/selection-schema";
import { BASE_PATH, DEMO_MODE } from "@/lib/demo-mode";
import { programCatalogDetailSchema, programCatalogListSchema } from "@/lib/program-catalog-schema";
import type {
  ProgramCatalogDetailResponse,
  ProgramCatalogListResponse,
  SelectionAdviceRequest,
  SelectionAdviceResponse,
} from "@/lib/types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function readJson(response: Response): Promise<unknown> {
  return response.json().catch(() => null);
}

function throwApiError(response: Response, body: unknown, fallback: string): never {
  const error = body as { error?: { code?: string; message?: string } } | null;
  throw new ApiError(
    error?.error?.message ?? fallback,
    error?.error?.code ?? "REQUEST_FAILED",
    response.headers.get("x-request-id") ?? undefined,
  );
}

export async function requestSelectionAdvice(
  payload: SelectionAdviceRequest,
  signal?: AbortSignal,
): Promise<SelectionAdviceResponse> {
  if (DEMO_MODE) throw new ApiError("公开演示不接收个人资料，请运行完整版本进行分析。", "DEMO_READ_ONLY");
  const response = await fetch("/api/v1/selection-advice", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });

  const requestId = response.headers.get("x-request-id") ?? undefined;
  const body = await readJson(response);

  if (!response.ok) {
    throwApiError(response, body, "生成失败，请稍后重试。");
  }

  const parsed = selectionAdviceResponseSchema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError("服务返回的数据格式无法识别，请稍后重试。", "INVALID_RESPONSE", requestId);
  }
  return parsed.data;
}

export async function requestProgramCatalog(signal?: AbortSignal): Promise<ProgramCatalogListResponse> {
  const response = await fetch(DEMO_MODE ? `${BASE_PATH}/demo/catalog.json` : "/api/v1/programs", { signal });
  const body = await readJson(response);
  if (!response.ok) throwApiError(response, body, "项目数据库加载失败，请稍后重试。");
  const parsed = programCatalogListSchema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError("项目数据格式无法识别，请稍后重试。", "INVALID_RESPONSE");
  }
  return parsed.data;
}

export async function requestProgramDetail(
  programRef: string,
  signal?: AbortSignal,
): Promise<ProgramCatalogDetailResponse> {
  const response = await fetch(DEMO_MODE ? `${BASE_PATH}/demo/programs/${encodeURIComponent(programRef)}.json` : `/api/v1/programs/${encodeURIComponent(programRef)}`, { signal });
  const body = await readJson(response);
  if (!response.ok) throwApiError(response, body, "项目详情加载失败，请稍后重试。");
  const parsed = programCatalogDetailSchema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError("项目详情格式无法识别，请稍后重试。", "INVALID_RESPONSE");
  }
  return parsed.data;
}
