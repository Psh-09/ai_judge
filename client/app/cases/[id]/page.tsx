"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  appealCase,
  getCase,
  getCaseProgress,
  toggleSentence,
} from "@/lib/api";
import { describeError } from "@/lib/errorMessages";
import type { CaseDetail, CaseStatus } from "@/lib/types";
import { Banner } from "@/components/Banner";
import { CodeBlock, scrollToLine } from "@/components/CodeBlock";
import { ChargeCard } from "@/components/ChargeCard";
import { ProgressStages } from "@/components/ProgressStages";
import { EffortBadge, StatusBadge } from "@/components/Badges";
import { AppealModal } from "@/components/AppealModal";

const TERMINAL: CaseStatus[] = ["SENTENCED", "DISMISSED", "FAILED"];
const POLL_INTERVAL_MS = 2000;

function shortCaseId(id: string) {
  return id.split("-")[0];
}

export default function CaseDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<{
    start: number;
    end: number;
  } | null>(null);
  const [appealOpen, setAppealOpen] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadDetail = useCallback(async () => {
    try {
      const data = await getCase(id);
      setDetail(data);
      return data;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
        return null;
      }
      setError(describeError(err));
      return null;
    }
  }, [id, router]);

  useEffect(() => {
    let cancelled = false;

    async function start() {
      const data = await loadDetail();
      if (cancelled || !data) return;
      if (TERMINAL.includes(data.status)) return;

      intervalRef.current = setInterval(async () => {
        try {
          const progress = await getCaseProgress(id);
          if (TERMINAL.includes(progress.status)) {
            if (intervalRef.current) clearInterval(intervalRef.current);
            await loadDetail();
          } else {
            setDetail((prev) =>
              prev ? { ...prev, status: progress.status } : prev,
            );
          }
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) {
            if (intervalRef.current) clearInterval(intervalRef.current);
            router.replace("/login");
          }
        }
      }, POLL_INTERVAL_MS);
    }

    start();

    return () => {
      cancelled = true;
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  function handleEvidenceClick(start: number, end: number) {
    setHighlight({ start, end });
    scrollToLine(start);
  }

  async function handleSentenceToggle(sentenceId: string, completed: boolean) {
    const result = await toggleSentence(sentenceId, completed);
    setDetail((prev) => {
      if (!prev || !prev.judgment) return prev;
      return {
        ...prev,
        judgment: {
          ...prev.judgment,
          sentences: prev.judgment.sentences.map((s) =>
            s.sentence_id === sentenceId
              ? { ...s, completed_at: result.completed_at }
              : s,
          ),
        },
      };
    });
  }

  async function handleAppealSubmit(rebuttal: string) {
    const progress = await appealCase(id, rebuttal);
    setAppealOpen(false);
    setDetail((prev) =>
      prev
        ? {
            ...prev,
            status: progress.status,
            appeal_used: progress.appeal_used,
          }
        : prev,
    );
    intervalRef.current = setInterval(async () => {
      const p = await getCaseProgress(id);
      if (TERMINAL.includes(p.status)) {
        if (intervalRef.current) clearInterval(intervalRef.current);
        await loadDetail();
      } else {
        setDetail((prev) => (prev ? { ...prev, status: p.status } : prev));
      }
    }, POLL_INTERVAL_MS);
  }

  if (error) {
    return (
      <div className="mx-auto w-full max-w-3xl p-6">
        <Banner kind="error">{error}</Banner>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex flex-1 items-center justify-center text-text-muted">
        불러오는 중...
      </div>
    );
  }

  const inProgress = !TERMINAL.includes(detail.status);

  return (
    <div className="mx-auto w-full max-w-5xl p-6">
      <header className="mb-6 flex items-center justify-between border-b border-border pb-4">
        <div>
          <p className="font-mono text-xs text-text-faint">
            CASE-{shortCaseId(detail.case_id)}
          </p>
          <p className="mt-1 font-mono text-sm text-text-muted">
            {detail.language.toUpperCase()}
          </p>
        </div>
        <StatusBadge status={detail.status} />
      </header>

      {inProgress && (
        <ProgressStages
          status={detail.status}
          failedStage={detail.failed_stage}
        />
      )}

      {detail.status === "FAILED" && (
        <FailedView
          detail={detail}
          onEvidenceClick={handleEvidenceClick}
          highlight={highlight}
        />
      )}

      {detail.status === "DISMISSED" && <DismissedView detail={detail} />}

      {detail.status === "SENTENCED" && (
        <JudgmentView
          detail={detail}
          highlight={highlight}
          onEvidenceClick={handleEvidenceClick}
          onToggleSentence={handleSentenceToggle}
          onAppeal={() => setAppealOpen(true)}
        />
      )}

      {appealOpen && (
        <AppealModal
          onClose={() => setAppealOpen(false)}
          onSubmit={handleAppealSubmit}
        />
      )}
    </div>
  );
}

function FailedView({
  detail,
  highlight,
  onEvidenceClick,
}: {
  detail: CaseDetail;
  highlight: { start: number; end: number } | null;
  onEvidenceClick: (start: number, end: number) => void;
}) {
  return (
    <div className="mt-6 space-y-4">
      <Banner kind="error">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span>
            심사에 실패했습니다 ({detail.failed_stage ?? "알 수 없는 단계"} ·{" "}
            {detail.failure_reason ?? "원인 미상"}). 완료된 단계까지는 확인할 수
            있습니다.
          </span>
          <span className="flex shrink-0 gap-2">
            {detail.charges.length > 0 && (
              <a
                href="#failed-charges"
                className="rounded border border-danger/40 px-3 py-1.5 text-xs font-semibold text-danger hover:bg-danger/10"
              >
                기소장 보기
              </a>
            )}
            <a
              href="/submit"
              className="rounded border border-accent bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent/20"
            >
              다시 제출
            </a>
          </span>
        </div>
      </Banner>
      {detail.charges.length > 0 && (
        <div id="failed-charges">
          <h2 className="mb-2 text-sm font-semibold text-text">
            기소장 (완료된 단계까지)
          </h2>
          <div className="space-y-3">
            {detail.charges.map((charge) => (
              <ChargeCard
                key={charge.charge_index}
                charge={charge}
                plea={detail.pleas.find(
                  (p) => p.charge_index === charge.charge_index,
                )}
                onEvidenceClick={onEvidenceClick}
              />
            ))}
          </div>
        </div>
      )}
      <CodeBlock
        code={detail.code}
        markers={detail.charges.map((c) => ({
          start: c.evidence_start,
          end: c.evidence_end,
        }))}
        highlight={highlight}
      />
    </div>
  );
}

function DismissedView({ detail }: { detail: CaseDetail }) {
  return (
    <div className="mt-6 space-y-4">
      <div className="rounded border border-border bg-surface p-6 text-center">
        <p className="text-lg font-semibold text-text">
          기소 가능한 위반이 발견되지 않았습니다
        </p>
        <p className="mt-2 text-sm text-text-muted">
          {detail.language.toUpperCase()} 법전 조항을 기준으로 심사했습니다.
        </p>
      </div>
      <CodeBlock code={detail.code} />
    </div>
  );
}

function JudgmentView({
  detail,
  highlight,
  onEvidenceClick,
  onToggleSentence,
  onAppeal,
}: {
  detail: CaseDetail;
  highlight: { start: number; end: number } | null;
  onEvidenceClick: (start: number, end: number) => void;
  onToggleSentence: (sentenceId: string, completed: boolean) => void;
  onAppeal: () => void;
}) {
  const judgment = detail.judgment;
  if (!judgment) return null;

  const counts = { SUSTAINED: 0, REDUCED: 0, DISMISSED: 0 };
  for (const v of judgment.verdicts) counts[v.verdict]++;

  const doneCount = judgment.sentences.filter((s) => s.completed_at).length;
  const statusBanner = judgmentStatusBanner(detail);

  return (
    <div className="mt-6 space-y-4">
      {statusBanner && (
        <Banner kind={statusBanner.kind}>{statusBanner.text}</Banner>
      )}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="space-y-4 lg:sticky lg:top-6 lg:self-start">
          {detail.origin.type === "github" && (
            <div className="rounded border border-border bg-surface p-3 text-xs">
              <p className="font-mono text-text-muted">
                {detail.origin.repo_url?.replace("https://github.com/", "")} ·{" "}
                <span className="text-accent">{detail.origin.commit_sha}</span>{" "}
                · {detail.origin.file_path}
              </p>
              <a
                href={detail.origin.repo_url ?? "#"}
                target="_blank"
                rel="noreferrer"
                className="mt-1 inline-block text-accent hover:underline"
              >
                GitHub에서 보기 ↗
              </a>
            </div>
          )}
          <CodeBlock
            code={detail.code}
            markers={detail.charges.map((c) => ({
              start: c.evidence_start,
              end: c.evidence_end,
            }))}
            highlight={highlight}
          />
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between text-sm">
            <span className="text-text-muted">
              기소 {detail.charges.length}건
            </span>
            <span className="flex gap-4 font-mono">
              <span className="text-text">
                {counts.SUSTAINED} <span className="text-text-faint">채택</span>
              </span>
              <span className="text-text">
                {counts.REDUCED} <span className="text-text-faint">감형</span>
              </span>
              <span className="text-text">
                {counts.DISMISSED} <span className="text-text-faint">기각</span>
              </span>
            </span>
          </div>

          <blockquote className="border-l-2 border-accent bg-surface p-4 text-sm leading-[1.7] text-text">
            <p className="mb-1 text-xs font-semibold text-text-faint">
              판사 총평
            </p>
            {judgment.opinion}
          </blockquote>

          {judgment.precedent_verdict_ids.length > 0 && (
            <p className="text-xs text-text-faint">
              유사 판례 {judgment.precedent_verdict_ids.length}건 참고
            </p>
          )}

          <div className="space-y-3">
            {detail.charges.map((charge) => (
              <ChargeCard
                key={charge.charge_index}
                charge={charge}
                plea={detail.pleas.find(
                  (p) => p.charge_index === charge.charge_index,
                )}
                verdict={judgment.verdicts.find(
                  (v) => v.charge_index === charge.charge_index,
                )}
                onEvidenceClick={onEvidenceClick}
              />
            ))}
          </div>

          {judgment.sentences.length > 0 && (
            <div className="rounded border border-border bg-surface p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-text">
                  형량 {judgment.sentences.length}건
                </h2>
                <span className="font-mono text-xs text-text-muted">
                  {doneCount} / {judgment.sentences.length} 완료
                </span>
              </div>
              <div className="mb-3 h-1.5 overflow-hidden rounded bg-surface-raised">
                <div
                  className="h-full bg-complete transition-all"
                  style={{
                    width: `${judgment.sentences.length ? (doneCount / judgment.sentences.length) * 100 : 0}%`,
                  }}
                />
              </div>
              <ul className="space-y-2">
                {judgment.sentences.map((sentence) => (
                  <li
                    key={sentence.sentence_id}
                    className="flex items-start gap-3 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={!!sentence.completed_at}
                      onChange={(e) =>
                        onToggleSentence(sentence.sentence_id, e.target.checked)
                      }
                      className="mt-1 h-4 w-4 accent-[color:var(--color-complete)]"
                    />
                    <div className="flex-1">
                      <p
                        className={
                          sentence.completed_at
                            ? "text-text-faint line-through"
                            : "text-text"
                        }
                      >
                        {sentence.task}
                        {sentence.advisory && (
                          <span className="ml-2 rounded border border-border px-1 py-0.5 text-[10px] text-text-faint">
                            권고
                          </span>
                        )}
                      </p>
                      <div className="mt-1 flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() =>
                            onEvidenceClick(
                              sentence.target_start,
                              sentence.target_end,
                            )
                          }
                          className="font-mono text-xs text-accent hover:underline"
                        >
                          {sentence.target_start === sentence.target_end
                            ? `L${sentence.target_start}`
                            : `L${sentence.target_start}–L${sentence.target_end}`}
                        </button>
                        <EffortBadge effort={sentence.effort} />
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!detail.appeal_used && (
            <button
              type="button"
              onClick={onAppeal}
              className="w-full rounded border border-accent bg-accent/10 py-3 text-sm font-semibold text-accent hover:bg-accent/20"
            >
              항소하기
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function judgmentStatusBanner(
  detail: CaseDetail,
): { text: string; kind: "info" | "warning" } | null {
  if (detail.revision === 1 && detail.appeal_used) {
    return { text: "재심 확정 (최종)", kind: "info" };
  }
  if (detail.revision === 0 && detail.appeal_used) {
    return {
      text: "원심 확정 (재심 실패) — 원심 판결이 유지됩니다.",
      kind: "warning",
    };
  }
  if (detail.revision === 0 && !detail.appeal_used) {
    return { text: "판결 확정 (항소 가능)", kind: "info" };
  }
  return null;
}
