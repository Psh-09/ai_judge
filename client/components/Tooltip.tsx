"use client";

import { useState } from "react";

/**
 * 마우스 호버 전용 title 속성 대신 실제 버튼으로 구현한다 — 포커스+Enter/Space로도
 * 열 수 있어야 키보드 사용자에게도 안내가 닿는다(docs/design.md 11장).
 */
export function InfoTooltip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label="안내"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-text-faint text-[10px] leading-none text-text-faint hover:border-accent hover:text-accent"
      >
        ?
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute bottom-full left-1/2 z-20 mb-2 w-64 -translate-x-1/2 rounded border border-border bg-surface-raised p-2 text-left text-xs font-normal leading-relaxed text-text-muted shadow-lg"
        >
          {text}
        </span>
      )}
    </span>
  );
}
