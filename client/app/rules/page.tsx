"use client";

import { useEffect, useState } from "react";
import { listRules } from "@/lib/api";
import { describeError } from "@/lib/errorMessages";
import type { Rule } from "@/lib/types";
import { Banner } from "@/components/Banner";
import { EffortBadge, SeverityBadge } from "@/components/Badges";

const CATEGORY_LABELS: Record<string, string> = {
  SECURITY: "SECURITY · 외부 입력을 신뢰하는 지점",
  ERROR: "ERROR · 실패를 처리하거나 은폐하는 방식",
  STRUCTURE: "STRUCTURE · 책임 분리, 길이, 중첩",
  NAMING: "NAMING · 식별자가 의미를 드러내는가",
  PERF: "PERF · 정적으로 확인 가능한 비효율",
  STYLE: "STYLE · 가독성",
};

const CATEGORY_ORDER = [
  "SECURITY",
  "ERROR",
  "STRUCTURE",
  "NAMING",
  "PERF",
  "STYLE",
];

// GET /rules는 활성 조항만 반환하고, 법전에서 제외한 후보는 API에 없다 — rules.yaml의
// excluded_candidates를 그대로 옮겨왔다(§6.6 "이 서비스가 보지 않는 것").
const EXCLUDED_CANDIDATES: { candidate: string; reason: string }[] = [
  {
    candidate: "설계에 확장성이 없다",
    reason: "위반 위치를 라인으로 지목할 수 없어 기소 형식으로 표현되지 않는다",
  },
  {
    candidate: "들여쓰기·줄바꿈이 일관되지 않다",
    reason: "포매터가 자동 처리하는 항목으로, 사람이 판단할 가치가 없다",
  },
  {
    candidate: "이 반복문이 느리다",
    reason: "코드를 실행하지 않으므로 실측 근거를 댈 수 없다",
  },
  {
    candidate: "주석이 부족하다",
    reason: "적정량이 팀 규약에 따라 갈려 판정이 객관적이지 않다",
  },
  {
    candidate: "파일 구조가 관례에 맞지 않다",
    reason: "단일 파일만 심사하므로 판정 자체가 불가능하다",
  },
  {
    candidate: "테스트가 없다",
    reason: "제출 대상 파일 밖의 사실이라 지목할 라인이 없다",
  },
];

export default function RulesPage() {
  const [rules, setRules] = useState<Rule[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    listRules()
      .then(setRules)
      .catch((err) => setError(describeError(err)));
  }, []);

  const filtered = (rules ?? []).filter((rule) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return (
      rule.title.toLowerCase().includes(q) ||
      rule.description.toLowerCase().includes(q)
    );
  });

  const byCategory = new Map<string, Rule[]>();
  for (const rule of filtered) {
    const list = byCategory.get(rule.category) ?? [];
    list.push(rule);
    byCategory.set(rule.category, list);
  }
  const categories = [...byCategory.keys()].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b),
  );

  return (
    <div className="mx-auto w-full max-w-3xl p-6">
      <h1 className="text-lg font-semibold text-text">법전</h1>
      <p className="mt-1 text-sm text-text-muted">
        이 서비스가 코드에서 무엇을 지적하는지 조항 목록이 그대로 설명합니다.
      </p>

      <div className="mt-6 rounded border border-border bg-surface p-4">
        <p className="mb-2 text-xs font-semibold text-text-faint">
          조항 선정 기준
        </p>
        <ul className="space-y-1 text-sm text-text-muted">
          <li>
            · 라인 지목 가능 — 위반 위치를 코드 라인으로 특정할 수 있어야 한다
          </li>
          <li>
            · 판정 객관성 — 프로젝트 규약에 따라 옳고 그름이 갈리지 않아야 한다
          </li>
          <li>
            · 실행 불필요 — 코드를 실행하지 않고 정적으로 판정 가능해야 한다
          </li>
        </ul>
      </div>

      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="조항명·설명 검색"
        className="mt-6 w-full rounded border border-border bg-surface p-3 text-sm text-text outline-none focus:border-accent"
      />

      {error && (
        <div className="mt-4">
          <Banner kind="error">{error}</Banner>
        </div>
      )}

      {!rules && !error && (
        <p className="mt-6 text-sm text-text-muted">불러오는 중...</p>
      )}

      <div className="mt-6 space-y-8">
        {categories.map((category) => (
          <div key={category}>
            <h2 className="mb-3 font-mono text-xs font-semibold text-text-faint">
              {CATEGORY_LABELS[category] ?? category}
            </h2>
            <div className="space-y-3">
              {byCategory.get(category)!.map((rule) => (
                <div
                  key={rule.rule_id}
                  className="rounded border border-border bg-surface p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-text-faint">
                        {rule.rule_id}
                      </span>
                      <span className="font-semibold text-text">
                        {rule.title}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={rule.default_severity} />
                      <EffortBadge effort={rule.typical_effort} />
                    </div>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-text-muted">
                    {rule.description}
                  </p>
                  <p className="mt-2 font-mono text-xs text-text-faint">
                    {rule.languages.length > 0
                      ? rule.languages.join(", ")
                      : "전 언어 공통"}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ))}
        {rules && filtered.length === 0 && (
          <p className="text-sm text-text-muted">검색 결과가 없습니다.</p>
        )}
      </div>

      <div className="mt-10 rounded border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-semibold text-text">
          이 서비스가 보지 않는 것
        </h2>
        <ul className="space-y-3 text-sm">
          {EXCLUDED_CANDIDATES.map((item) => (
            <li key={item.candidate}>
              <p className="text-text-muted line-through decoration-text-faint">
                {item.candidate}
              </p>
              <p className="text-text-faint">{item.reason}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
