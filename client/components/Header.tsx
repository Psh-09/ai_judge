"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout } from "@/lib/api";

export function Header() {
  const pathname = usePathname();
  const router = useRouter();

  if (pathname === "/login") return null;

  async function handleLogout() {
    try {
      await logout();
    } finally {
      router.push("/login");
    }
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
        <Link
          href="/submit"
          className="font-mono text-sm font-bold tracking-tight text-text"
        >
          CODE COURT
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          <Link
            href="/submit"
            className="rounded px-3 py-1.5 text-text-muted hover:bg-surface-raised hover:text-text"
          >
            새 재판
          </Link>
          <Link
            href="/cases"
            className="rounded px-3 py-1.5 text-text-muted hover:bg-surface-raised hover:text-text"
          >
            전과 기록
          </Link>
          <Link
            href="/rules"
            className="rounded px-3 py-1.5 text-text-muted hover:bg-surface-raised hover:text-text"
          >
            법전
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded px-3 py-1.5 text-text-muted hover:bg-surface-raised hover:text-text"
          >
            로그아웃
          </button>
        </nav>
      </div>
    </header>
  );
}
