import type { Effort, Severity, VerdictValue } from "@/lib/types";

const SEVERITY_LABEL: Record<Severity, string> = {
  HIGH: "HIGH",
  MEDIUM: "MEDIUM",
  LOW: "LOW",
};

const SEVERITY_COLOR: Record<Severity, string> = {
  HIGH: "text-severity-high border-severity-high/60 bg-severity-high/10",
  MEDIUM:
    "text-severity-medium border-severity-medium/60 bg-severity-medium/10",
  LOW: "text-severity-low border-severity-low/50 bg-severity-low/10",
};

export function SeverityBadge({
  severity,
  from,
}: {
  severity: Severity;
  /** 변경 전 severity — 있으면 "from → severity" 형태로 변화를 표기한다 */
  from?: Severity | null;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs">
      {from && from !== severity && (
        <>
          <span
            className={`rounded border px-1.5 py-0.5 ${SEVERITY_COLOR[from]} opacity-60`}
          >
            {SEVERITY_LABEL[from]}
          </span>
          <span className="text-text-faint">→</span>
        </>
      )}
      <span
        className={`rounded border px-1.5 py-0.5 ${SEVERITY_COLOR[severity]}`}
      >
        {SEVERITY_LABEL[severity]}
      </span>
    </span>
  );
}

const EFFORT_COLOR: Record<Effort, string> = {
  SMALL: "text-effort-small border-effort-small/50 bg-effort-small/10",
  MEDIUM: "text-effort-medium border-effort-medium/50 bg-effort-medium/10",
  LARGE: "text-effort-large border-effort-large/50 bg-effort-large/10",
};

const EFFORT_BARS: Record<Effort, number> = { SMALL: 1, MEDIUM: 2, LARGE: 3 };

export function EffortBadge({ effort }: { effort: Effort }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-xs ${EFFORT_COLOR[effort]}`}
    >
      <span className="flex items-end gap-px" aria-hidden>
        {[1, 2, 3].map((bar) => (
          <span
            key={bar}
            className="block w-1 rounded-sm"
            style={{
              height: `${bar * 3}px`,
              backgroundColor:
                bar <= EFFORT_BARS[effort] ? "currentColor" : "transparent",
              border:
                bar <= EFFORT_BARS[effort] ? "none" : "1px solid currentColor",
            }}
          />
        ))}
      </span>
      {effort}
    </span>
  );
}

const VERDICT_LABEL: Record<VerdictValue, string> = {
  SUSTAINED: "채택",
  REDUCED: "감형",
  DISMISSED: "기각",
};

export function VerdictBadge({ verdict }: { verdict: VerdictValue }) {
  const base =
    "inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold";
  if (verdict === "SUSTAINED") {
    return (
      <span className={`${base} border border-text bg-text text-bg`}>
        {VERDICT_LABEL[verdict]}
      </span>
    );
  }
  if (verdict === "REDUCED") {
    return (
      <span className={`${base} border border-text text-text`}>
        {VERDICT_LABEL[verdict]}
      </span>
    );
  }
  return (
    <span
      className={`${base} border border-dashed border-text-faint text-text-muted`}
    >
      {VERDICT_LABEL[verdict]}
    </span>
  );
}

const STATUS_LABEL: Record<string, string> = {
  QUEUED_PROSECUTION: "검사 대기",
  PROSECUTING: "검사 중",
  QUEUED_DEFENSE: "변호 대기",
  DEFENDING: "변호 중",
  QUEUED_JUDGMENT: "판결 대기",
  JUDGING: "판결 중",
  SENTENCED: "판결 확정",
  DISMISSED: "무혐의",
  QUEUED_REJUDGMENT: "재심 대기",
  REJUDGING: "재심 중",
  FAILED: "실패",
};

export function StatusBadge({ status }: { status: string }) {
  const isTerminal = status === "SENTENCED" || status === "DISMISSED";
  const isFailed = status === "FAILED";
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-1 text-xs font-semibold ${
        isFailed
          ? "border border-danger/60 bg-danger/10 text-danger"
          : isTerminal
            ? "border border-accent/60 bg-accent/10 text-accent"
            : "border border-border bg-surface-raised text-text-muted"
      }`}
    >
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}
