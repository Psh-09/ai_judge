"use client";

import { useSyncExternalStore } from "react";
import Link from "next/link";

const DISMISS_KEY = "code-court:onboarding-dismissed";
const listeners = new Set<() => void>();

function subscribe(callback: () => void) {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

function isDismissed() {
  return localStorage.getItem(DISMISS_KEY) === "1";
}

// SSR에는 localStorage가 없다 — 서버 스냅샷은 항상 숨김으로 두고, 클라이언트
// 하이드레이션 이후 실제 값으로 즉시 교정한다(깜빡임은 나더라도 불일치 경고는 없다).
function getServerSnapshot() {
  return true;
}

function dismiss() {
  localStorage.setItem(DISMISS_KEY, "1");
  listeners.forEach((notify) => notify());
}

const CARDS = [
  {
    title: "무엇을 심사하나",
    body: "GitHub 파일 링크 또는 붙여넣은 코드 한 파일을 심사합니다. 저장소 전체나 여러 파일은 심사하지 않습니다.",
  },
  {
    title: "어떻게 심사하나",
    body: "검사가 기소하고, 변호인이 반박하고, 판사가 채택·감형·기각을 결정합니다. 기각된 지적도 이유와 함께 보여드립니다.",
  },
  {
    title: "무엇을 받나",
    body: "판결문과 형량(할 일 목록)을 받습니다. 판결에 불복하면 1회 항소할 수 있습니다.",
  },
];

export function OnboardingCards() {
  const dismissed = useSyncExternalStore(
    subscribe,
    isDismissed,
    getServerSnapshot,
  );

  if (dismissed) return null;

  return (
    <div className="mb-6 rounded border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="grid flex-1 grid-cols-1 gap-4 sm:grid-cols-3">
          {CARDS.map((card) => (
            <div key={card.title}>
              <p className="mb-1 text-xs font-semibold text-accent">
                {card.title}
              </p>
              <p className="text-xs leading-relaxed text-text-muted">
                {card.body}
              </p>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="닫기"
          className="shrink-0 text-text-faint hover:text-text"
        >
          ✕
        </button>
      </div>
      <Link
        href="/rules"
        className="mt-4 inline-block text-xs font-semibold text-accent hover:underline"
      >
        법전 보기 →
      </Link>
    </div>
  );
}
