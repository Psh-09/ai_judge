"use client";

export function CacheHitModal({
  originLabel,
  onViewExisting,
  onRetrial,
  onCancel,
}: {
  originLabel: string | null | undefined;
  onViewExisting: () => void;
  onRetrial: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-md rounded border border-border bg-surface p-6">
        <h2 className="text-lg font-semibold text-text">
          이미 판결된 코드입니다
        </h2>
        {originLabel && (
          <p className="mt-2 font-mono text-xs text-text-faint">
            출처: {originLabel}
          </p>
        )}
        <p className="mt-3 text-sm leading-relaxed text-text-muted">
          같은 코드는 재판을 다시 열지 않습니다. 다시 재판하면 새 사건이
          생성되고 제출 횟수가 소모됩니다.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-border px-4 py-2 text-sm text-text-muted hover:border-text-faint"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onRetrial}
            className="rounded border border-border px-4 py-2 text-sm text-text-muted hover:border-text-faint"
          >
            다시 재판하기
          </button>
          <button
            type="button"
            onClick={onViewExisting}
            className="rounded border border-accent bg-accent/10 px-4 py-2 text-sm font-semibold text-accent hover:bg-accent/20"
          >
            기존 판결 보기
          </button>
        </div>
      </div>
    </div>
  );
}

export function InProgressModal({
  onViewProgress,
  onCancel,
}: {
  onViewProgress: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-md rounded border border-border bg-surface p-6">
        <h2 className="text-lg font-semibold text-text">
          이 코드는 현재 심사 중입니다
        </h2>
        <p className="mt-3 text-sm leading-relaxed text-text-muted">
          같은 코드에 대한 사건이 이미 진행되고 있습니다. 완료될 때까지 기다려
          주세요.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-border px-4 py-2 text-sm text-text-muted hover:border-text-faint"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onViewProgress}
            className="rounded border border-accent bg-accent/10 px-4 py-2 text-sm font-semibold text-accent hover:bg-accent/20"
          >
            진행 상황 보기
          </button>
        </div>
      </div>
    </div>
  );
}
