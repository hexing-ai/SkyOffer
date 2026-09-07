import Link from "next/link";
import { AppHeader } from "@/components/AppHeader";
import profile from "@/demo/profile.json";

export function DemoProfile() {
  return <><AppHeader active="profile" /><main className="profile-page"><header className="profile-heading"><div><h1>示例申请档案</h1><p>公开演示使用固定合成档案，不采集或保存你的个人资料。</p></div></header><section className="output-panel results-panel"><div className="profile-summary"><div><span>本科院校</span><strong>{profile.undergraduate_institution}</strong></div><div><span>本科专业</span><strong>{profile.undergraduate_major}</strong></div><div><span>原始成绩</span><strong>{profile.grade_value} / {profile.grading_scale}</strong></div><div><span>语言成绩</span><strong>尚未提供</strong></div></div><h2>已提供课程</h2><p>{profile.core_courses.join("、")}</p><h2 style={{ marginTop: 24 }}>合成项目经历</h2><p>{profile.experiences[0].description}</p><p className="beta-scope-note">完整版本可编辑并保存自己的申请档案，再自动带入选校表单。</p><Link className="primary-button" href="/advice">查看这份档案的示例建议</Link></section></main></>;
}
