"use client";

import Link from "next/link";
import { useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { ProgramCard } from "@/components/ProgramCard";
import { selectionAdviceResponseSchema } from "@/lib/selection-schema";
import snapshot from "@/demo/advice.json";

const advice = selectionAdviceResponseSchema.parse(snapshot);

export function DemoAdvice() {
  const [all, setAll] = useState(false);
  const programs = all ? advice.results : advice.results.slice(0, 4);
  return <>
    <AppHeader active="advice" />
    <main className="planner-shell planner-shell--results">
      <section className="output-panel results-panel">
        <header className="results-header"><div><p className="overline">SkyOffer · 公开演示</p><h1>选校建议示例</h1></div><Link className="primary-button" href="/programs">浏览项目数据库</Link></header>
        <p className="beta-scope-note">固定合成档案 · 规则说明模式 · 非实时 AI 分析。本页不接收个人资料；所有结果均属于下方示例背景，不构成录取承诺。</p>
        <div className="profile-summary"><div><span>合成申请档案</span><strong>华东示例理工大学 · 自动化</strong></div><div><span>原始成绩</span><strong>82.4 / 100</strong></div><div><span>语言成绩</span><strong>尚未提供</strong></div><div><span>申请地区</span><strong>香港 · 英国</strong></div></div>
        <p className="hero__lead">展开项目卡片，查看条件缺口、历史参考与字段级官网依据。</p>
        <p className="results-meta">数据快照：2026-09-07 · 当前学年：2027/28 · 2026/27 历史参考单独标注</p>
        <div className="program-list">{programs.map((program, index) => <ProgramCard key={program.program_ref} program={program} index={index} />)}</div>
        {!all && <button className="primary-button" style={{ marginTop: 24 }} onClick={() => setAll(true)}>查看全部 {advice.results.length} 个示例项目</button>}
        <p className="beta-scope-note">想用自己的背景实时分析？请按 GitHub README 安装完整版本，并在服务端配置模型密钥。<a href="https://github.com/hexing-ai/SkyOffer#快速开始">查看安装步骤</a></p>
      </section>
    </main>
  </>;
}
