"use strict";

const params = new URLSearchParams(window.location.search);
const state = {
  datasetId: params.get("dataset") || "dataset.alpha.synthetic.2027.v1",
  requestedPackRef: params.get("pack"),
  programs: [],
  detail: null,
  selectedFieldKey: null,
  reviewedFields: new Set(),
  busy: false,
};

const elements = Object.fromEntries([
  "datasetId", "manifestHash", "programPosition", "versionStatus", "errorPanel",
  "successPanel", "reviewedCount", "fieldRuler", "programName", "institutionName",
  "packRef", "programRef", "region", "direction", "contentHash", "fieldNav",
  "fieldEmpty", "fieldContent", "fieldKey", "fieldHeading", "criticalBadge",
  "coverageBadge", "fieldDisplay", "diffType", "diffBefore", "diffAfter",
  "fieldPayload", "markReviewed", "evidenceList", "gateList", "preflightBadge",
  "reviewNote", "decisionHint", "rejectButton", "publishButton", "technicalLog",
].map(id => [id, document.getElementById(id)]));

const statusLabels = {
  candidate: "Candidate",
  pending_review: "待领域复核",
  published: "已发布",
  rejected: "已驳回",
  superseded: "已替代",
  missing: "尚未导入",
};

const directionLabels = {
  computer_science: "计算机科学",
  artificial_intelligence: "人工智能",
  aerospace_engineering: "航空工程",
  low_altitude_economy: "低空经济",
};

function textElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
}

function setLog(payload) {
  elements.technicalLog.textContent = JSON.stringify(payload, null, 2);
}

function showError(message) {
  elements.errorPanel.textContent = message;
  elements.errorPanel.hidden = false;
}

function clearPanels() {
  elements.errorPanel.hidden = true;
  elements.successPanel.hidden = true;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  setLog({ status: response.status, path, payload });
  if (!response.ok) {
    const code = payload?.error?.code || "REQUEST_FAILED";
    const message = payload?.error?.message || `请求失败（HTTP ${response.status}）`;
    throw new Error(`${code}：${message}`);
  }
  return payload;
}

function idempotencyKey(action) {
  const version = state.detail?.version?.version_id || "unknown";
  return `phase4-page-${action}-${version}-${crypto.randomUUID()}`;
}

function storageKey() {
  return `skyoffer.phase4.reviewed.${state.detail?.version?.version_id || "none"}`;
}

function restoreReviewed() {
  try {
    // Preserve review selections saved by the pre-SkyOffer local tool.
    const legacyKey = storageKey().replace(/^skyoffer\./, "offerpilot.");
    const values = JSON.parse(sessionStorage.getItem(storageKey()) || sessionStorage.getItem(legacyKey) || "[]");
    state.reviewedFields = new Set(Array.isArray(values) ? values : []);
  } catch (_error) {
    state.reviewedFields = new Set();
  }
}

function persistReviewed() {
  sessionStorage.setItem(storageKey(), JSON.stringify([...state.reviewedFields].sort()));
}

function criticalFields() {
  return (state.detail?.fields || []).filter(field => field.is_critical);
}

function allCriticalReviewed() {
  const fields = criticalFields();
  return fields.length > 0 && fields.every(field => state.reviewedFields.has(field.field_key));
}

function renderDossier() {
  const detail = state.detail;
  elements.datasetId.textContent = detail.dataset_id;
  elements.manifestHash.textContent = detail.manifest_sha256;
  const index = state.programs.findIndex(item => item.pack_ref === detail.program.pack_ref);
  elements.programPosition.textContent = `${index + 1} / ${state.programs.length}`;
  elements.versionStatus.textContent = statusLabels[detail.version.status] || detail.version.status;
  elements.versionStatus.className = `status-chip ${detail.version.status}`;
  elements.programName.textContent = detail.program.official_name;
  elements.institutionName.textContent = detail.program.institution_name;
  elements.packRef.textContent = detail.program.pack_ref;
  elements.programRef.textContent = detail.program.program_ref;
  elements.region.textContent = detail.program.region;
  elements.direction.textContent = [
    directionLabels[detail.program.primary_direction] || detail.program.primary_direction,
    ...detail.program.secondary_directions.map(item => directionLabels[item] || item),
  ].join(" · ");
  elements.contentHash.textContent = detail.version.content_sha256;
}

function selectField(fieldKey) {
  state.selectedFieldKey = fieldKey;
  renderRuler();
  renderFieldNav();
  renderSelectedField();
}

