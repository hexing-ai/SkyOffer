"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, ShieldCheck } from "lucide-react";

import { AppHeader } from "@/components/AppHeader";
import { ApiError, requestProgramDetail } from "@/lib/api";
import {
  COVERAGE_LABELS,
  DIRECTION_LABELS,
  REGION_LABELS,
  formatDate,
} from "@/lib/program-labels";
import type { ProgramCatalogDetailResponse, ProgramCatalogField } from "@/lib/types";

const GROUPS = ["项目概况", "专业方向", "申请门槛"] as const;

export function ProgramDetail({ programRef }: { programRef: string }) {
  const [data, setData] = useState<ProgramCatalogDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    requestProgramDetail(programRef, controller.signal)
      .then(setData)
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === "AbortError") return;
        setError(
          requestError instanceof ApiError
            ? requestError.message
            : "项目详情加载失败，请稍后重试。",
        );
      });
    return () => controller.abort();
  }, [programRef]);

  const fieldsByGroup = useMemo(() => {
    const grouped = new Map<string, ProgramCatalogField[]>();
    data?.program.fields.forEach((field) => {
      grouped.set(field.group, [...(grouped.get(field.group) ?? []), field]);
    });
    return grouped;
  }, [data]);

  return (
    <>
      <a className="skip-link" href="#program-detail">跳到项目详情</a>
      <AppHeader active="programs" />
      <main id="program-detail" className="detail-page">
        <Link className="back-link" href="/programs"><ArrowLeft aria-hidden="true" size={16} /> 返回项目数据库</Link>
        {!data && !error ? <div className="catalog-state"><span className="loading-dot" />正在读取项目详情</div> : null}
        {error ? <div className="catalog-state catalog-state--error" role="alert"><strong>无法加载项目详情</strong><span>{error}</span><Link href="/programs">返回项目数据库</Link></div> : null}
        {data ? (
          <>
            <header className="detail-hero">
              <div className="detail-hero__main">
                <div className="detail-tags"><span>{REGION_LABELS[data.program.region]}</span><span>{DIRECTION_LABELS[data.program.primary_direction]}</span><span>授课型硕士</span></div>
                <p>{data.program.institution_name}</p>
                <h1>{data.program.official_name}</h1>
              </div>
              <a className="official-button" href={data.program.official_program_url} target="_blank" rel="noreferrer">打开项目官网 <ExternalLink aria-hidden="true" size={16} /></a>
            </header>

            <div className="candidate-boundary" role="note">
              <ShieldCheck aria-hidden="true" size={20} />
              <div><strong>Beta 候选版本</strong><p>已完成领域复核，部分字段仍待补充或再次核验；请以字段下方的官网引用为准。</p></div>
            </div>

            <section className="version-strip" aria-label="数据版本信息">
              <div><span>目标学年</span><strong>{data.program.target_academic_year}</strong></div>
              <div><span>领域复核日期</span><strong>{formatDate(data.program.reviewed_at)}</strong></div>
              <div><span>候选版本</span><strong>{data.program.candidate_version_id}</strong></div>
              <div><span>Program Pack</span><strong>{data.program.pack_ref}</strong></div>
            </section>

            {GROUPS.map((group) => (
              <section className="field-section" key={group} aria-labelledby={`group-${group}`}>
                <div className="field-section__heading"><h2 id={`group-${group}`}>{group}</h2><span>{fieldsByGroup.get(group)?.length ?? 0} 个字段</span></div>
                <div className="field-list">
                  {(fieldsByGroup.get(group) ?? []).map((field) => (
                    <article className="catalog-field" key={field.field_key} data-coverage={field.coverage_status}>
                      <header>
                        <div><h3>{field.label}</h3><code>{field.field_key}</code></div>
                        <div className="field-badges">{field.is_critical ? <span className="critical-chip">关键字段</span> : null}<span className="coverage-chip">{COVERAGE_LABELS[field.coverage_status]}</span></div>
                      </header>
                      <p className="catalog-field__value">{field.display_text}</p>
                      <details className="field-evidence">
                        <summary>查看官网依据（{field.citations.length}）</summary>
                        <div className="evidence-list">
                          {field.citations.map((citation) => (
                            <blockquote key={`${field.field_key}-${citation.evidence_id}-${citation.citation_order}`}>
                              <p>{citation.excerpt}</p>
                              <footer>
                                <div><strong>{citation.page_title}</strong><span>核验日期 {formatDate(citation.verified_at)} · {citation.source_version}</span></div>
                                <a href={citation.url} target="_blank" rel="noreferrer">查看官网原文 <ExternalLink aria-hidden="true" size={14} /></a>
                              </footer>
                            </blockquote>
                          ))}
                        </div>
                      </details>
                    </article>
                  ))}
                </div>
              </section>
            ))}

            <footer className="detail-footer">
              <p>数据集 {data.dataset.dataset_id} · Manifest {data.dataset.manifest_sha256}</p>
            </footer>
          </>
        ) : null}
      </main>
    </>
  );
}
