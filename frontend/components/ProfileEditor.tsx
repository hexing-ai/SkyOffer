"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { ArrowRight, Check, LockKeyhole, Save, Trash2 } from "lucide-react";

import { AppHeader } from "@/components/AppHeader";
import {
  INITIAL_VALUES,
  clearApplicationProfile,
  saveApplicationProfile,
  useApplicationProfile,
} from "@/lib/applicant-profile";
import type { Direction, FormValues, Region } from "@/lib/types";
import type { ApplicantProfile } from "@/lib/applicant-profile";

function ProfileChoice({
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

export function ProfileEditor() {
  const profile = useApplicationProfile();
  return <ProfileEditorForm key={profile?.saved_at ?? "empty"} profile={profile} />;
}

function ProfileEditorForm({ profile }: { profile: ApplicantProfile | null }) {
  const [values, setValues] = useState<FormValues>(profile?.values ?? INITIAL_VALUES);
  const [dirty, setDirty] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const update = <K extends keyof FormValues>(key: K, value: FormValues[K]) => {
    setValues((current) => ({ ...current, [key]: value }));
    setDirty(true);
    setSaveError(null);
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

  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      saveApplicationProfile(values);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "保存失败，请重试。");
    }
  };

  const clear = () => {
    if (!window.confirm("确定清空当前浏览器中保存的申请档案吗？")) return;
    clearApplicationProfile();
  };

  return (
    <>
      <a className="skip-link" href="#profile-editor">跳到申请档案</a>
      <AppHeader active="profile" />
      <main className="profile-page">
        <header className="profile-heading">
          <div>
            <h1>申请档案</h1>
            <p>保存个人背景，生成选校建议时自动填入。</p>
          </div>
          <div className="local-only-note"><LockKeyhole aria-hidden="true" size={17} /><span><strong>仅保存在当前浏览器</strong>不会上传到账号，也不会跨设备同步。</span></div>
        </header>

        <form id="profile-editor" className="profile-editor" onSubmit={save}>
          <section className="profile-section" aria-labelledby="profile-academic">
            <header><div><span>01</span><h2 id="profile-academic">学业背景</h2></div><p>院校、专业和成绩</p></header>
            <div className="profile-section__body">
              <div className="field-grid field-grid--two">
                <label>当前状态<select value={values.educationStatus} onChange={(event) => update("educationStatus", event.target.value as FormValues["educationStatus"])}><option value="undergraduate">本科在读</option><option value="graduated">本科已毕业</option><option value="other">其他</option></select></label>
                <label>毕业年份<input type="number" min="2000" max="2035" value={values.graduationYear} onChange={(event) => update("graduationYear", event.target.value)} /></label>
              </div>
              <label>本科院校<input value={values.institution} onChange={(event) => update("institution", event.target.value)} maxLength={120} placeholder="例如：华南理工大学" /></label>
              <label>院校识别状态<select value={values.institutionRecognition} onChange={(event) => update("institutionRecognition", event.target.value as FormValues["institutionRecognition"])}><option value="unknown">不确定 / 交由人工核验</option><option value="mainland_recognized">已确认受认可</option><option value="mainland_priority">已确认属于项目优先院校</option></select><small>不确定时保持默认，系统不会自行推断院校层级。</small></label>
              <div className="field-grid field-grid--two">
                <label>本科专业<input value={values.major} onChange={(event) => update("major", event.target.value)} maxLength={120} placeholder="例如：自动化" /></label>
                <label>学位类型<input value={values.degreeType} onChange={(event) => update("degreeType", event.target.value)} maxLength={120} /></label>
              </div>
              <div className="grade-pair">
                <label>当前成绩<input type="number" min="0" step="0.01" value={values.gradeValue} onChange={(event) => update("gradeValue", event.target.value)} placeholder="82.5" /></label>
                <span aria-hidden="true">/</span>
                <label>满分<input type="number" min="1" step="0.01" value={values.gradingScale} onChange={(event) => update("gradingScale", event.target.value)} /></label>
              </div>
              <label>核心课程<textarea rows={4} value={values.courses} onChange={(event) => update("courses", event.target.value)} placeholder={"每行一门，例如：\n高等数学\nPython 程序设计\n自动控制原理"} /></label>
            </div>
          </section>

          <section className="profile-section" aria-labelledby="profile-experience">
            <header><div><span>02</span><h2 id="profile-experience">语言与经历</h2></div><p>语言成绩和代表经历</p></header>
            <div className="profile-section__body">
              <div className="field-grid field-grid--two">
                <label>语言考试<select value={values.languageType} onChange={(event) => update("languageType", event.target.value as FormValues["languageType"])}><option value="">尚未考试</option><option value="IELTS">IELTS</option><option value="TOEFL">TOEFL</option><option value="PTE">PTE</option></select></label>
                <label>总分<input type="number" min="0" step="0.5" value={values.languageTotal} onChange={(event) => update("languageTotal", event.target.value)} placeholder="7.0" /></label>
              </div>
              <div className="field-grid field-grid--four compact-fields">
                {(["listening", "reading", "writing", "speaking"] as const).map((key, index) => (
                  <label key={key}>{["听力", "阅读", "写作", "口语"][index]}<input type="number" min="0" step="0.5" value={values[key]} onChange={(event) => update(key, event.target.value)} /></label>
                ))}
              </div>
              <label>相关工作经验（月）<input type="number" min="0" max="1200" value={values.workMonths} onChange={(event) => update("workMonths", event.target.value)} placeholder="没有可填 0；不确定可留空" /></label>
              <label>代表经历标题<input value={values.experienceTitle} onChange={(event) => update("experienceTitle", event.target.value)} maxLength={120} placeholder="例如：无人机视觉导航课程设计" /></label>
              <label>经历内容<textarea rows={3} value={values.experienceDescription} onChange={(event) => update("experienceDescription", event.target.value)} maxLength={800} placeholder="说明职责、方法和结果" /></label>
            </div>
          </section>

          <section className="profile-section" aria-labelledby="profile-target">
            <header><div><span>03</span><h2 id="profile-target">申请目标</h2></div><p>地区、方向和材料状态</p></header>
            <div className="profile-section__body">
              <label className="choice-label">目标地区</label>
              <div className="choice-row" aria-label="目标地区">
                <ProfileChoice checked={values.targetRegions.includes("hong_kong")} label="香港" onChange={() => toggleRegion("hong_kong")} />
                <ProfileChoice checked={values.targetRegions.includes("united_kingdom")} label="英国" onChange={() => toggleRegion("united_kingdom")} />
              </div>
              <label className="choice-label">目标专业方向</label>
              <div className="choice-row" aria-label="目标专业方向">
                <ProfileChoice checked={values.targetDirections.includes("computer_science")} label="计算机科学" onChange={() => toggleDirection("computer_science")} />
                <ProfileChoice checked={values.targetDirections.includes("artificial_intelligence")} label="人工智能" onChange={() => toggleDirection("artificial_intelligence")} />
                <ProfileChoice checked={values.targetDirections.includes("aerospace_engineering")} label="航空工程" onChange={() => toggleDirection("aerospace_engineering")} />
                <ProfileChoice checked={values.targetDirections.includes("low_altitude_economy")} label="低空经济" onChange={() => toggleDirection("low_altitude_economy")} />
              </div>
              <label>职业目标<textarea rows={3} value={values.careerGoal} onChange={(event) => update("careerGoal", event.target.value)} maxLength={500} placeholder="例如：希望从事自主飞行系统或智能感知工作" /></label>
              <div className="field-grid field-grid--three">
                {([[
                  "portfolio", "作品集",
                ], [
                  "interview", "面试准备",
                ], [
                  "recommendation", "推荐信",
                ]] as const).map(([key, label]) => (
                  <label key={key}>{label}<select value={values[key]} onChange={(event) => update(key, event.target.value as FormValues[typeof key])}><option value="">不确定</option><option value="true">已准备</option><option value="false">未准备</option></select></label>
                ))}
              </div>
            </div>
          </section>

          <footer className="profile-savebar">
            <div className="profile-save-status" data-state={saveError ? "failed" : !dirty && profile ? "saved" : "idle"}>{!dirty && profile ? <Check aria-hidden="true" size={16} /> : null}<span>{saveError ?? (dirty ? "有未保存的修改" : profile ? `已保存于 ${formatSavedAt(profile.saved_at)}` : "尚未保存")}</span></div>
            <div className="profile-save-actions">
              {profile ? <button className="clear-profile-button" type="button" onClick={clear}><Trash2 aria-hidden="true" size={15} />清空档案</button> : null}
              <button className="primary-button" type="submit"><Save aria-hidden="true" size={16} />保存申请档案</button>
              {profile && !dirty ? <Link className="profile-advice-link" href="/advice">生成选校建议 <ArrowRight aria-hidden="true" size={16} /></Link> : null}
            </div>
          </footer>
        </form>
      </main>
    </>
  );
}

function formatSavedAt(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