function renderRuler() {
  elements.fieldRuler.replaceChildren();
  state.detail.fields.forEach((field, index) => {
    const button = document.createElement("button");
    const classes = ["ruler-mark"];
    if (field.field_key === state.selectedFieldKey) classes.push("active");
    if (state.reviewedFields.has(field.field_key)) classes.push("reviewed");
    button.className = classes.join(" ");
    button.type = "button";
    button.title = `${field.display_label} · ${field.field_key}`;
    button.setAttribute("aria-label", button.title);
    button.append(textElement("span", "", String(index + 1).padStart(2, "0")));
    button.addEventListener("click", () => selectField(field.field_key));
    elements.fieldRuler.append(button);
  });
}

function renderFieldNav() {
  elements.fieldNav.replaceChildren();
  state.detail.fields.forEach(field => {
    const button = document.createElement("button");
    const classes = ["field-nav-button"];
    if (field.field_key === state.selectedFieldKey) classes.push("active");
    if (state.reviewedFields.has(field.field_key)) classes.push("reviewed");
    button.className = classes.join(" ");
    button.type = "button";
    button.append(
      textElement("span", "", field.display_label),
      textElement("small", "", field.is_critical ? "critical" : "supporting"),
    );
    button.addEventListener("click", () => selectField(field.field_key));
    elements.fieldNav.append(button);
  });
}

function renderEvidence(field) {
  elements.evidenceList.replaceChildren();
  field.evidence.forEach(item => {
    const card = document.createElement("article");
    card.className = "evidence-card";
    const header = document.createElement("header");
    const heading = document.createElement("div");
    heading.append(
      textElement("h3", "", item.page_title),
      textElement("p", "field-key", `${item.reviewed_source_role} · ${item.support_scope}`),
    );
    header.append(heading, textElement("span", `freshness ${item.freshness}`, item.freshness));
    const quote = document.createElement("blockquote");
    quote.textContent = item.excerpt;
    const meta = document.createElement("div");
    meta.className = "evidence-meta";
    const link = document.createElement("a");
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = item.url;
    meta.append(
      link,
      textElement("span", "", `snapshot ${item.snapshot_sha256}`),
      textElement("span", "", `hash scope ${item.hash_scope}`),
      textElement("span", "", `verified ${item.verified_at} · ${item.verified_by}`),
      textElement("span", "", `review due ${item.review_due_at}`),
    );
    card.append(header, quote, meta);
    elements.evidenceList.append(card);
  });
}

function diffText(side) {
  if (!side) return "不存在";
  return `${side.display_text}\n${side.value_sha256}`;
}

function renderSelectedField() {
  const field = state.detail.fields.find(item => item.field_key === state.selectedFieldKey);
  if (!field) {
    elements.fieldEmpty.hidden = false;
    elements.fieldContent.hidden = true;
    return;
  }
  elements.fieldEmpty.hidden = true;
  elements.fieldContent.hidden = false;
  elements.fieldKey.textContent = field.field_key;
  elements.fieldHeading.textContent = field.display_label;
  elements.criticalBadge.textContent = field.is_critical ? "critical" : "supporting";
  elements.coverageBadge.textContent = field.coverage_status;
  elements.fieldDisplay.textContent = field.display_text;
  elements.diffType.textContent = field.diff.change_type;
  elements.diffBefore.textContent = diffText(field.diff.before);
  elements.diffAfter.textContent = diffText(field.diff.after);
  elements.fieldPayload.textContent = JSON.stringify(field.value_payload, null, 2);
  const reviewed = state.reviewedFields.has(field.field_key);
  elements.markReviewed.textContent = reviewed ? "已核对 · 点击撤销" : "标记本字段已核对";
  elements.markReviewed.className = `mark-button${reviewed ? " reviewed" : ""}`;
  renderEvidence(field);
}

function renderGates() {
  elements.gateList.replaceChildren();
  state.detail.gates.forEach(gate => {
    const item = document.createElement("article");
    item.className = "gate-item";
    item.append(
      textElement("span", `gate-status ${gate.status}`, gate.status),
      textElement("h3", "", gate.label),
      textElement("p", "", gate.detail),
    );
    elements.gateList.append(item);
  });
  const blocked = state.detail.gates.some(gate => gate.blocking);
  if (blocked) {
    elements.preflightBadge.textContent = "存在阻塞门禁";
    elements.preflightBadge.className = "preflight-badge blocked";
  } else if (state.detail.preflight_ready) {
    elements.preflightBadge.textContent = "可进入人工发布决定";
    elements.preflightBadge.className = "preflight-badge ready";
  } else {
    elements.preflightBadge.textContent = "当前版本不可发布";
    elements.preflightBadge.className = "preflight-badge pending";
  }
}

