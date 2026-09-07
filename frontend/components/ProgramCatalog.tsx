"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Database, Search, ShieldCheck } from "lucide-react";

import { ApiError, requestProgramCatalog } from "@/lib/api";
import { DIRECTION_LABELS, REGION_LABELS, formatDate } from "@/lib/program-labels";
import type { Direction, ProgramCatalogListResponse, Region } from "@/lib/types";
import { AppHeader } from "@/components/AppHeader";

type ReviewFilter = "all" | "domain_reviewed" | "has_unresolved_fields";

export function ProgramCatalog() {
  const [data, setData] = useState<ProgramCatalogListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState<"all" | Region>("all");
  const [direction, setDirection] = useState<"all" | Direction>("all");
  const [review, setReview] = useState<ReviewFilter>("all");

  useEffect(() => {
    const controller = new AbortController();
    requestProgramCatalog(controller.signal)
      .then(setData)
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === "AbortError") return;
        setError(
          requestError instanceof ApiError
            ? requestError.message
            : "项目数据库加载失败，请稍后重试。",
        );
      });
    return () => controller.abort();
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [];
    const keyword = query.trim().toLocaleLowerCase();
    return data.programs.filter((program) => {
      const matchesQuery = !keyword || `${program.official_name} ${program.institution_name}`
        .toLocaleLowerCase()
        .includes(keyword);
      const matchesRegion = region === "all" || program.region === region;
      const directions = [program.primary_direction, ...program.secondary_directions];
      const matchesDirection = direction === "all" || directions.includes(direction);
      const matchesReview = review === "all"
        || (review === "domain_reviewed" && program.review_status === "domain_reviewed")
        || (review === "has_unresolved_fields" && program.has_unresolved_fields);
      return matchesQuery && matchesRegion && matchesDirection && matchesReview;
    });
  }, [data, direction, query, region, review]);

  return (
    <>
      <a className="skip-link" href="#catalog-results">跳到项目列表</a>
      <AppHeader active="programs" />
      <main className="catalog-page">
        <header className="catalog-heading">
          <div>
            <p className="overline">公开 Beta 数据</p>
            <h1>项目数据库</h1>
            <p>搜索项目并查看申请门槛与官网依据。</p>
          </div>
          <div className="catalog-heading__count" aria-label="当前项目数量">
            <strong>{data?.dataset.program_count ?? "—"}</strong>
            <span>个项目</span>
          </div>
        </header>

        <div className="catalog-boundary" role="note">
          <ShieldCheck aria-hidden="true" size={18} />
          <p><strong>Beta 候选数据</strong> 已通过领域复核，但部分字段仍待官网补充或再次核验；请以字段下方的官网引用为准。</p>
        </div>

        <section className="catalog-filters" aria-label="项目筛选">
          <label className="catalog-search">
            <span>搜索学校或项目</span>
            <span className="catalog-search__input"><Search aria-hidden="true" size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入学校或项目名称" /></span>
          </label>
          <label><span>地区</span><select value={region} onChange={(event) => setRegion(event.target.value as "all" | Region)}><option value="all">全部地区</option><option value="hong_kong">香港</option><option value="united_kingdom">英国</option></select></label>
          <label><span>专业方向</span><select value={direction} onChange={(event) => setDirection(event.target.value as "all" | Direction)}><option value="all">全部方向</option>{Object.entries(DIRECTION_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label><span>核验状态</span><select value={review} onChange={(event) => setReview(event.target.value as ReviewFilter)}><option value="all">全部状态</option><option value="domain_reviewed">领域复核通过</option><option value="has_unresolved_fields">含待核验字段</option></select></label>
        </section>

        <section id="catalog-results" className="catalog-results" aria-live="polite">
          {!data && !error ? (
            <div className="catalog-state"><span className="loading-dot" />正在读取项目数据</div>
          ) : null}
          {error ? (
            <div className="catalog-state catalog-state--error" role="alert"><strong>无法加载项目数据库</strong><span>{error}</span></div>
          ) : null}
          {data ? (
            <>
              <div className="catalog-results__meta"><strong>{filtered.length}</strong> 个项目<span>数据版本 {data.dataset.manifest_sha256.slice(0, 10)}</span></div>
              {filtered.length ? (
                <div className="catalog-grid">
                  {filtered.map((program) => {
                    const confirmedRate = Math.round((program.coverage.confirmed / program.coverage.total) * 100);
                    return (
                      <article className="catalog-card" key={program.program_ref}>
                        <div className="catalog-card__topline">
                          <span>{REGION_LABELS[program.region]}</span>
                          <span>{DIRECTION_LABELS[program.primary_direction]}</span>
                          <span className="review-chip">领域复核通过</span>
                        </div>
                        <p className="catalog-card__institution">{program.institution_name}</p>
                        <h2>{program.official_name}</h2>
                        <dl className="catalog-card__facts">
                          <div><dt>入学年份</dt><dd>{program.target_academic_year.replace("-", "/")}</dd></div>
                          <div><dt>官网证据</dt><dd>{program.evidence_count} 个来源</dd></div>
                          <div><dt>最近复核</dt><dd>{formatDate(program.reviewed_at)}</dd></div>
                        </dl>
                        <div className="coverage-line">
                          <div><span>已确认字段</span><strong>{program.coverage.confirmed} / {program.coverage.total}</strong></div>
                          <span className="coverage-track" aria-label={`已确认 ${confirmedRate}%`}><i style={{ width: `${confirmedRate}%` }} /></span>
                          {program.coverage.unresolved ? <small>{program.coverage.unresolved} 个字段仍需核验或补充</small> : <small>全部字段已确认</small>}
                        </div>
                        <Link className="catalog-card__link" href={`/programs/${program.program_ref}`}>查看项目详情与官网依据 <ArrowRight aria-hidden="true" size={16} /></Link>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <div className="catalog-state"><Database aria-hidden="true" size={24} /><strong>没有符合当前条件的项目</strong><span>修改搜索词或筛选条件后重试。</span></div>
              )}
            </>
          ) : null}
        </section>
      </main>
    </>
  );
}
