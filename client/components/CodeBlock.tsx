export interface EvidenceMarker {
  start: number;
  end: number;
  /** severity 색상 등 마커 강조에 쓸 클래스 */
  className?: string;
}

export function CodeBlock({
  code,
  markers = [],
  highlight,
}: {
  code: string;
  markers?: EvidenceMarker[];
  /** 클릭된 증거 라인 범위 — 하이라이트 배경 + 좌측 마커 이중 표기 */
  highlight?: { start: number; end: number } | null;
}) {
  const lines = code.split("\n");

  return (
    <div className="overflow-x-auto rounded border border-border bg-surface">
      <table className="w-full border-collapse font-mono text-[13px] leading-[1.4]">
        <tbody>
          {lines.map((line, idx) => {
            const lineNo = idx + 1;
            const isCharged = markers.some(
              (m) => lineNo >= m.start && lineNo <= m.end,
            );
            const isHighlighted =
              !!highlight &&
              lineNo >= highlight.start &&
              lineNo <= highlight.end;
            return (
              <tr
                key={lineNo}
                id={`code-line-${lineNo}`}
                className={isHighlighted ? "bg-accent/15" : undefined}
              >
                <td
                  className={`select-none whitespace-nowrap border-r px-2 py-0.5 text-right align-top ${
                    isHighlighted
                      ? "border-r-accent bg-accent/25 text-accent"
                      : isCharged
                        ? "border-r-severity-high/60 text-text-faint"
                        : "border-r-border text-text-faint"
                  }`}
                  style={{
                    borderRightWidth:
                      isCharged || isHighlighted ? "3px" : "1px",
                  }}
                >
                  {lineNo}
                </td>
                <td className="whitespace-pre px-3 py-0.5 align-top text-text">
                  {line || " "}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function scrollToLine(lineNo: number) {
  const el = document.getElementById(`code-line-${lineNo}`);
  el?.scrollIntoView({ behavior: "smooth", block: "center" });
}
