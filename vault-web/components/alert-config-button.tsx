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

export function AlertConfigButton({
  projectKey,
  walletKey,
  walletName,
  initial,
  kvConfigured,
}: Props) {
  const [open, setOpen] = useState(false);
  // 버튼 인디케이터용 — 저장 성공 시 갱신
  const [savedConfig, setSavedConfig] = useState<AlertConfig>(initial);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 pl-2.5 pr-3.5 py-1.5 rounded-full text-[12.5px] border border-ink-12 hover:bg-ink-06 ink-60 cursor-pointer"
        title={
          savedConfig.enabled
            ? `잔고가 $${savedConfig.threshold.toLocaleString("en-US")} ${
                savedConfig.direction === "below" ? "이하" : "이상"
              }일 때 알림 ON`
            : "알림 OFF — 클릭해서 설정"
        }
      >
        <span
          className="block w-1.5 h-1.5 rounded-full"
          style={{
            background: savedConfig.enabled
              ? "var(--color-accent)"
              : "color-mix(in srgb, var(--color-ink) 25%, transparent)",
          }}
        />
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          width="13"
          height="13"
        >
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        <span>알림 설정</span>
      </button>

      {open && (
        <AlertModal
          projectKey={projectKey}
          walletKey={walletKey}
          walletName={walletName}
          initial={savedConfig}
          kvConfigured={kvConfigured}
          onClose={() => setOpen(false)}
          onSaved={(c) => setSavedConfig(c)}
        />
      )}
    </>
  );
}

function AlertModal({
  projectKey,
  walletKey,
  walletName,
  initial,
  kvConfigured,
  onClose,
  onSaved,
}: Props & {
  onClose: () => void;
  onSaved: (c: AlertConfig) => void;
}) {
  const [enabled, setEnabled] = useState(initial.enabled);
  const [threshold, setThreshold] = useState(String(initial.threshold));
  const [direction, setDirection] = useState<AlertDirection>(initial.direction);
  const [dirOpen, setDirOpen] = useState(false);
  const dirRef = useRef<HTMLDivElement>(null);
  const [isPending, startTransition] = useTransition();
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const initialKeyRef = useRef(JSON.stringify(initial));
  const currentKey = JSON.stringify({
    enabled,
    threshold: Number(threshold) || 0,
    direction,
  });
  const dirty = currentKey !== initialKeyRef.current;

  // ESC 로 닫기 + body scroll lock
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

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
        const saved: AlertConfig = { enabled, threshold: t, direction };
        onSaved(saved);
        initialKeyRef.current = currentKey;
        setMsg({ kind: "ok", text: "저장됨" });
        setTimeout(() => onClose(), 700);
      } else {
        setMsg({ kind: "err", text: res.error ?? "저장 실패" });
      }
    });
  }

  const currentDir = DIRECTIONS.find((d) => d.value === direction) ?? DIRECTIONS[0];

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center px-4"
      style={{
        background: "color-mix(in srgb, var(--color-ink) 50%, transparent)",
      }}
      onClick={onClose}
    >
      <div
        className="bg-white border border-ink-12 rounded-[18px] p-7 w-full max-w-[460px]"
        style={{
          boxShadow:
            "0 24px 60px -16px color-mix(in srgb, var(--color-ink) 35%, transparent)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 mb-1">
          <div>
            <div className="text-[12px] ink-45 uppercase tracking-[0.12em]">
              이메일 알림
            </div>
            <div className="text-[16px] font-medium mt-1">{walletName}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="grid place-items-center w-8 h-8 rounded-full hover:bg-ink-06 ink-45 cursor-pointer"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              width="14"
              height="14"
            >
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>
        <p className="ink-60 text-[13px] mt-3 leading-relaxed">
          잔고가 조건을 만족하면 매일 09:00 (UTC) 요약 메일에 포함됩니다.
        </p>

        <div className="flex items-center justify-between mt-5">
          <span className="text-[14px] font-medium">알림 사용</span>
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            onClick={() => setEnabled((v) => !v)}
            className="relative inline-flex items-center w-[44px] h-[24px] rounded-full transition-colors cursor-pointer"
            style={{
              background: enabled
                ? "var(--color-accent)"
                : "color-mix(in srgb, var(--color-ink) 18%, transparent)",
            }}
          >
            <span
              className="block w-[18px] h-[18px] rounded-full bg-white transition-transform"
              style={{
                transform: enabled ? "translateX(23px)" : "translateX(3px)",
                boxShadow: "0 1px 2px rgba(0,0,0,0.2)",
              }}
            />
          </button>
        </div>

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
              className="bg-transparent border border-ink-12 rounded-[10px] pl-7 pr-3 py-1.5 text-[14px] ink focus:outline-none focus:border-ink-25 w-[140px]"
              style={{ fontFamily: "var(--font-mono)" }}
            />
          </div>
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
          <span className="ink-60">알림</span>
        </div>

        {!kvConfigured && (
          <div
            className="mt-5 text-[12px] px-3 py-2 rounded-[10px]"
            style={{
              background: "color-mix(in srgb, var(--color-ink) 4%, transparent)",
              border:
                "1px solid color-mix(in srgb, var(--color-ink) 12%, transparent)",
              color: "color-mix(in srgb, var(--color-ink) 70%, transparent)",
            }}
          >
            저장소(Edge Config) 가 아직 연결되지 않았습니다 — 현재 변경분은
            저장되지 않습니다.
          </div>
        )}

        <div className="mt-6 flex items-center justify-end gap-3">
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
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center px-4 py-1.5 rounded-full text-[13px] border border-ink-12 hover:bg-ink-06 ink-60 cursor-pointer"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={!dirty || isPending}
            className="inline-flex items-center px-4 py-1.5 rounded-full text-[13px] font-medium cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              background: "var(--color-ink)",
              color: "var(--color-bg)",
            }}
          >
            {isPending ? "저장 중…" : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