function renderDecision() {
  const criticalTotal = criticalFields().length;
  const reviewedCritical = criticalFields().filter(field => state.reviewedFields.has(field.field_key)).length;
  elements.reviewedCount.textContent = `${reviewedCritical} / ${criticalTotal}`;
  const hasNote = elements.reviewNote.value.trim().length > 0;
  const allReviewed = allCriticalReviewed();
  elements.publishButton.disabled = !(
    state.detail.can_publish && allReviewed && hasNote && !state.busy
  );
  elements.rejectButton.disabled = !(state.detail.can_reject && hasNote && !state.busy);
  if (state.detail.version.status === "published") {
    elements.decisionHint.textContent = "该版本已经发布；页面已刷新发布指针与四眼审核门禁。";
  } else if (state.detail.version.status === "rejected") {
    elements.decisionHint.textContent = "该版本已经驳回；它不会进入 Published-only 读取。";
  } else if (!allReviewed) {
    elements.decisionHint.textContent = `还需核对 ${criticalTotal - reviewedCritical} 个关键字段；发现问题可随时填写说明并驳回。`;
  } else if (!hasNote) {
    elements.decisionHint.textContent = "关键字段已核对；填写领域复核说明后才能改变状态。";
  } else {
    elements.decisionHint.textContent = "人工核对与服务端门禁均已就绪，请明确选择发布或驳回。";
  }
}

function render() {
  renderDossier();
  renderRuler();
  renderFieldNav();
  renderSelectedField();
  renderGates();
  renderDecision();
}

async function loadDetail(packRef, { preserveReviewed = true } = {}) {
  const encodedDataset = encodeURIComponent(state.datasetId);
  const encodedPack = encodeURIComponent(packRef);
  state.detail = await api(
    `/api/v1/internal/alpha-datasets/${encodedDataset}/programs/${encodedPack}`,
  );
  if (!preserveReviewed) state.reviewedFields = new Set();
  restoreReviewed();
  state.selectedFieldKey = state.selectedFieldKey || state.detail.fields[0]?.field_key;
  render();
}

async function initialize() {
  clearPanels();
  try {
    const encodedDataset = encodeURIComponent(state.datasetId);
    const listing = await api(
      `/api/v1/internal/alpha-datasets/${encodedDataset}/programs?offset=0&limit=30`,
    );
    state.programs = listing.programs;
    if (!state.programs.length) throw new Error("该数据集没有可质检项目。");
    const requested = state.programs.find(item => item.pack_ref === state.requestedPackRef);
    const pending = state.programs.find(item => item.status === "pending_review");
    const versioned = state.programs.find(item => item.version_id);
    await loadDetail((requested || pending || versioned || state.programs[0]).pack_ref, { preserveReviewed: false });
  } catch (error) {
    showError(error.message);
  }
}

async function decide(action) {
  if (state.busy) return;
  clearPanels();
  state.busy = true;
  renderDecision();
  const version = state.detail.version;
  const note = elements.reviewNote.value.trim();
  const path = `/api/v1/internal/program-versions/${encodeURIComponent(version.version_id)}/${action}`;
  const body = {
    reviewed_by: state.detail.reviewer_actor,
    review_note: note,
  };
  if (action === "publish") {
    body.expected_current_version_id = state.detail.current_published_version_id;
  }
  try {
    await api(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey(action),
      },
      body: JSON.stringify(body),
    });
    elements.successPanel.textContent = action === "publish" ? "Published：版本已通过人工复核并发布。" : "Rejected：版本已驳回，未改变 Published-only 读取。";
    elements.successPanel.hidden = false;
    await loadDetail(state.detail.program.pack_ref);
  } catch (error) {
    showError(error.message);
  } finally {
    state.busy = false;
    renderDecision();
  }
}

elements.markReviewed.addEventListener("click", () => {
  const key = state.selectedFieldKey;
  if (!key) return;
  if (state.reviewedFields.has(key)) state.reviewedFields.delete(key);
  else state.reviewedFields.add(key);
  persistReviewed();
  renderRuler();
  renderFieldNav();
  renderSelectedField();
  renderDecision();
});
elements.reviewNote.addEventListener("input", renderDecision);
elements.publishButton.addEventListener("click", () => decide("publish"));
elements.rejectButton.addEventListener("click", () => decide("reject"));

initialize();
