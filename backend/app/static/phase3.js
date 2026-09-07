"use strict";

const STORAGE_KEY = "skyoffer.phase3.acceptance.v1";
// Read the pre-SkyOffer key to preserve existing local acceptance sessions.
const LEGACY_STORAGE_KEY = "offerpilot.phase3.acceptance.v1";
const DATA_PREPARER = "actor.data_preparer.codex";
const DOMAIN_REVIEWER = "actor.domain_reviewer.product_owner";

const steps = [
  { id: "initialize", title: "建立 Program 与三条 Evidence", detail: "严格校验、幂等写入；不访问官方 URL。", action: "初始化本地场景" },
  { id: "v1_create", title: "创建 v1 candidate", detail: "2026–27 IELTS 7.0 / 单项 6.5，关联 E1 + E2。", action: "创建 v1" },
  { id: "v1_submit", title: "提交 v1 复核", detail: "data_preparer 提交；还不能被用户读取。", action: "提交 v1" },
  { id: "v1_publish", title: "领域复核并发布 v1", detail: "domain_reviewer 审核后，published-only 首次可见。", action: "发布 v1" },
  { id: "v2_create", title: "创建 v2 candidate", detail: "切换 2027–28 待核验，E1 替换为 E3。", action: "创建 v2" },
  { id: "v2_submit", title: "提交 v2 复核", detail: "此时用户仍只能看到 v1。", action: "提交 v2" },
  { id: "v2_publish", title: "领域复核并发布 v2", detail: "v1 superseded；用户只看到“2027–28 待核验”。", action: "发布 v2" },
  { id: "v3_create", title: "从 v1 创建 rollback v3", detail: "服务端复制 v1；base 指向 v2，历史不改写。", action: "创建 rollback v3" },
  { id: "v3_submit", title: "提交 rollback v3 复核", detail: "回滚候选仍需四眼审核，用户继续看到 v2。", action: "提交 v3" },
  { id: "v3_publish", title: "领域复核并发布 v3", detail: "v2 superseded；v3 内容 hash 应与 v1 一致。", action: "发布 v3" },
];

const evidenceBlueprints = [
  {
    slot: "e1",
    source_type: "official_program_page",
    url: "https://study.ed.ac.uk/programmes/postgraduate-taught/110-computer-science",
    page_title: "Computer Science MSc - Postgraduate taught programmes | The University of Edinburgh",
    excerpt: "IELTS Academic: total 7.0 with at least 6.5 in each component We do not accept IELTS One Skill Retake to meet our English language requirements.",
    snapshot_sha256: "b991bedc92cae1b638867cad5ff3efa88db7e33016db9b899cb86df737a40a01",
    source_version: "degree-finder-entry-2026; page states academic year 2026-27",
    review_due_at: "2026-10-01T00:00:00Z",
    expires_at: "2026-10-08T00:00:00Z",
    label: "E1 · 2026–27 直接门槛",
  },
  {
    slot: "e2",
    source_type: "official_policy_page",
    url: "https://study.ed.ac.uk/postgraduate/applying/entry-requirements/english-language",
    page_title: "English language entry requirements | Postgraduate study | The University of Edinburgh",
    excerpt: "The following English language tests must be no more than two years old on the 1st of the month your programme starts. IELTS Academic / IELTS Academic for UKVI and IELTS Academic Online. We do not accept IELTS One Skill Retake.",
    snapshot_sha256: "fd35fcf6eff4926c1544a97b07b8c57ed2ff88d6588668b70c8290f02a5d531e",
    source_version: "unversioned; page observed 2026-09-01 and copyright 2026",
    review_due_at: "2026-10-01T00:00:00Z",
    expires_at: "2026-10-08T00:00:00Z",
    label: "E2 · 校级定义与限制",
  },
  {
    slot: "e3",
    source_type: "official_program_page",
    url: "https://study.ed.ac.uk/programmes/postgraduate-taught/110-computer-science",
    page_title: "Computer Science MSc - Postgraduate taught programmes | The University of Edinburgh",
    excerpt: "These entry requirements are for the 2026-27 academic year and requirements for future academic years may differ. Entry requirements for the 2027-28 academic year will be published on 1 Oct 2026.",
    snapshot_sha256: "75e4eb1c4b571e35b5061dffe79c24087bc56de714f9408a2a90176c2388e4a2",
    source_version: "degree-finder-entry-2026; future-year notice observed 2026-09-01",
    review_due_at: "2026-10-01T00:00:00Z",
    expires_at: "2026-10-02T00:00:00Z",
    label: "E3 · 2027–28 尚未发布",
  },
];

