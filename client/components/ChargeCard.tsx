import type { Charge, Plea, Verdict } from "@/lib/types";
import { SeverityBadge, VerdictBadge } from "./Badges";

function formatLines(start: number, end: number) {
  return start === end ? `L${start}` : `L${start}–L${end}`;
}

export function ChargeCard({
  charge,
  plea,
  verdict,
  onEvidenceClick,
}: {
  charge: Charge;
  plea?: Plea;
  verdict?: Verdict;
  onEvidenceClick: (start: number, end: number) => void;
}) {
  const isDismissed = verdict?.verdict === "DISMISSED";

  return (
    <div
      className={`rounded border p-4 ${
        isDismissed
          ? "border-dashed border-border bg-surface/60"
          : "border-border bg-surface"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-text-faint">
            {charge.rule_id}
          </span>
          <span className="font-semibold text-text">{charge.rule_title}</span>
        </div>
        <div className="flex items-center gap-3">
          {verdict ? (
            <SeverityBadge
              severity={verdict.final_severity ?? charge.charged_severity}
              from={
                verdict.final_severity &&
                verdict.final_severity !== charge.charged_severity
                  ? charge.charged_severity
                  : null
              }
            />
          ) : (
            <SeverityBadge severity={charge.charged_severity} />
          )}
          {verdict && <VerdictBadge verdict={verdict.verdict} />}
        </div>
      </div>

      <button
        type="button"
        onClick={() =>
          onEvidenceClick(charge.evidence_start, charge.evidence_end)
        }
        className="mt-3 inline-flex items-center rounded border border-border bg-surface-raised px-2 py-1 font-mono text-xs text-accent hover:border-accent"
      >
        증거 {formatLines(charge.evidence_start, charge.evidence_end)}
      </button>

      <dl className="mt-3 space-y-2 text-sm leading-relaxed">
        <div>
          <dt className="text-xs font-semibold text-text-faint">검사 주장</dt>
          <dd className="text-text-muted">{charge.description}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-text-faint">변론</dt>
          <dd className="text-text-muted">
            {plea && plea.plea !== "NO_RESPONSE" ? plea.argument : "변론 없음"}
          </dd>
        </div>
        {verdict && (
          <div>
            <dt className="text-xs font-semibold text-text-faint">판정 사유</dt>
            <dd className="text-text">{verdict.reasoning}</dd>
          </div>
        )}
      </dl>
    </div>
  );
}
