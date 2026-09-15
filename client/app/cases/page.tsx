"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, getRuleFrequency, listCases } from "@/lib/api";
import { describeError } from "@/lib/errorMessages";
import type { CaseSummary, RuleFrequencyItem } from "@/lib/types";
import { Banner } from "@/components/Banner";
import { StatusBadge } from "@/components/Badges";

const PER_PAGE = 20;

function shortCaseId(id: string) {
  return id.split("-")[0];
}

export default function CaseListPage() {
  const router = useRouter();
  const [items, setItems] = useState<CaseSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [ranking, setRanking] = useState<RuleFrequencyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listCases(1, PER_PAGE), getRuleFrequency()])
      .then(([caseList, freq]) => {
        setItems(caseList.items);
        setTotal(caseList.total);
        setRanking(freq.items);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
          return;
        }
        setError(describeError(err));
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function loadMore() {
    const nextPage = page + 1;
    const caseList = await listCases(nextPage, PER_PAGE);
    setItems((prev) => [...prev, ...caseList.items]);
    setPage(nextPage);
  }

  return (
    <div className="mx-auto w-full max-w-3xl p-6">
      <h1 className="text-lg font-semibold text-text">전과 기록</h1>
      <p className="mt-1 text-sm text-text-muted">
        지금까지 제출한 사건 목록입니다.
      </p>

      {error && (
        <div className="mt-4">
          <Banner kind="error">{error}</Banner>
        </div>
      )}

      {loading && (
        <p className="mt-6 text-sm text-text-muted">불러오는 중...</p>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="mt-8 rounded border border-border bg-surface p-8 text-center">
          <p className="text-text-muted">아직 판결받은 사건이 없습니다.</p>
          <Link
            href="/submit"
            className="mt-4 inline-block rounded border border-accent bg-accent/10 px-4 py-2 text-sm font-semibold text-accent hover:bg-accent/20"
          >
            코드 제출하기
          </Link>
        </div>
      )}

      {ranking.length > 0 && (
        <div className="mt-6 rounded border border-border bg-surface p-4">
          <h2 className="mb-3 text-sm font-semibold text-text">
            반복 조항 랭킹
          </h2>
          <ol className="space-y-1 text-sm">
            {ranking.map((item, idx) => (
              <li
                key={item.rule_id}
                className="flex items-center justify-between text-text-muted"
              >
                <span>
                  <span className="mr-2 font-mono text-text-faint">
                    {idx + 1}.
                  </span>
                  <span className="font-mono text-xs text-text-faint">
                    {item.rule_id}
                  </span>{" "}
                  {item.rule_title}
                </span>
                <span className="font-mono text-text">{item.count}회</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {items.length > 0 && (
        <div className="mt-6 space-y-2">
          {items.map((c) => (
            <Link
              key={c.case_id}
              href={`/cases/${c.case_id}`}
              className="block rounded border border-border bg-surface p-4 hover:border-accent"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs text-text-faint">
                    CASE-{shortCaseId(c.case_id)}
                  </span>
                  <span className="text-sm text-text">{c.origin_label}</span>
                  <span className="font-mono text-xs text-text-faint">
                    {c.language}
                  </span>
                </div>
                <StatusBadge status={c.status} />
              </div>
              <div className="mt-2 flex items-center gap-4 text-xs text-text-muted">
                <span>
                  기소 {c.charges_count}건 중 채택 {c.sustained_count}건
                </span>
                <span>
                  형량 {c.sentence_progress.done}/{c.sentence_progress.total}{" "}
                  완료
                </span>
                <span>
                  {new Date(c.created_at).toLocaleDateString("ko-KR")}
                </span>
              </div>
            </Link>
          ))}

          {items.length < total && (
            <button
              type="button"
              onClick={loadMore}
              className="w-full rounded border border-border py-2 text-sm text-text-muted hover:border-accent hover:text-accent"
            >
              더 보기 ({items.length} / {total})
            </button>
          )}
        </div>
      )}
    </div>
  );
}
