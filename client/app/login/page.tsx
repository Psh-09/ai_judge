"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, register } from "@/lib/api";
import { describeError } from "@/lib/errorMessages";
import { Banner } from "@/components/Banner";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "register") {
        await register(email, password);
      }
      await login(email, password);
      router.push("/submit");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="font-mono text-2xl font-bold tracking-tight text-text">
            CODE COURT
          </h1>
          <p className="mt-2 text-sm text-text-muted">
            검사·변호인·판사가 코드를 심리하는 대립형 코드 리뷰
          </p>
        </div>

        <div className="mb-6 flex rounded border border-border bg-surface p-1">
          <button
            type="button"
            onClick={() => setMode("login")}
            className={`flex-1 rounded py-2 text-sm font-semibold transition ${
              mode === "login"
                ? "bg-surface-raised text-text"
                : "text-text-muted"
            }`}
          >
            로그인
          </button>
          <button
            type="button"
            onClick={() => setMode("register")}
            className={`flex-1 rounded py-2 text-sm font-semibold transition ${
              mode === "register"
                ? "bg-surface-raised text-text"
                : "text-text-muted"
            }`}
          >
            회원가입
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-semibold text-text-muted">
              이메일
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded border border-border bg-surface p-3 text-sm text-text outline-none focus:border-accent"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold text-text-muted">
              비밀번호
            </label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-border bg-surface p-3 text-sm text-text outline-none focus:border-accent"
              placeholder="8자 이상"
            />
          </div>

          {error && <Banner kind="error">{error}</Banner>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded border border-accent bg-accent/10 py-3 text-sm font-semibold text-accent hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting
              ? "처리 중..."
              : mode === "login"
                ? "로그인"
                : "가입하고 시작하기"}
          </button>
        </form>
      </div>
    </div>
  );
}
