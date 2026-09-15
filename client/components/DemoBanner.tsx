"use client";

import { usePathname, useRouter } from "next/navigation";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE !== "false";

export function DemoBanner() {
  const pathname = usePathname();
  const router = useRouter();

  if (!DEMO_MODE || pathname === "/login") return null;

  function handleShowSample() {
    if (pathname === "/submit") {
      window.dispatchEvent(new Event("code-court:fill-sample"));
    } else {
      router.push("/submit?fillSample=1");
    }
  }

  return (
    <div className="border-b border-warning/30 bg-warning/10 px-6 py-2 text-center text-xs text-warning">
      데모 모드입니다. 준비된 샘플 코드에 대해 저장된 판결을 보여줍니다. 재판
      진행, 검증, 항소 흐름은 실제로 동작합니다.{" "}
      <button
        type="button"
        onClick={handleShowSample}
        className="ml-1 font-semibold underline underline-offset-2 hover:text-text"
      >
        샘플 코드 보기
      </button>
    </div>
  );
}
