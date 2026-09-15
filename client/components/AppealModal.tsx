"use client";

import { useState } from "react";

const MIN_LENGTH = 20;

export function AppealModal({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (rebuttal: string) => Promise<void>;
}) {
  const [rebuttal, setRebuttal] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tooShort = rebuttal.trim().length < MIN_LENGTH;

  async function handleSubmit() {
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit(rebuttal.trim());
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "항소 접수에 실패했습니다.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-lg rounded border border-border bg-surface p-6">
        <h2 className="text-lg font-semibold text-text">항소하기</h2>

        <p className="mt-3 rounded border border-warning/40 bg-warning/10 p-3 text-xs leading-relaxed text-warning">
          항소는 사건당 1회만 가능하며, 접수 시점에 기회가 소진됩니다. 재심이
          실패해도 다시 항소할 수 없습니다.
        </p>

        <div className="mt-4 rounded border border-border bg-surface-raised p-3 text-xs leading-relaxed text-text-muted">
          <p>
            판사는 사용자 주장 자체를 근거로 인정하지 않습니다. 코드와 조항에
            비추어 왜 적용이 과한지를 쓰면 반영될 가능성이 높습니다.
          </p>
          <p className="mt-2 text-complete">
            좋은 예: “이 함수는 단일 진입점 스크립트에서만 호출되므로 전역 변수
            사용이 의도된 설계입니다”
          </p>
          <p className="mt-1 text-danger">
            나쁜 예: “이건 문제 아닙니다” / “다시 봐주세요”
          </p>
        </div>

        <textarea
          value={rebuttal}
          onChange={(e) => setRebuttal(e.target.value)}
          rows={5}
          placeholder="반박 사유를 입력하세요 (20자 이상)"
          className="mt-4 w-full rounded border border-border bg-bg p-3 font-sans text-sm text-text outline-none focus:border-accent"
        />
        <div className="mt-1 flex justify-between text-xs">
          <span className={tooShort ? "text-danger" : "text-complete"}>
            {rebuttal.trim().length} / {MIN_LENGTH}자 이상
          </span>
        </div>

        {error && (
          <p className="mt-2 rounded border border-danger/40 bg-danger/10 p-2 text-xs text-danger">
            {error}
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded border border-border px-4 py-2 text-sm text-text-muted hover:border-text-faint"
          >
            취소
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={tooShort || submitting}
            className="rounded border border-accent bg-accent/10 px-4 py-2 text-sm font-semibold text-accent hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting ? "접수 중..." : "항소 접수"}
          </button>
        </div>
      </div>
    </div>
  );
}
