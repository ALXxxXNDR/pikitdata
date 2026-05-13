"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { saveAlertConfigAction } from "@/app/actions/alert-config";
import type { AlertConfig, AlertDirection } from "@/lib/alert-config";

type Props = {
  projectKey: string;
  walletKey: string;
  walletName: string;
  initial: AlertConfig;
  kvConfigured: boolean;
};

const DIRECTIONS: { value: AlertDirection; label: string }[] = [
  { value: "below", label: "이하일 때" },
  { value: "above", label: "이상일 때" },
];

export function AlertConfigCard({
  projectKey,
  walletKey,
  walletName,
  initial,
  kvConfigured,
}: Props) {
  const [enabled, setEnabled] = useState(initial.enabled);
  const [threshold, setThreshold] = useState(String(initial.threshold));
  const [direction, setDirection] = useState<AlertDirection>(initial.direction);
  const [dirOpen, setDirOpen] = useState(false);
  const dirRef = useRef<HTMLDivElement>(null);
  const [isPending, startTransition] = useTransition();
  const [msg, setMsg] = useState<{
    kind: "ok" | "err";
    text: string;
  } | null>(null);

  // dirty 추적 — 변경이 있을 때만 저장 가능
  const initialKeyRef = useRef(JSON.stringify(initial));
  const currentKey = JSON.stringify({
    enabled,
    threshold: Number(threshold) || 0,
    direction,
  });
  const dirty = currentKey !== initialKeyRef.current;

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!dirRef.current?.contains(e.target as Node)) setDirOpen(false);
    }
    document.addEventListener("click", onDoc);
    return () => document.removeEventListener("click", onDoc);
  }, []);

  function onSave() {
    const t = Number(threshold);
    if (!Number.isFinite(t) || t < 0) {
      setMsg({ kind: "err", text: "유효한 금액을 입력하세요" });
      return;
    }
    setMsg(null);
    startTransition(async () => {
      const res = await saveAlertConfigAction(
        projectKey,
        walletKey,
        enabled,
        t,
        direction,
      );
      if (res.ok) {
        initialKeyRef.current = currentKey;
        setMsg({ kind: "ok", text: "저장됨" });
        setTimeout(() => setMsg(null), 2500);
      } else {
        setMsg({ kind: "err", text: res.error ?? "저장 실패" });
      }
    });
  }

  const currentDir = DIRECTIONS.find((d) => d.value === direction) ?? DIRECTIONS[0];

  return (
    <div className="bg-white border border-ink-12 rounded-[18px] p-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex flex-col gap-1">
          <div className="text-[12px] ink-45 uppercase tracking-[0.12em]">
            이메일 알림
          </div>
          <div className="text-[13.5px] ink-60">
            {walletName} 잔고 조건이 충족되면 매일 1회 요약 메일
          </div>
        </div>
        {/* On/Off 토글 */}
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={() => setEnabled((v) => !v)}
          className="relative inline-flex items-center w-[42px] h-[24px] rounded-full transition-colors cursor-pointer"
          style={{
            background: enabled
              ? "var(--color-accent)"
              : "color-mix(in srgb, var(--color-ink) 18%, transparent)",
          }}
        >
          <span
            className="block w-[18px] h-[18px] rounded-full bg-white transition-transform"
            style={{
              transform: enabled ? "translateX(21px)" : "translateX(3px)",
              boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
            }}
          />
        </button>
      </div>

      {/* 조건 입력 */}
      <div
        className={`mt-5 flex items-center gap-2 flex-wrap text-[13.5px] ${
          enabled ? "" : "opacity-50 pointer-events-none"
        }`}
      >
        <span className="ink-60">잔고가</span>
        <div className="relative">
          <span
            className="absolute left-3 top-1/2 -translate-y-1/2 ink-45 text-[13px] pointer-events-none"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            $
          </span>
          <input
            type="number"
            min="0"
            step="any"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            className="bg-transparent border border-ink-12 rounded-[10px] pl-7 pr-3 py-1.5 text-[14px] ink focus:outline-none focus:border-ink-25 w-[120px]"
            style={{ fontFamily: "var(--font-mono)" }}
          />
        </div>
        {/* 방향 드롭다운 */}
        <div className="relative" ref={dirRef}>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setDirOpen((v) => !v);
            }}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-[10px] border border-ink-12 hover:bg-ink-06 ink-60 text-[13.5px] cursor-pointer"
          >
            <span>{currentDir.label}</span>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              width="11"
              height="11"
              className={`transition-transform ${dirOpen ? "rotate-180" : ""}`}
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          {dirOpen && (
            <div
              className="absolute left-0 top-full mt-2 bg-white border border-ink-12 rounded-[10px] p-1 z-20 min-w-[140px]"
              style={{
                boxShadow:
                  "0 12px 32px -12px color-mix(in srgb, var(--color-ink) 20%, transparent)",
              }}
            >
              {DIRECTIONS.map((d) => {
                const active = d.value === direction;
                return (
                  <button
                    key={d.value}
                    type="button"
                    onClick={() => {
                      setDirection(d.value);
                      setDirOpen(false);
                    }}
                    className={`w-full text-left px-3 py-2 rounded-[8px] text-[13px] hover:bg-ink-06 cursor-pointer ${
                      active ? "bg-ink-06" : ""
                    }`}
                  >
                    {d.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <span className="ink-60">알림 받기</span>
      </div>

      {/* 저장 + 상태 */}
      <div className="mt-5 flex items-center gap-3">
        <button
          type="button"
          onClick={onSave}
          disabled={!dirty || isPending}
          className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-[13px] font-medium cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          style={{
            background: "var(--color-ink)",
            color: "var(--color-bg)",
          }}
        >
          {isPending ? "저장 중…" : "저장"}
        </button>
        {msg && (
          <span
            className="text-[12.5px]"
            style={{
              color:
                msg.kind === "ok"
                  ? "var(--color-accent)"
                  : "color-mix(in srgb, var(--color-ink) 70%, transparent)",
            }}
          >
            {msg.text}
          </span>
        )}
        {!kvConfigured && !msg && (
          <span className="text-[11.5px] ink-45">
            KV 미연결 — 현재 변경분은 저장되지 않습니다
          </span>
        )}
      </div>
    </div>
  );
}
