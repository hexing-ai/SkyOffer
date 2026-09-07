"use strict";

const $ = id => document.getElementById(id);
const form = $("advice-form");
const output = document.querySelector(".output-panel");
const tierLabels = { relative_safe: "相对稳妥", target: "主申", sprint: "冲刺", verify: "待核验" };
const statusLabels = { met: "满足", unmet: "未满足", missing_information: "信息缺失", manual_review: "人工核验", not_applicable: "不适用" };

function selected(name) {
  return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(item => item.value);
}
function optionalNumber(id) {
  const value = $(id).value.trim();
  return value === "" ? null : Number(value);
}
function triState(id) {
  const value = $(id).value;
  return value === "" ? null : value === "true";
}
function lines(id) {
  return $(id).value.split("\n").map(item => item.trim()).filter(Boolean);
}

function buildPayload() {
  const targetRegions = selected("region");
  const targetDirections = selected("direction");
  if (!targetRegions.length || !targetDirections.length) throw new Error("请至少选择一个目标地区和一个专业方向。");
  const languageType = $("language-type").value;
  const languageTotal = optionalNumber("language-total");
  if ((languageType && languageTotal === null) || (!languageType && languageTotal !== null)) throw new Error("语言考试类型和总分需要同时填写。");
  const languageScores = [];
  if (languageType) {
    const components = {};
    [["listening","listening"],["reading","reading"],["writing","writing"],["speaking","speaking"]].forEach(([id,key]) => {
      const value = optionalNumber(id); if (value !== null) components[key] = value;
    });
    languageScores.push({ test_type: languageType, total_score: languageTotal, component_scores: components, test_date: null });
  }
  const title = $("experience-title").value.trim();
  const description = $("experience-description").value.trim();
  if ((title && !description) || (!title && description)) throw new Error("代表经历的标题和具体内容需要同时填写。");
  return {
    schema_version: "selection_advice_request.v1",
    profile: {
      schema_version: "applicant_analysis_input.v1",
      request_language: "zh-CN",
      education_status: $("education-status").value,
      graduation_year: Number($("graduation-year").value),
      undergraduate_institution: $("institution").value.trim(),
      undergraduate_major: $("major").value.trim(),
      degree_type: $("degree-type").value.trim(),
      grading_scale: Number($("grading-scale").value),
      grade_value: Number($("grade-value").value),
      core_courses: lines("courses"),
      language_scores: languageScores,
      experiences: title ? [{ type: "project", title, description }] : [],
      target_regions: targetRegions,
      target_directions: targetDirections,
      career_goal: $("career-goal").value.trim() || null,
      budget_note: null,
    },
    rule_facts: {
      institution_recognition: $("institution-recognition").value,
      work_experience_months: optionalNumber("work-months"),
      materials: { portfolio: triState("portfolio"), interview: triState("interview"), recommendation_letters: triState("recommendation") },
    },
  };
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function list(title, values) {
  const box = el("div"); box.append(el("h4", "", title));
  const ul = el("ul"); (values.length ? values : ["暂无"]).forEach(value => ul.append(el("li", "", value))); box.append(ul); return box;
}
function signal(status, count) {
  const box = el("div", `signal ${status}`); box.append(el("b", "", String(count)), el("span", "", statusLabels[status])); return box;
}
function citationCard(item) {
  const card = el("div", "citation");
  const quote = el("blockquote", "", item.excerpt);
  const link = el("a", "", `${item.page_title} ↗`); link.href = item.url; link.target = "_blank"; link.rel = "noreferrer";
  card.append(quote, link, el("small", "", `核验于 ${new Date(item.verified_at).toLocaleDateString("zh-CN")} · ${item.source_version} · ${item.freshness}`));
  return card;
}
function evidenceDrawer(program) {
  const drawer = el("div", "evidence-drawer"); drawer.hidden = true;
  program.field_judgments.forEach(field => {
    const detail = el("details", "field-record");
    const summary = el("summary");
    summary.append(el("span", "field-key", field.field_key), el("span", `status-pill ${field.status}`, statusLabels[field.status] || field.status), el("span", "coverage-pill", field.coverage_status));
    detail.append(summary, el("p", "field-copy", field.display_text));
    field.citations.forEach(item => detail.append(citationCard(item)));
    drawer.append(detail);
  });
  return drawer;
}
function programCard(program) {
  const card = el("article", "program-card"); card.dataset.tier = program.recommendation_tier;
  const main = el("div", "program-main"); const top = el("div", "program-top"); const identity = el("div");
  identity.append(el("span", "field-key", program.primary_direction), el("h3", "", program.program_name), el("p", "institution", program.institution_name));
  top.append(identity, el("span", "tier-badge", program.recommendation_label));
  const signals = el("div", "signal-grid");
  ["met","unmet","missing_information","manual_review","not_applicable"].forEach(key => signals.append(signal(key, program.threshold_summary[key])));
  const columns = el("div", "program-columns"); columns.append(list("当前优势", program.explanation.strengths), list("风险与待办", [...program.explanation.risks, ...program.explanation.next_actions]));
  const actions = el("div", "program-actions");
  const official = el("a", "", "打开项目官网 ↗"); official.href = program.official_program_url; official.target = "_blank"; official.rel = "noreferrer";
  const toggle = el("button", "evidence-toggle", `查看 ${program.field_judgments.length} 个字段与官网引用`); toggle.type = "button";
  const drawer = evidenceDrawer(program);
  toggle.addEventListener("click", () => { drawer.hidden = !drawer.hidden; toggle.textContent = drawer.hidden ? `查看 ${program.field_judgments.length} 个字段与官网引用` : "收起官网引用"; });
  actions.append(toggle, official); main.append(top, el("p", "program-summary", program.explanation.summary), signals, columns, actions); card.append(main, drawer); return card;
}

function render(data) {
  $("result-list").replaceChildren(...data.results.map(programCard));
  const counts = { relative_safe:0, target:0, sprint:0, verify:0 }; data.results.forEach(item => counts[item.recommendation_tier]++);
  $("tier-summary").replaceChildren(...Object.keys(counts).map(key => { const box = el("div", "summary-cell"); box.append(el("b", "", String(counts[key])), el("span", "", tierLabels[key])); return box; }));
  $("dataset-meta").textContent = `${data.results.length} 项匹配 · ${data.excluded_program_count} 项因地区或方向未进入 · 数据版本 ${data.meta.dataset_manifest_sha256.slice(0,12)}`;
  $("result-disclaimer").textContent = data.disclaimer;
  $("empty-state").hidden = true; $("loading-state").hidden = true; $("results-state").hidden = false; output.setAttribute("aria-busy", "false");
  if (!data.results.length) { $("result-list").append(el("div", "message", data.empty_reason)); }
}

async function submit(event) {
  event.preventDefault(); $("form-error").hidden = true;
  let payload; try { payload = buildPayload(); } catch (error) { $("form-error").textContent = error.message; $("form-error").hidden = false; return; }
  $("submit-button").disabled = true; $("empty-state").hidden = true; $("results-state").hidden = true; $("loading-state").hidden = false; output.setAttribute("aria-busy", "true");
  try {
    const response = await fetch("/api/v1/selection-advice", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`${data?.error?.code || "REQUEST_FAILED"}：${data?.error?.message || "生成失败，请检查输入后重试。"}`);
    render(data); if (window.innerWidth < 1050) output.scrollIntoView({ behavior:"smooth", block:"start" });
  } catch (error) {
    $("loading-state").hidden = true; $("empty-state").hidden = false; output.setAttribute("aria-busy", "false");
    $("form-error").textContent = error.message; $("form-error").hidden = false;
  } finally { $("submit-button").disabled = false; }
}

form.addEventListener("submit", submit);
$("edit-button").addEventListener("click", () => { form.scrollIntoView({behavior:"smooth",block:"start"}); $("institution").focus(); });