function createToken() {
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
}

function newState() {
  return { token: createToken(), programId: null, evidence: {}, versions: {}, completed: [], lastResponse: null };
}

function loadState() {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || localStorage.getItem(LEGACY_STORAGE_KEY));
    if (stored && typeof stored.token === "string" && Array.isArray(stored.completed)) return stored;
  } catch (_error) {
    localStorage.removeItem(STORAGE_KEY);
  }
  return newState();
}

let state = loadState();
let busyStep = null;
let liveEvidence = [];
let liveVersions = [];
let liveAudit = [];
let livePublished = null;

const elements = {
  scenarioId: document.getElementById("scenarioId"),
  progressCount: document.getElementById("progressCount"),
  newScenario: document.getElementById("newScenario"),
  errorPanel: document.getElementById("errorPanel"),
  evidenceCards: document.getElementById("evidenceCards"),
  stepList: document.getElementById("stepList"),
  workflowState: document.getElementById("workflowState"),
  publishedView: document.getElementById("publishedView"),
  versionSpine: document.getElementById("versionSpine"),
  auditTimeline: document.getElementById("auditTimeline"),
  auditCount: document.getElementById("auditCount"),
  technicalLog: document.getElementById("technicalLog"),
};

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function evidenceId(slot) {
  return `evidence.phase3.${state.token}.${slot}`;
}

function idempotencyKey(step) {
  return `phase3-${state.token}-${step}-key`;
}

async function api(path, { method = "GET", body = null, key = null, allowNotPublished = false } = {}) {
  const headers = {};
  if (body !== null) headers["Content-Type"] = "application/json";
  if (key) headers["Idempotency-Key"] = key;
  const response = await fetch(path, { method, headers, body: body === null ? undefined : JSON.stringify(body) });
  const data = await response.json();
  const requestId = response.headers.get("X-Request-ID") || data?.error?.request_id || "无 request ID";
  if (!response.ok) {
    if (allowNotPublished && data?.error?.code === "PROGRAM_NOT_PUBLISHED") return { data: null, requestId };
    const error = new Error(data?.error?.message || `HTTP ${response.status}`);
    error.code = data?.error?.code || "UNKNOWN_ERROR";
    error.requestId = requestId;
    throw error;
  }
  state.lastResponse = { path, request_id: requestId, body: data };
  saveState();
  return { data, requestId };
}

function programPayload() {
  return {
    official_name: "Computer Science MSc",
    institution_name: "The University of Edinburgh",
    region: "united_kingdom",
    official_program_url: `https://study.ed.ac.uk/programmes/postgraduate-taught/110-computer-science?skyoffer_phase3_scenario=${state.token}`,
    registered_official_domain: "ed.ac.uk",
    created_by: DATA_PREPARER,
    creation_note: `Phase 3 browser acceptance scenario ${state.token}.`,
  };
}

function evidencePayload(blueprint) {
  return {
    id: evidenceId(blueprint.slot),
    program_id: state.programId,
    source_type: blueprint.source_type,
    url: blueprint.url,
    official_domain: "study.ed.ac.uk",
    page_title: blueprint.page_title,
    excerpt: blueprint.excerpt,
    snapshot_sha256: blueprint.snapshot_sha256,
    source_version: blueprint.source_version,
    captured_at: "2026-09-01T00:00:00Z",
    verified_at: "2026-09-01T00:00:00Z",
    verified_by: DOMAIN_REVIEWER,
    review_due_at: blueprint.review_due_at,
    expires_at: blueprint.expires_at,
    availability_at_verification: "available",
  };
}

function v1Field() {
  const display = "2026–27 IELTS Academic：总分至少 7.0，听说读写各项至少 6.5；本字段仅判断分数门槛，考试类型、有效期及 One Skill Retake 另行核验。";
  return {
    field_key: "requirements.language.ielts",
    value_schema_version: "program_requirement_field.v1",
    value_payload: {
      schema_version: "program_requirement_field.v1",
      applicable_academic_year: "2026-27",
      coverage: "score_threshold_only",
      requirement: {
        requirement_id: "requirement.pilot.ielts",
        requirement_type: "language",
        is_hard: true,
        applicability: null,
        rule: {
          node_id: "node.pilot.ielts.minimum",
          operator: "language_minimum",
          test_type: "ielts",
          total_min: "7.0",
          component_mins: { listening: "6.5", reading: "6.5", speaking: "6.5", writing: "6.5" },
        },
        evidence_fixture_ids: [evidenceId("e1"), evidenceId("e2")],
        display_text: display,
      },
    },
    display_text: display,
    is_critical: true,
    evidence_links: [
      { evidence_id: evidenceId("e1"), support_scope: "direct", citation_order: 1 },
      { evidence_id: evidenceId("e2"), support_scope: "definition", citation_order: 2 },
    ],
  };
}

