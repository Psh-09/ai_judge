"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, createCase, getCase } from "@/lib/api";
import { describeError } from "@/lib/errorMessages";
import type { CaseSubmissionResult } from "@/lib/types";
import { Banner } from "@/components/Banner";
import { InfoTooltip } from "@/components/Tooltip";
import { OnboardingCards } from "@/components/OnboardingCards";
import {
  CacheHitModal,
  InProgressModal,
} from "@/components/SubmissionNoticeModal";

const MAX_LINES = 500;
const MAX_CHARS = 20000;
const LANGUAGES = [
  "python",
  "javascript",
  "typescript",
  "java",
  "other",
] as const;
const CREDENTIAL_PATTERN =
  /(api[_-]?key|secret|password|token)\s*[:=]\s*["'][A-Za-z0-9_\-./+]{8,}["']/i;

const LINE_LIMIT_TOOLTIP =
  "심사 정확도와 처리 시간을 위해 한 번에 한 파일, 500줄까지 심사합니다. 긴 파일은 문제가 있다고 의심되는 부분만 잘라 제출하면 판결이 더 정확합니다.";
const RATE_LIMIT_TOOLTIP =
  "24시간 내 20건까지 심사합니다. 이미 판결받은 코드를 다시 열람하는 것과 링크를 불러오다 실패한 경우는 횟수에 포함되지 않습니다.";

type Tab = "paste" | "github";

export default function SubmitPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-1 items-center justify-center text-text-muted">
          불러오는 중...
        </div>
      }
    >
      <SubmitPageInner />
    </Suspense>
  );
}

function SubmitPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [authChecked, setAuthChecked] = useState(false);
  const [tab, setTab] = useState<Tab>("paste");
  const [code, setCode] = useState("");
  const [language, setLanguage] =
    useState<(typeof LANGUAGES)[number]>("python");
  const [repoUrl, setRepoUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [cacheHit, setCacheHit] = useState<CaseSubmissionResult | null>(null);
  const [inProgress, setInProgress] = useState<CaseSubmissionResult | null>(
    null,
  );

  useEffect(() => {
    // 인증 확인을 겸해 가벼운 인증 요청을 한 번 보낸다 — 실패(401)면 로그인 화면으로 보낸다.
    getCase("00000000-0000-0000-0000-000000000000")
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
          return;
        }
      })
      .finally(() => setAuthChecked(true));
  }, [router]);

  useEffect(() => {
    function fillSample() {
      fetch("/sample-code/user_handler.py")
        .then((r) => r.text())
        .then((sampleCode) => {
          setTab("paste");
          setLanguage("python");
          setCode(sampleCode);
        });
    }
    if (searchParams.get("fillSample") === "1") fillSample();
    window.addEventListener("code-court:fill-sample", fillSample);
    return () =>
      window.removeEventListener("code-court:fill-sample", fillSample);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lineCount = code.length === 0 ? 0 : code.split("\n").length;
  const charCount = code.length;
  const overLimit = lineCount > MAX_LINES || charCount > MAX_CHARS;
  const hasCredentialWarning = CREDENTIAL_PATTERN.test(code);

  async function submit(forceRetrial = false) {
    setError(null);
    setSubmitting(true);
    try {
      const payload =
        tab === "paste"
          ? { code, language, force_retrial: forceRetrial }
          : { repo_url: repoUrl, force_retrial: forceRetrial };
      const result = await createCase(payload);
      if (result.cached) {
        setCacheHit(result);
      } else if (result.in_progress) {
        setInProgress(result);
      } else {
        router.push(`/cases/${result.case_id}`);
      }
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit =
    !submitting &&
    (tab === "paste"
      ? code.trim().length > 0 && !overLimit
      : repoUrl.trim().length > 0);

  const showPasteFallback =
    tab === "github" &&
    error &&
    (error.code === "REPO_FILE_UNAVAILABLE" ||
      error.code === "FETCH_RATE_LIMITED");

  if (!authChecked) {
    return (
      <div className="flex flex-1 items-center justify-center text-text-muted">
        확인 중...
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl p-6">
      <OnboardingCards />

      <h1 className="text-lg font-semibold text-text">코드 제출</h1>
      <p className="mt-1 text-sm text-text-muted">
        한 번에 한 파일, 500줄까지 심사합니다. 검사·변호인·판사가 순서대로
        심리합니다.
      </p>
      <p className="mt-1 flex items-center gap-1 text-xs text-text-faint">
        24시간 내 20건까지 제출 가능 <InfoTooltip text={RATE_LIMIT_TOOLTIP} />
      </p>

      <div className="mt-6 flex rounded border border-border bg-surface p-1">
        <button
          type="button"
          onClick={() => setTab("paste")}
          className={`flex-1 rounded py-2 text-sm font-semibold transition ${
            tab === "paste" ? "bg-surface-raised text-text" : "text-text-muted"
          }`}
        >
          붙여넣기
        </button>
        <button
          type="button"
          onClick={() => setTab("github")}
          className={`flex-1 rounded py-2 text-sm font-semibold transition ${
            tab === "github" ? "bg-surface-raised text-text" : "text-text-muted"
          }`}
        >
          GitHub 링크
        </button>
      </div>

      {tab === "paste" ? (
        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between">
            <label className="text-xs font-semibold text-text-muted">
              언어
            </label>
            <select
              value={language}
              onChange={(e) =>
                setLanguage(e.target.value as (typeof LANGUAGES)[number])
              }
              className="rounded border border-border bg-surface px-2 py-1 text-sm text-text outline-none focus:border-accent"
            >
              {LANGUAGES.map((lang) => (
                <option key={lang} value={lang}>
                  {lang === "other" ? "기타" : lang}
                </option>
              ))}
            </select>
          </div>

          {language === "other" && (
            <Banner kind="info">
              언어 종속 조항은 적용되지 않습니다. 공통 조항만으로 심사합니다.
            </Banner>
          )}

          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            rows={16}
            placeholder="코드를 붙여넣으세요"
            className="mt-2 w-full rounded border border-border bg-surface p-3 font-mono text-sm text-text outline-none focus:border-accent"
          />

          <div className="mt-1 flex items-center justify-between text-xs">
            <span className={overLimit ? "text-danger" : "text-text-faint"}>
              {lineCount} / {MAX_LINES}줄 · {charCount} / {MAX_CHARS}자
            </span>
            <InfoTooltip text={LINE_LIMIT_TOOLTIP} />
          </div>

          {hasCredentialWarning && (
            <div className="mt-2">
              <Banner kind="warning">
                코드에 API 키로 보이는 문자열이 있습니다. 제출 전 제거를
                권장합니다.
              </Banner>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-4">
          <label className="mb-1 block text-xs font-semibold text-text-muted">
            GitHub 파일 링크
          </label>
          <input
            type="url"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://github.com/owner/repo/blob/main/src/app.py"
            className="w-full rounded border border-border bg-surface p-3 font-mono text-sm text-text outline-none focus:border-accent"
          />
          <p className="mt-2 text-xs leading-relaxed text-text-muted">
            이 커밋 시점의 파일로 심사합니다. 이후 저장소가 변경되어도 판결은
            유지됩니다. 공개 저장소의 파일만 지원합니다.
          </p>
        </div>
      )}

      {error && (
        <div className="mt-4 space-y-2">
          <Banner kind="error">{describeError(error)}</Banner>
          {showPasteFallback && (
            <button
              type="button"
              onClick={() => {
                setTab("paste");
                setError(null);
              }}
              className="rounded border border-border px-3 py-1.5 text-xs font-semibold text-text-muted hover:border-accent hover:text-accent"
            >
              직접 붙여넣기로 제출
            </button>
          )}
        </div>
      )}

      <button
        type="button"
        onClick={() => submit(false)}
        disabled={!canSubmit}
        className="mt-6 w-full rounded border border-accent bg-accent/10 py-3 text-sm font-semibold text-accent hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {submitting ? "제출 중..." : "제출하고 재판 시작"}
      </button>

      {cacheHit && (
        <CacheHitModal
          originLabel={cacheHit.origin_label}
          onViewExisting={() => router.push(`/cases/${cacheHit.case_id}`)}
          onRetrial={() => {
            setCacheHit(null);
            submit(true);
          }}
          onCancel={() => setCacheHit(null)}
        />
      )}

      {inProgress && (
        <InProgressModal
          onViewProgress={() => router.push(`/cases/${inProgress.case_id}`)}
          onCancel={() => setInProgress(null)}
        />
      )}
    </div>
  );
}
