"use client";

import { useId, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  CircleHelp,
  FileSearch,
  Minus,
} from "lucide-react";

import type { ProgramAdvice, RequirementStatus } from "@/lib/types";

const STATUS_META: Record<
  RequirementStatus,
  { label: string; icon: typeof Check }
> = {
  met: { label: "满足", icon: Check },
  unmet: { label: "未满足", icon: AlertTriangle },
  missing_information: { label: "缺信息", icon: CircleHelp },
  manual_review: { label: "人工核验", icon: FileSearch },
  not_applicable: { label: "不适用", icon: Minus },
};

const DIRECTION_LABELS: Record<string, string> = {
  computer_science: "计算机科学",
  artificial_intelligence: "人工智能",
  aerospace_engineering: "航空工程",
  low_altitude_economy: "低空经济",
};

const REGION_LABELS = {
  hong_kong: "香港",
  united_kingdom: "英国",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

export function ProgramCard({ program, index }: { program: ProgramAdvice; index: number }) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const evidenceId = useId();
  const historyId = useId();
  const history = program.historical_reference;

  return (
    <article className="program-card" data-tier={program.recommendation_tier}>
      <div className="program-stripe" aria-hidden="true" />
      <div className="program-card__body">
        <div className="program-card__topline">
          <span className="route-number">{String(index + 1).padStart(2, "0")}</span>
          <span>{REGION_LABELS[program.region]}</span>
          <span>{DIRECTION_LABELS[program.primary_direction] ?? program.primary_direction}</span>
          <span className="tier-badge">{program.recommendation_label}</span>
        </div>

        <div className="program-card__identity">
          <div>
            <p>{program.institution_name}</p>
            <h3>{program.program_name}</h3>
          </div>
          <a
            className="icon-link"
            href={program.official_program_url}
            target="_blank"
            rel="noreferrer"
            aria-label={`打开 ${program.program_name} 官方项目页面`}
            title="打开项目官网"
          >
            <ArrowUpRight aria-hidden="true" size={18} />
          </a>
        </div>

        <p className="program-summary">{program.explanation.summary}</p>

        <div className="threshold-grid" aria-label="门槛判断汇总">
          {(Object.keys(STATUS_META) as RequirementStatus[]).map((status) => {
            const Icon = STATUS_META[status].icon;
            return (
              <div className="threshold-item" data-status={status} key={status}>
                <Icon aria-hidden="true" size={14} />
                <strong>{program.threshold_summary[status]}</strong>
                <span>{STATUS_META[status].label}</span>
              </div>
            );
          })}
        </div>

        {history ? (
          <section className="history-reference" data-status={history.reference_status}>
            <div>
              <p className="micro-label">2026/27 官方历史参考</p>
              <strong>{history.reference_label}</strong>
              <span>不参与 2027 推荐分层</span>
            </div>
            <button
              type="button"
              aria-expanded={historyOpen}
              aria-controls={historyId}
              onClick={() => setHistoryOpen((value) => !value)}
            >
              {historyOpen ? "收起历史门槛" : "查看历史门槛"}
              <ChevronDown aria-hidden="true" size={16} />
            </button>
          </section>
        ) : null}

        {history && historyOpen ? (
          <div className="history-drawer" id={historyId}>
            <p className="history-disclaimer">{history.disclaimer}</p>
            {history.limitation_note ? <p className="history-limitation">{history.limitation_note}</p> : null}
            {history.field_judgments.map((field) => {
              const Icon = STATUS_META[field.status].icon;
              return (
                <details className="history-field" key={field.field_key}>
                  <summary>
                    <span>{field.display_text}</span>
                    <span className="field-status" data-status={field.status}>
                      <Icon aria-hidden="true" size={13} />
                      {STATUS_META[field.status].label}
                    </span>
                    <ChevronDown aria-hidden="true" size={15} />
                  </summary>
                  {field.citations.map((citation) => (
                    <blockquote className="citation citation--history" key={citation.source_id}>
                      <p>“{citation.excerpt}”</p>
                      <footer>
                        <a href={citation.url} target="_blank" rel="noreferrer">
                          {citation.page_title}
                          <ArrowUpRight aria-hidden="true" size={13} />
                        </a>
                        <span>核验 {formatDate(citation.verified_at)} · {citation.source_version}</span>
                      </footer>
                    </blockquote>
                  ))}
                </details>
              );
            })}
          </div>
        ) : null}

        <div className="program-card__columns">
          <section>
            <p className="micro-label">优势信号</p>
            <ul>
              {(program.explanation.strengths.length
                ? program.explanation.strengths
                : ["暂无已确认优势"]
              ).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
          <section>
            <p className="micro-label">风险与下一步</p>
            <ul>
              {[...program.explanation.risks, ...program.explanation.next_actions].map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        </div>

        <div className="program-card__actions">
          <Link className="program-detail-link" href={`/programs/${program.program_ref}`}>
            查看项目详情 <ArrowRight aria-hidden="true" size={16} />
          </Link>
          <button
            className="evidence-button"
            type="button"
            aria-expanded={evidenceOpen}
            aria-controls={evidenceId}
            onClick={() => setEvidenceOpen((value) => !value)}
          >
            <span>{evidenceOpen ? "收起官网核验记录" : `查看 ${program.field_judgments.length} 项官网核验记录`}</span>
            <ChevronDown aria-hidden="true" size={18} />
          </button>
        </div>
      </div>

      {evidenceOpen ? (
        <div className="evidence-drawer" id={evidenceId}>
          {program.field_judgments.map((field) => {
            const Icon = STATUS_META[field.status].icon;
            return (
              <details className="field-record" key={field.field_key}>
                <summary>
                  <span className="field-name">{field.field_key}</span>
                  {field.is_high_risk ? <span className="risk-flag">高风险</span> : null}
                  <span className="field-status" data-status={field.status}>
                    <Icon aria-hidden="true" size={13} />
                    {STATUS_META[field.status].label}
                  </span>
                  <ChevronDown className="field-chevron" aria-hidden="true" size={16} />
                </summary>
                <p className="field-description">{field.display_text}</p>
                {field.citations.map((citation) => (
                  <blockquote className="citation" key={citation.evidence_id}>
                    <p>“{citation.excerpt}”</p>
                    <footer>
                      <a href={citation.url} target="_blank" rel="noreferrer">
                        {citation.page_title}
                        <ArrowUpRight aria-hidden="true" size={13} />
                      </a>
                      <span>
                        核验 {formatDate(citation.verified_at)} · {citation.source_version} · {citation.freshness}
                      </span>
                    </footer>
                  </blockquote>
                ))}
              </details>
            );
          })}
        </div>
      ) : null}
    </article>
  );
}