function v2Field() {
  const display = "2027–28 IELTS 分数门槛待核验；官方页面说明将在 2026-10-01 发布，当前不得沿用 2026–27 分数。";
  return {
    field_key: "requirements.language.ielts",
    value_schema_version: "program_requirement_field.v1",
    value_payload: {
      schema_version: "program_requirement_field.v1",
      applicable_academic_year: "2027-28",
      coverage: "score_threshold_only",
      requirement: {
        requirement_id: "requirement.pilot.ielts",
        requirement_type: "language",
        is_hard: true,
        applicability: null,
        rule: { node_id: "node.pilot.ielts.pending_verification", operator: "manual_review", reason_code: "OFFICIAL_RULE_AMBIGUOUS" },
        evidence_fixture_ids: [evidenceId("e3"), evidenceId("e2")],
        display_text: display,
      },
    },
    display_text: display,
    is_critical: true,
    evidence_links: [
      { evidence_id: evidenceId("e3"), support_scope: "direct", citation_order: 1 },
      { evidence_id: evidenceId("e2"), support_scope: "definition", citation_order: 2 },
    ],
  };
}

const actions = {
  initialize: async () => {
    if (!state.programId) {
      const { data } = await api("/api/v1/internal/programs", { method: "POST", body: programPayload(), key: idempotencyKey("program") });
      state.programId = data.id;
      saveState();
    }
    for (const blueprint of evidenceBlueprints) {
      const { data } = await api("/api/v1/internal/source-evidence", { method: "POST", body: evidencePayload(blueprint), key: idempotencyKey(blueprint.slot) });
      state.evidence[blueprint.slot] = data.id;
      saveState();
    }
  },
  v1_create: async () => {
    const { data } = await api(`/api/v1/internal/programs/${state.programId}/versions`, {
      method: "POST", key: idempotencyKey("v1-create"),
      body: { base_version_id: null, fields: [v1Field()], created_by: DATA_PREPARER, creation_note: "Create reviewed 2026–27 IELTS candidate." },
    });
    state.versions.v1 = data.id;
  },
  v1_submit: async () => {
    await api(`/api/v1/internal/program-versions/${state.versions.v1}/submit`, { method: "POST", key: idempotencyKey("v1-submit"), body: { submitted_by: DATA_PREPARER, submission_note: "Submit v1 for independent domain review." } });
  },
  v1_publish: async () => {
    await api(`/api/v1/internal/program-versions/${state.versions.v1}/publish`, { method: "POST", key: idempotencyKey("v1-publish"), body: { reviewed_by: DOMAIN_REVIEWER, review_note: "v1 official evidence and structured threshold verified.", expected_current_version_id: null } });
  },
  v2_create: async () => {
    const { data } = await api(`/api/v1/internal/programs/${state.programId}/versions`, {
      method: "POST", key: idempotencyKey("v2-create"),
      body: { base_version_id: state.versions.v1, fields: [v2Field()], created_by: DATA_PREPARER, creation_note: "Create fail-closed 2027–28 pending-verification candidate." },
    });
    state.versions.v2 = data.id;
  },
  v2_submit: async () => {
    await api(`/api/v1/internal/program-versions/${state.versions.v2}/submit`, { method: "POST", key: idempotencyKey("v2-submit"), body: { submitted_by: DATA_PREPARER, submission_note: "Submit v2 pending-verification snapshot." } });
  },
  v2_publish: async () => {
    await api(`/api/v1/internal/program-versions/${state.versions.v2}/publish`, { method: "POST", key: idempotencyKey("v2-publish"), body: { reviewed_by: DOMAIN_REVIEWER, review_note: "v2 correctly fails closed for unpublished 2027–28 threshold.", expected_current_version_id: state.versions.v1 } });
  },
  v3_create: async () => {
    const { data } = await api(`/api/v1/internal/programs/${state.programId}/rollback-candidates`, {
      method: "POST", key: idempotencyKey("v3-create"),
      body: { target_version_id: state.versions.v1, expected_current_version_id: state.versions.v2, created_by: DATA_PREPARER, creation_note: "Create reviewed rollback candidate restoring v1 content." },
    });
    state.versions.v3 = data.id;
  },
  v3_submit: async () => {
    await api(`/api/v1/internal/program-versions/${state.versions.v3}/submit`, { method: "POST", key: idempotencyKey("v3-submit"), body: { submitted_by: DATA_PREPARER, submission_note: "Submit rollback v3 for independent review." } });
  },
  v3_publish: async () => {
    await api(`/api/v1/internal/program-versions/${state.versions.v3}/publish`, { method: "POST", key: idempotencyKey("v3-publish"), body: { reviewed_by: DOMAIN_REVIEWER, review_note: "Rollback v3 content and lineage verified.", expected_current_version_id: state.versions.v2 } });
  },
};

