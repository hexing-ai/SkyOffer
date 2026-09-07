"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  FileCheck2,
  LockKeyhole,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";

import { ApiError, requestSelectionAdvice } from "@/lib/api";
import type {
  Direction,
  FormValues,
  Region,
  RequestState,
  SelectionAdviceRequest,
  SelectionAdviceResponse,
} from "@/lib/types";
import { ProgramCard } from "@/components/ProgramCard";
import { AppHeader } from "@/components/AppHeader";
import { INITIAL_VALUES, useApplicationProfile } from "@/lib/applicant-profile";

export { INITIAL_VALUES } from "@/lib/applicant-profile";

const TIER_ORDER = ["relative_safe", "target", "sprint", "verify"] as const;
const TIER_LABELS = {
  relative_safe: "相对稳妥",
  target: "主申",
  sprint: "冲刺",
  verify: "待核验",
};

type FormStep = 1 | 2 | 3;

const FORM_STEPS: Array<{ id: FormStep; label: string; title: string }> = [
  { id: 1, label: "学业背景", title: "填写学业背景" },
  { id: 2, label: "语言与经历", title: "填写语言与经历" },
  { id: 3, label: "申请目标", title: "选择申请目标" },
];

function optionalNumber(value: string) {
  return value.trim() === "" ? null : Number(value);
}

function triState(value: "" | "true" | "false") {
  return value === "" ? null : value === "true";
}

function getStepError(step: FormStep, values: FormValues) {
  if (
    step === 1 &&
    (!values.institution.trim() ||
      !values.major.trim() ||
      !values.degreeType.trim() ||
      !values.graduationYear.trim() ||
      !values.gradeValue.trim() ||
      !values.gradingScale.trim())
  ) {
    return "请填写完整的学业背景必填项。";
  }
  if (
    step === 2 &&
    ((values.languageType && !values.languageTotal) || (!values.languageType && values.languageTotal))
  ) {
    return "语言考试类型和总分需要同时填写。";
  }
  if (
    step === 2 &&
    ((values.experienceTitle.trim() && !values.experienceDescription.trim()) ||
      (!values.experienceTitle.trim() && values.experienceDescription.trim()))
  ) {
    return "代表经历的标题和具体内容需要同时填写。";
  }
  if (step === 3 && (!values.targetRegions.length || !values.targetDirections.length)) {
    return "请至少选择一个目标地区和一个专业方向。";
  }
  return null;
}

export function buildPayload(values: FormValues): SelectionAdviceRequest {
  if (!values.targetRegions.length || !values.targetDirections.length) {
    throw new Error("请至少选择一个目标地区和一个专业方向。");
  }
  if ((values.languageType && !values.languageTotal) || (!values.languageType && values.languageTotal)) {
    throw new Error("语言考试类型和总分需要同时填写。");
  }
  if (
    (values.experienceTitle.trim() && !values.experienceDescription.trim()) ||
    (!values.experienceTitle.trim() && values.experienceDescription.trim())
  ) {
    throw new Error("代表经历的标题和具体内容需要同时填写。");
  }

  const componentScores: Partial<Record<"listening" | "reading" | "writing" | "speaking", number>> = {};
  (["listening", "reading", "writing", "speaking"] as const).forEach((key) => {
    const score = optionalNumber(values[key]);
    if (score !== null) componentScores[key] = score;
  });

  const languageScores: SelectionAdviceRequest["profile"]["language_scores"] = [];
  if (values.languageType && values.languageTotal) {
    languageScores.push({
      test_type: values.languageType,
      total_score: Number(values.languageTotal),
      component_scores: componentScores,
      test_date: null,
    });
  }

  return {
    schema_version: "selection_advice_request.v1",
    profile: {
      schema_version: "applicant_analysis_input.v1",
      request_language: "zh-CN",
      education_status: values.educationStatus,
      graduation_year: Number(values.graduationYear),
      undergraduate_institution: values.institution.trim(),
      undergraduate_major: values.major.trim(),
      degree_type: values.degreeType.trim(),
      grading_scale: Number(values.gradingScale),
      grade_value: Number(values.gradeValue),
      core_courses: values.courses.split("\n").map((item) => item.trim()).filter(Boolean),
      language_scores: languageScores,
      experiences: values.experienceTitle.trim()
        ? [{
            type: "project",
            title: values.experienceTitle.trim(),
            description: values.experienceDescription.trim(),
          }]
        : [],
      target_regions: values.targetRegions,
      target_directions: values.targetDirections,
      career_goal: values.careerGoal.trim() || null,
      budget_note: null,
    },
    rule_facts: {
      institution_recognition: values.institutionRecognition,
      work_experience_months: optionalNumber(values.workMonths),
      materials: {
        portfolio: triState(values.portfolio),
        interview: triState(values.interview),
        recommendation_letters: triState(values.recommendation),
      },
    },
  };
}

