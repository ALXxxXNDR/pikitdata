"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";

export function RefreshControl() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  function refresh() {
    startTransition(() => {
      router.refresh();
    });
  }

  return (
    <span
      className="inline-flex items-center gap-2.5 pl-3 pr-1.5 py-1.5 rounded-full text-[13px] border border-ink-12"
      title={isPending ? "스캔 중…" : "실시간 동기화 (클릭으로 즉시 새로고침)"}
    >
      <span
        className={`block w-1.5 h-1.5 rounded-full ${
          isPending ? "heartbeat-pulse" : ""
        }`}
        style={{ background: "var(--color-accent)" }}
      />
      <span className="ink-60 select-none">
        {isPending ? "스캔 중…" : "실시간 동기화"}
      </span>
      <button
        type="button"
        onClick={refresh}
        disabled={isPending}
        aria-label="새로고침"
        className="grid place-items-center w-7 h-7 rounded-full hover:bg-ink-06 disabled:cursor-wait cursor-pointer"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          width="14"
          height="14"
          className={isPending ? "spin-icon" : ""}
        >
          <polyline points="23 4 23 10 17 10" />
          <polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10" />
          <path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14" />
        </svg>
      </button>
    </span>
  );
}