function textElement(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = value;
  return element;
}

function renderEvidence() {
  elements.evidenceCards.replaceChildren();
  for (const blueprint of evidenceBlueprints) {
    const record = liveEvidence.find(item => item.id === evidenceId(blueprint.slot));
    const card = document.createElement("article");
    card.className = `evidence-card${blueprint.slot === "e3" ? " pending" : ""}`;
    const header = document.createElement("header");
    const titleWrap = document.createElement("div");
    titleWrap.append(textElement("h3", "", blueprint.label), textElement("p", "source-type", blueprint.source_type));
    const freshness = textElement("span", `freshness ${record?.freshness || ""}`, record?.freshness || "待写入");
    header.append(titleWrap, freshness);
    const quote = document.createElement("blockquote");
    quote.textContent = blueprint.excerpt;
    const meta = document.createElement("div");
    meta.className = "evidence-meta";
    const link = document.createElement("a");
    link.href = blueprint.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = blueprint.url;
    meta.append(link, textElement("span", "", `snapshot ${blueprint.snapshot_sha256}`), textElement("span", "", `verified ${record?.verified_at || "2026-09-01 · 待写入"}`));
    card.append(header, quote, meta);
    elements.evidenceCards.append(card);
  }
}

function renderSteps() {
  elements.stepList.replaceChildren();
  const nextIndex = steps.findIndex(step => !state.completed.includes(step.id));
  steps.forEach((step, index) => {
    const done = state.completed.includes(step.id);
    const current = index === nextIndex;
    const item = document.createElement("li");
    item.className = `step-item${done ? " done" : ""}${current ? " current" : ""}`;
    item.append(textElement("span", "step-marker", ""));
    const copy = document.createElement("div");
    copy.className = "step-copy";
    copy.append(textElement("h3", "", step.title), textElement("p", "", step.detail));
    const button = textElement("button", `step-button${done ? " done" : ""}`, done ? "已完成" : busyStep === step.id ? "执行中…" : step.action);
    button.type = "button";
    button.disabled = done || !current || busyStep !== null;
    button.dataset.step = step.id;
    button.addEventListener("click", () => runStep(step.id));
    item.append(copy, button);
    elements.stepList.append(item);
  });
  elements.progressCount.textContent = String(state.completed.length);
  if (state.completed.length === steps.length) {
    elements.workflowState.className = "state-badge complete";
    elements.workflowState.textContent = "闭环完成";
  } else if (state.completed.length > 0) {
    elements.workflowState.className = "state-badge active";
    elements.workflowState.textContent = `进行到 ${state.completed.length + 1} / ${steps.length}`;
  } else {
    elements.workflowState.className = "state-badge idle";
    elements.workflowState.textContent = "等待初始化";
  }
}

function renderPublished() {
  elements.publishedView.replaceChildren();
  if (!state.programId) {
    elements.publishedView.className = "empty-state";
    elements.publishedView.textContent = "初始化后，此处通过公开 API 读取；candidate 与 pending_review 不会出现。";
    return;
  }
  if (!livePublished) {
    elements.publishedView.className = "empty-state";
    elements.publishedView.textContent = "PROGRAM_NOT_PUBLISHED：当前没有用户可见版本。";
    return;
  }
  elements.publishedView.className = "published-fact";
  const field = livePublished.fields[0];
  const year = field.value_payload.applicable_academic_year;
  elements.publishedView.append(
    textElement("span", "year", `v${livePublished.version_no} · ${year} · published`),
    textElement("p", "", field.display_text),
    textElement("span", "hash", `content ${livePublished.content_sha256}`),
    textElement("span", "hash", `${field.evidence.length} 条字段级官方引用 · version ${livePublished.version_id}`),
  );
}