function ChoiceChip({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: () => void;
}) {
  return (
    <label className="choice-chip">
      <input type="checkbox" checked={checked} onChange={onChange} />
      <span>{label}</span>
    </label>
  );
}

export function SelectionPlanner() {
  const storedProfile = useApplicationProfile();
  const [draftValues, setDraftValues] = useState<FormValues | null>(null);
  const values = draftValues ?? storedProfile?.values ?? INITIAL_VALUES;
  const [step, setStep] = useState<FormStep>(1);
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [data, setData] = useState<SelectionAdviceResponse | null>(null);
  const [error, setError] = useState<{ message: string; code?: string; requestId?: string } | null>(null);
  const outputRef = useRef<HTMLElement>(null);

  const tierCounts = useMemo(() => {
    const counts = { relative_safe: 0, target: 0, sprint: 0, verify: 0 };
    data?.results.forEach((program) => counts[program.recommendation_tier]++);
    return counts;
  }, [data]);

  const update = <K extends keyof FormValues>(key: K, value: FormValues[K]) => {
    setDraftValues((current) => ({ ...(current ?? values), [key]: value }));
    if (error) setError(null);
  };

  const toggleRegion = (region: Region) => {
    update(
      "targetRegions",
      values.targetRegions.includes(region)
        ? values.targetRegions.filter((item) => item !== region)
        : [...values.targetRegions, region],
    );
  };

  const toggleDirection = (direction: Direction) => {
    update(
      "targetDirections",
      values.targetDirections.includes(direction)
        ? values.targetDirections.filter((item) => item !== direction)
        : [...values.targetDirections, direction],
    );
  };

  const advance = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const validationError = getStepError(step, values);
    if (validationError) {
      setError({ message: validationError });
      return;
    }
    setError(null);
    setStep((current) => Math.min(current + 1, 3) as FormStep);
  };

  const goBack = () => {
    setError(null);
    setStep((current) => Math.max(current - 1, 1) as FormStep);
  };

  const returnToForm = (targetStep: FormStep = 1) => {
    setRequestState("idle");
    setError(null);
    setStep(targetStep);
    window.setTimeout(() => document.querySelector("#profile-form")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (requestState === "submitting") return;
    setError(null);

    let payload: SelectionAdviceRequest;
    try {
      const validationError = getStepError(3, values);
      if (validationError) throw new Error(validationError);
      payload = buildPayload(values);
    } catch (validationError) {
      setError({ message: validationError instanceof Error ? validationError.message : "请检查输入。" });
      return;
    }

    setRequestState("submitting");
    setData(null);
    try {
      const response = await requestSelectionAdvice(payload);
      setData(response);
      setRequestState(response.results.length ? "succeeded" : "empty");
      window.setTimeout(() => outputRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch (requestError) {
      const apiError = requestError instanceof ApiError ? requestError : null;
      setRequestState("failed");
      setError({
        message: requestError instanceof Error ? requestError.message : "生成失败，请稍后重试。",
        code: apiError?.code,
        requestId: apiError?.requestId,
      });
    }
  };

  return (
    <>
      <a className="skip-link" href="#profile-form">跳到申请档案</a>
      <AppHeader active="advice" />

      <main id="top" className={requestState === "idle" ? undefined : "main--results"}>
        {requestState === "idle" ? (
          <section className="hero" aria-labelledby="page-title">
            <h1 id="page-title">选校建议</h1>
            <p className="hero__lead">根据官网申请要求，检查你的条件并生成选校建议。</p>
            <p className="beta-scope-note">
              当前覆盖 20 个项目；2027/28 官方门槛用于正式分层，其余项目仅提供明确标注年份的 2026/27 历史参考。
            </p>
          </section>
        ) : null}

        <section className={`planner-shell ${requestState === "idle" ? "planner-shell--form" : "planner-shell--results"}`} aria-label="选校建议工作台">
          {requestState === "idle" && storedProfile ? (
            <div className="profile-loaded" role="status">
              <span>已自动填入申请档案</span>
              <a href="/profile">编辑档案</a>
            </div>
          ) : null}
          {requestState === "idle" ? (
            <ol className="step-progress" aria-label="填写进度">
              {FORM_STEPS.map((item) => (
                <li key={item.id} className={item.id === step ? "is-current" : item.id < step ? "is-complete" : undefined}>
                  <button type="button" disabled={item.id > step} onClick={() => setStep(item.id)} aria-current={item.id === step ? "step" : undefined}>
                    <span>{item.id}</span>{item.label}
                  </button>
                </li>
              ))}
            </ol>
          ) : null}

          {requestState === "idle" ? (
          <form id="profile-form" className="profile-form" onSubmit={step === 3 ? submit : advance}>
            <div className="panel-title">
              <div>
                <p className="step-kicker">第 {step} 步，共 3 步</p>
                <h2>{FORM_STEPS[step - 1].title}</h2>
              </div>
              <span>* 必填</span>
            </div>

            {step === 1 ? (
            <fieldset aria-label="学业背景">
              <div className="field-grid field-grid--two">
                <label>当前状态 *
                  <select value={values.educationStatus} onChange={(e) => update("educationStatus", e.target.value as FormValues["educationStatus"])} required>
                    <option value="undergraduate">本科在读</option>
                    <option value="graduated">本科已毕业</option>
                    <option value="other">其他</option>
                  </select>
                </label>
                <label>毕业年份 *
                  <input type="number" min="2000" max="2035" value={values.graduationYear} onChange={(e) => update("graduationYear", e.target.value)} required />
                </label>
              </div>
              <label>本科院校 *
                <input value={values.institution} onChange={(e) => update("institution", e.target.value)} maxLength={120} placeholder="例如：华南理工大学" required />
              </label>
              <label>院校识别状态
                <select value={values.institutionRecognition} onChange={(e) => update("institutionRecognition", e.target.value as FormValues["institutionRecognition"])}>
                  <option value="unknown">不确定 / 交由人工核验</option>
                  <option value="mainland_recognized">已确认受认可</option>
                  <option value="mainland_priority">已确认属于项目优先院校</option>
                </select>
                <small>不知道就保持“不确定”，系统不会自行推断院校层级。</small>
              </label>
              <div className="field-grid field-grid--two">
                <label>本科专业 *
                  <input value={values.major} onChange={(e) => update("major", e.target.value)} maxLength={120} placeholder="例如：自动化" required />
                </label>
                <label>学位类型 *
                  <input value={values.degreeType} onChange={(e) => update("degreeType", e.target.value)} maxLength={120} required />
                </label>
              </div>
              <div className="grade-pair">
                <label>当前成绩 *
                  <input type="number" min="0" step="0.01" value={values.gradeValue} onChange={(e) => update("gradeValue", e.target.value)} placeholder="82.5" required />
                </label>
                <span aria-hidden="true">/</span>
                <label>满分 *
                  <input type="number" min="1" step="0.01" value={values.gradingScale} onChange={(e) => update("gradingScale", e.target.value)} required />
                </label>
              </div>
              <label>核心课程
                <textarea rows={4} value={values.courses} onChange={(e) => update("courses", e.target.value)} placeholder={"每行一门，例如：\n高等数学\nPython 程序设计\n自动控制原理"} />
              </label>
            </fieldset>
            ) : null}

            {step === 2 ? (
            <fieldset aria-label="语言与经历">
              <div className="field-grid field-grid--two">
                <label>语言考试
                  <select value={values.languageType} onChange={(e) => update("languageType", e.target.value as FormValues["languageType"])}>
                    <option value="">尚未考试</option>
                    <option value="IELTS">IELTS</option>
                    <option value="TOEFL">TOEFL</option>
                    <option value="PTE">PTE</option>
                  </select>
                </label>
                <label>总分
                  <input type="number" min="0" step="0.5" value={values.languageTotal} onChange={(e) => update("languageTotal", e.target.value)} placeholder="7.0" />
                </label>
              </div>
              <div className="field-grid field-grid--four compact-fields">
                {(["listening", "reading", "writing", "speaking"] as const).map((key, index) => (
                  <label key={key}>{["听力", "阅读", "写作", "口语"][index]}
                    <input type="number" min="0" step="0.5" value={values[key]} onChange={(e) => update(key, e.target.value)} />
                  </label>
                ))}
              </div>
              <label>相关工作经验（月）
                <input type="number" min="0" max="1200" value={values.workMonths} onChange={(e) => update("workMonths", e.target.value)} placeholder="没有可填 0；不确定可留空" />
              </label>
              <label>代表经历标题
                <input value={values.experienceTitle} onChange={(e) => update("experienceTitle", e.target.value)} maxLength={120} placeholder="例如：无人机视觉导航课程设计" />
              </label>
              <label>你具体做了什么
                <textarea rows={3} value={values.experienceDescription} onChange={(e) => update("experienceDescription", e.target.value)} maxLength={800} placeholder="说明职责、方法和结果；没有可留空" />
              </label>
            </fieldset>
            ) : null}

            {step === 3 ? (
            <fieldset aria-label="申请目标">
              <p className="field-help">至少选择一个地区和一个专业方向。</p>
              <div className="choice-row" aria-label="目标地区">
                <ChoiceChip checked={values.targetRegions.includes("hong_kong")} label="香港" onChange={() => toggleRegion("hong_kong")} />
                <ChoiceChip checked={values.targetRegions.includes("united_kingdom")} label="英国" onChange={() => toggleRegion("united_kingdom")} />
              </div>
              <div className="choice-row" aria-label="目标专业方向">
                <ChoiceChip checked={values.targetDirections.includes("computer_science")} label="计算机科学" onChange={() => toggleDirection("computer_science")} />
                <ChoiceChip checked={values.targetDirections.includes("artificial_intelligence")} label="人工智能" onChange={() => toggleDirection("artificial_intelligence")} />
                <ChoiceChip checked={values.targetDirections.includes("aerospace_engineering")} label="航空工程" onChange={() => toggleDirection("aerospace_engineering")} />
                <ChoiceChip checked={values.targetDirections.includes("low_altitude_economy")} label="低空经济" onChange={() => toggleDirection("low_altitude_economy")} />
              </div>
              <label>职业目标
                <textarea rows={3} value={values.careerGoal} onChange={(e) => update("careerGoal", e.target.value)} maxLength={500} placeholder="例如：希望从事自主飞行系统或智能感知工作" />
              </label>
              <details className="optional-fields">
                <summary>补充材料状态（可选）</summary>
                <div className="field-grid field-grid--three">
                  {([
                    ["portfolio", "作品集"],
                    ["interview", "面试准备"],
                    ["recommendation", "推荐信"],
                  ] as const).map(([key, label]) => (
                    <label key={key}>{label}
                      <select value={values[key]} onChange={(e) => update(key, e.target.value as FormValues[typeof key])}>
                        <option value="">不确定</option>
                        <option value="true">已准备</option>
                        <option value="false">未准备</option>
                      </select>
                    </label>
                  ))}
                </div>
              </details>
            </fieldset>
            ) : null}

            {error ? (
              <div className="form-error" role="alert">
                <strong>{error.code ? `${error.code}：` : "请检查："}</strong>{error.message}
                {error.requestId ? <small>Request ID：{error.requestId}</small> : null}
              </div>
            ) : null}

            <div className="form-footer">
              <p className="boundary-note"><ShieldCheck aria-hidden="true" size={16} /> 结果不代表录取概率，也不等于保底。</p>
              <div className="form-actions">
                {step > 1 ? (
                  <button className="secondary-button" type="button" onClick={goBack}>
                    <ArrowLeft aria-hidden="true" size={17} /> 上一步
                  </button>
                ) : null}
                <button className="primary-button" type="submit">
                  <span>{step === 3 ? "生成选校建议" : "继续"}</span>
                  <ArrowRight aria-hidden="true" size={18} />
                </button>
              </div>
            </div>
            <p className="privacy-line"><LockKeyhole aria-hidden="true" size={13} /> 申请信息仅用于本次分析；模型不能修改规则结论。</p>
          </form>
          ) : null}

          {requestState !== "idle" ? (
          <section ref={outputRef} className="output-panel" data-state={requestState} aria-live="polite" aria-busy={requestState === "submitting"}>
            {requestState === "submitting" ? (
              <div className="output-placeholder loading-panel">
                <div className="scan-track" aria-hidden="true"><span /></div>
                <p className="overline">正在处理</p>
                <h1>正在分析申请条件</h1>
                <p>系统正在核对项目申请要求并整理结果。</p>
                <div className="loading-steps">
                  <span className="is-running"><i />读取申请事实</span>
                  <span><i />执行门槛规则</span>
                  <span><i />生成可读解释</span>
                </div>
              </div>
            ) : null}

            {requestState === "failed" ? (
              <div className="output-placeholder error-panel">
                <div className="status-symbol">!</div>
                <p className="overline">请求失败</p>
                <h1>生成失败</h1>
                <p>{error?.message ?? "请检查输入或服务状态后重试，你填写的内容仍然保留。"}</p>
                <button className="ghost-button" type="button" onClick={() => returnToForm(3)}>返回并检查信息 <ArrowRight aria-hidden="true" size={16} /></button>
              </div>
            ) : null}

            {requestState === "empty" && data ? (
              <div className="output-placeholder empty-panel">
                <div className="status-symbol"><FileCheck2 aria-hidden="true" size={34} /></div>
                <p className="overline">没有匹配结果</p>
                <h1>暂无匹配项目</h1>
                <p>{data.empty_reason ?? "当前没有同时匹配地区和方向的已核验项目。"}</p>
                <p className="empty-disclaimer">系统没有调用模型补造项目；修改目标范围后可重新提交。</p>
                <button className="ghost-button" type="button" onClick={() => returnToForm(3)}>修改目标范围 <RotateCcw aria-hidden="true" size={16} /></button>
              </div>
            ) : null}

            {requestState === "succeeded" && data ? (
              <div className="results-panel">
                <div className="results-header">
                  <div>
                    <p className="overline">分析结果</p>
                    <h1>选校建议结果</h1>
                  </div>
                  <button className="ghost-button ghost-button--light" type="button" onClick={() => returnToForm(1)}>修改信息</button>
                </div>
                <div className="profile-summary" aria-label="本次申请信息摘要">
                  <div><span>本科院校</span><strong>{values.institution}</strong></div>
                  <div><span>本科专业</span><strong>{values.major}</strong></div>
                  <div><span>成绩</span><strong>{values.gradeValue} / {values.gradingScale}</strong></div>
                  <div><span>申请范围</span><strong>{values.targetRegions.length} 个地区 · {values.targetDirections.length} 个方向</strong></div>
                </div>
                <div className="results-meta">
                  <span>{data.results.length} 项匹配</span>
                  <span>{data.excluded_program_count} 项未进入</span>
                  <span>用时 {(data.meta.duration_ms / 1000).toFixed(1)}s</span>
                  <span>数据 {data.meta.dataset_manifest_sha256.slice(0, 10)}</span>
                </div>
                <div className="tier-summary">
                  {TIER_ORDER.map((tier) => (
                    <div key={tier} data-tier={tier}>
                      <strong>{tierCounts[tier]}</strong>
                      <span>{TIER_LABELS[tier]}</span>
                    </div>
                  ))}
                </div>
                <div className="program-list">
                  {data.results.map((program, index) => <ProgramCard key={program.program_ref} program={program} index={index} />)}
                </div>
                <div className="result-disclaimer"><ShieldCheck aria-hidden="true" size={18} /><p>{data.disclaimer}</p></div>
              </div>
            ) : null}
          </section>
          ) : null}
        </section>
      </main>
    </>
  );
}
