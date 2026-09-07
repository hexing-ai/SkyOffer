import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowDown, ArrowRight, ArrowUpRight, BookOpen, Check,
  ChevronDown, CircleHelp, ClipboardCheck, Database,
  FileCheck2, FileText, GraduationCap, LockKeyhole, Search, ShieldCheck,
} from "lucide-react";

import { BrandLink } from "@/components/BrandLink";
import { DEMO_MODE } from "@/lib/demo-mode";
import styles from "./home.module.css";

export const metadata: Metadata = {
  title: "SkyOffer · 看清申请条件，找到适合你的硕士项目",
  description: "面向香港与英国授课型硕士申请者，结合学业背景与院校官网要求，提供可核验的选校建议、项目数据库和申请档案。",
};

const questions = [
  {
    question: "现在可以查哪些地区和项目？",
    answer: "当前体验版收录香港与英国的 20 个授课型硕士项目，涉及计算机科学、人工智能、航空工程等相关方向。你可以在项目数据库中查看完整名单和各项目的信息覆盖情况，更多项目将逐步补充。",
  },
  {
    question: "项目要求对应哪一年的申请？",
    answer: "当前面向 2027/28 学年申请。已有当年官网门槛的项目，按相应要求参与判断；其余项目可查看明确标注的 2026/27 历史参考。历史满足度不会作为 2027/28 的正式分层依据，缺失或尚未核实的信息会标为待核验。",
  },
  {
    question: "选校建议可以当作录取保证吗？",
    answer: "选校建议帮助你整理项目、核对申请门槛和发现条件差距，不代表录取概率或录取承诺。实际录取还受申请竞争、材料质量和院校综合评审等因素影响，请结合项目官网最新要求作出决定。",
  },
  {
    question: "没有语言成绩，也能开始吗？",
    answer: "可以。你可以先填写已有的学业背景、申请地区和专业方向。尚未提供的信息会保留为缺失或待核验，之后可以补充资料并重新生成建议。",
  },
  {
    question: "需要注册吗？申请档案保存在哪里？",
    answer: "当前可以直接进入体验，无需注册。主动保存的申请档案仅保存在当前浏览器，不会跨设备同步，清理浏览器数据可能将其删除。生成建议时，填写的背景信息会提交给服务端进行条件判断和 AI 解释；本地保存档案与提交分析是两个不同的操作。",
  },
];

function StartLink({ light = false }: { light?: boolean }) {
  return <Link href="/advice" className={`${styles.cta} ${light ? styles.ctaLight : ""}`}>开始选校 <ArrowRight size={18} aria-hidden="true" /></Link>;
}

function AdvicePreview() {
  return (
    <div className={styles.preview} aria-label="选校条件核对示例，非个人评估">
      <div className={styles.previewBar}>
        <span><FileCheck2 size={17} aria-hidden="true" /> 你的选校建议</span>
        <span className={styles.exampleBadge}>示例预览</span>
      </div>
      <div className={styles.previewBody}>
        <div className={styles.sampleProfile}>
          <span className={styles.profileIcon}><GraduationCap size={22} aria-hidden="true" /></span>
          <div><strong>从你的背景出发</strong><p>示例背景 · 计算机专业 · IELTS 7.0</p></div>
        </div>
        <div className={styles.previewConnector}><span />对照项目官网要求<ArrowDown size={13} aria-hidden="true" /></div>
        <article className={styles.sampleProgram}>
          <div className={styles.sampleProgramMeta}><span>香港大学</span><span>2027/28</span></div>
          <h2>人工智能理学硕士</h2>
          <p className={styles.englishName}>MSc in Artificial Intelligence</p>
          <div className={styles.checkRow}>
            <span className={styles.checkIcon}><Check size={15} aria-hidden="true" /></span>
            <div><strong>语言分数达到所列要求</strong><p>示例：总分 7.0，单项均不低于 6.0</p></div>
          </div>
          <div className={styles.checkRow}>
            <span className={styles.pendingIcon}><CircleHelp size={15} aria-hidden="true" /></span>
            <div><strong>先修知识仍需核对</strong><p>需结合数学、统计与编程课程背景</p></div>
          </div>
          <details className={styles.sampleEvidence}>
            <summary><BookOpen size={15} aria-hidden="true" /> 查看这条要求的官网依据<ChevronDown size={15} aria-hidden="true" /></summary>
            <div>
              <p>IELTS 总分至少 6.0，各单项不低于 5.5。</p>
              <p>官网要求摘录核验于 2026-09-04。完整判断还需结合学位、先修知识等条件。</p>
              <a href="https://www.mscai.hku.hk/admissions/" target="_blank" rel="noreferrer">香港大学项目招生页 <ArrowUpRight size={14} aria-hidden="true" /></a>
            </div>
          </details>
        </article>
        <p className={styles.previewNote}><ShieldCheck size={15} aria-hidden="true" /> 条件有依据，不确定的信息明确标注。</p>
      </div>
      <div className={styles.previewCaption}>示例背景仅用于展示核对方式，不代表个人选校结论。</div>
    </div>
  );
}