function renderVersions() {
  elements.versionSpine.replaceChildren();
  if (!liveVersions.length) {
    elements.versionSpine.className = "version-spine empty-state";
    elements.versionSpine.textContent = "尚无版本。";
    return;
  }
  elements.versionSpine.className = "version-spine";
  for (const version of liveVersions) {
    const node = document.createElement("div");
    node.className = "version-node";
    const copy = document.createElement("div");
    const lineage = [];
    if (version.base_version_id) lineage.push(`base ${version.base_version_id}`);
    if (version.rollback_of_version_id) lineage.push(`rollback_of ${version.rollback_of_version_id}`);
    if (!lineage.length) lineage.push("initial snapshot");
    copy.append(
      textElement("p", "", version.id),
      ...lineage.map(value => textElement("small", "", value)),
      textElement("small", "", `hash ${version.content_sha256}`),
    );
    node.append(textElement("span", "version-number", `v${version.version_no}`), copy, textElement("span", `version-status ${version.status}`, version.status));
    elements.versionSpine.append(node);
  }
}

function renderAudit() {
  elements.auditTimeline.replaceChildren();
  elements.auditCount.textContent = `${liveAudit.length} events`;
  if (!liveAudit.length) {
    elements.auditTimeline.className = "audit-timeline empty-state";
    elements.auditTimeline.textContent = "Program 创建后开始记录不可变事件。";
    return;
  }
  elements.auditTimeline.className = "audit-timeline";
  for (const event of liveAudit) {
    const row = document.createElement("div");
    row.className = "audit-event";
    const actor = document.createElement("div");
    actor.append(textElement("strong", "", event.event_type), textElement("p", "", event.actor_role));
    const reason = document.createElement("div");
    reason.append(textElement("code", "", event.request_id), textElement("p", "", event.reason || event.event_payload.entity_type || "—"));
    row.append(textElement("code", "", event.version_id || "PROGRAM"), actor, reason);
    elements.auditTimeline.append(row);
  }
}

function render() {
  elements.scenarioId.textContent = state.programId || `scenario.${state.token} · 尚未写入`;
  elements.technicalLog.textContent = state.lastResponse ? JSON.stringify(state.lastResponse, null, 2) : "尚未发送请求";
  renderEvidence();
  renderSteps();
  renderPublished();
  renderVersions();
  renderAudit();
}

async function refreshLiveState() {
  if (!state.programId) return;
  const [evidence, versions, audit, published] = await Promise.all([
    api(`/api/v1/internal/programs/${state.programId}/source-evidence`),
    api(`/api/v1/internal/programs/${state.programId}/versions`),
    api(`/api/v1/internal/programs/${state.programId}/audit-events`),
    api(`/api/v1/programs/${state.programId}/published`, { allowNotPublished: true }),
  ]);
  liveEvidence = evidence.data.evidence;
  liveVersions = versions.data.versions;
  liveAudit = audit.data.events;
  livePublished = published.data;
}

async function runStep(stepId) {
  elements.errorPanel.hidden = true;
  busyStep = stepId;
  renderSteps();
  try {
    await actions[stepId]();
    if (!state.completed.includes(stepId)) state.completed.push(stepId);
    saveState();
    await refreshLiveState();
  } catch (error) {
    elements.errorPanel.hidden = false;
    elements.errorPanel.textContent = `${error.code || "CLIENT_ERROR"} / ${error.requestId || "无 request ID"}：${error.message}。修正后可用同一步骤重试，幂等键不会重复写入。`;
  } finally {
    busyStep = null;
    render();
  }
}

elements.newScenario.addEventListener("click", () => {
  if (!window.confirm("将切换到新的独立场景；当前数据库历史会保留且不会被删除。继续吗？")) return;
  state = newState();
  liveEvidence = [];
  liveVersions = [];
  liveAudit = [];
  livePublished = null;
  saveState();
  elements.errorPanel.hidden = true;
  render();
});

render();
if (state.programId) {
  refreshLiveState().then(render).catch(error => {
    elements.errorPanel.hidden = false;
    elements.errorPanel.textContent = `${error.code || "RESTORE_FAILED"} / ${error.requestId || "无 request ID"}：无法恢复当前场景，请确认本地服务与数据库仍指向同一环境。`;
  });
}