export default function Home() {
  return (
    <div className={styles.home}>
      <a className="skip-link" href="#home-main">跳到产品介绍</a>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <BrandLink />
          <nav className={styles.nav} aria-label="产品介绍导航">
            <a href="#features">产品能力</a>
            <a href="#how-it-works">使用流程</a>
            <a href="#faq">常见问题</a>
          </nav>
          <StartLink />
        </div>
      </header>

      <main id="home-main">
        <section className={styles.hero} aria-labelledby="home-title">
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}><span /> AI 留学选校建议平台</p>
            <h1 id="home-title">看清申请条件，<br />找到适合你的<br /><em>硕士项目。</em></h1>
            <p className={styles.heroLead}>从你的学业背景与申请目标出发，对照院校官网要求，看清可考虑的项目、需要补齐的条件，以及每条建议背后的依据。</p>
            <div className={styles.heroActions}><StartLink /><a className={styles.textLink} href="#how-it-works">了解如何使用 <ArrowDown size={16} aria-hidden="true" /></a></div>
            <p className={styles.entryNote}>{DEMO_MODE ? "公开演示 · 固定示例结果 · 无需填写个人信息" : "无需注册，即可开始体验"}</p>
          </div>
          <div className={styles.heroVisual}><AdvicePreview /></div>
        </section>

        <div className={styles.scope} role="note">
          <div><span className={styles.beta}>当前体验版</span><strong>香港 & 英国</strong><span>20 个授课型硕士项目</span></div>
          <p>申请年份与历史参考均明确标注</p>
        </div>

        <section id="features" className={styles.section} aria-labelledby="features-title">
          <div className={styles.sectionHeading}>
            <div><p className={styles.eyebrow}>从了解项目，到做出选择</p><h2 id="features-title">让选校的每一步，<br />都有据可循。</h2></div>
            <p>把分散的项目要求与你的背景放在一起，<br />更清楚地了解选择，也知道下一步该准备什么。</p>
          </div>
          <div className={styles.features}>
            <article className={styles.feature}>
              <div className={styles.featureIcon}><ClipboardCheck size={23} aria-hidden="true" /></div>
              <h3>选校建议</h3><p>对照你的条件，了解项目的申请门槛、尚缺信息和需要进一步核验的地方。</p>
              <div className={`${styles.miniature} ${styles.adviceMini}`} aria-label="建议内容示意">
                <span className={styles.miniLabel}>每条建议，都能继续往下看</span>
                <div><Check size={15} aria-hidden="true" /><span>条件核对</span><span>逐项查看</span></div>
                <div><CircleHelp size={15} aria-hidden="true" /><span>信息缺口</span><span>明确标注</span></div>
                <div><BookOpen size={15} aria-hidden="true" /><span>官网依据</span><span>追溯原文</span></div>
              </div>
              <Link href="/advice" className={styles.featureLink}>开始了解我的选择 <ArrowUpRight size={17} aria-hidden="true" /></Link>
            </article>
            <article className={styles.feature}>
              <div className={styles.featureIcon}><Database size={23} aria-hidden="true" /></div>
              <h3>项目数据库</h3><p>按地区和专业方向寻找项目，查看具体申请要求、适用年份和对应官网来源。</p>
              <div className={styles.miniature} aria-label="项目数据库内容示意">
                <div className={styles.miniSearch}><Search size={15} aria-hidden="true" /> 院校、项目或专业方向</div>
                <div className={styles.miniProgram}><span>香港大学</span><strong>人工智能理学硕士</strong></div>
                <div className={styles.miniProgram}><span>香港科技大学</span><strong>信息技术理学硕士</strong></div>
              </div>
              <Link href="/programs" className={styles.featureLink}>浏览当前收录项目 <ArrowUpRight size={17} aria-hidden="true" /></Link>
            </article>
            <article className={styles.feature}>
              <div className={styles.featureIcon}><FileText size={23} aria-hidden="true" /></div>
              <h3>申请档案</h3><p>整理学业、语言与经历，在当前浏览器保存一份档案，再次选校时自动带入。</p>
              <div className={styles.miniature} aria-label="申请档案字段示意">
                <div className={styles.miniProfile}><span>学业背景</span><strong>院校 · 专业 · 成绩</strong></div>
                <div className={styles.miniProfile}><span>语言与经历</span><strong>考试 · 课程 · 项目</strong></div>
                <div className={styles.miniProfile}><span>申请目标</span><strong>地区 · 方向</strong></div>
                <span className={styles.localNote}><LockKeyhole size={13} aria-hidden="true" /> 档案仅保存在当前浏览器</span>
              </div>
              <Link href="/profile" className={styles.featureLink}>整理我的申请背景 <ArrowUpRight size={17} aria-hidden="true" /></Link>
            </article>
          </div>
        </section>

        <section id="how-it-works" className={styles.processSection} aria-labelledby="process-title">
          <div className={styles.section}>
            <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>使用流程</p><h2 id="process-title">从你的背景开始，<br />走向更清楚的申请计划。</h2></div><StartLink /></div>
            <ol className={styles.steps}>
              <li><span className={styles.stepNumber}>01</span><h3>填写背景与目标</h3><p>填写学业、语言和经历，选择想申请的地区与专业方向。已有档案会自动带入。</p><span className={styles.stepHint}>先填写你已经知道的信息</span></li>
              <li><span className={styles.stepNumber}>02</span><h3>对照项目申请条件</h3><p>系统核对官网门槛，区分已满足的条件、信息缺口和仍需人工核验的部分。</p><span className={styles.stepHint}>不确定的条件，保留为待核验</span></li>
              <li><span className={styles.stepNumber}>03</span><h3>查看建议与下一步</h3><p>阅读选校建议和条件差距，展开官网依据，明确需要补充的材料或进一步了解的项目。</p><span className={styles.stepHint}>带着依据，继续完善你的选择</span></li>
            </ol>
          </div>
        </section>

        <section id="faq" className={`${styles.section} ${styles.faqSection}`} aria-labelledby="faq-title">
          <div className={styles.faqIntro}><p className={styles.eyebrow}>开始之前</p><h2 id="faq-title">你可能想了解</h2><p>关于项目范围、建议依据，<br />以及你的申请信息。</p></div>
          <div className={styles.faqList}>{questions.map(({ question, answer }) => (
            <details key={question} className={styles.faqItem}><summary>{question}<ChevronDown size={18} aria-hidden="true" /></summary><p>{answer}</p></details>
          ))}</div>
        </section>

        <section className={styles.closing} aria-labelledby="closing-title">
          <div><p className={styles.closingKicker}>你的下一站，从看清选择开始。</p><h2 id="closing-title">把申请的第一步，<br />交给有依据的选校建议。</h2><p>从现有背景出发，逐步找到自己的方向。</p></div>
          <div className={styles.closingAction}><StartLink light /><span>无需注册 · 可随时补充背景</span></div>
        </section>
      </main>

      <footer className={styles.footer}><BrandLink /><p>选校有依据，申请有方向。</p><a href="#faq">关于数据与建议</a></footer>
    </div>
  );
}
