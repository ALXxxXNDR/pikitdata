"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Sparkline } from "./sparkline";
import type { BalancePoint } from "@/lib/types";

type Range = "24h" | "7d" | "30d" | "3m" | "6m" | "1y" | "all";

const RANGES: { value: Range; label: string }[] = [
  { value: "24h", label: "지난 24시간" },
  { value: "7d", label: "지난 7일" },
  { value: "30d", label: "지난 30일" },
  { value: "3m", label: "지난 3개월" },
  { value: "6m", label: "지난 6개월" },
  { value: "1y", label: "지난 1년" },
  { value: "all", label: "전체" },
];

function rangeMs(r: Range): number | null {
  if (r === "all") return null;
  if (r === "24h") return 24 * 3600_000;
  if (r === "7d") return 7 * 86400_000;
  if (r === "30d") return 30 * 86400_000;
  if (r === "3m") return 90 * 86400_000;
  if (r === "6m") return 180 * 86400_000;
  return 365 * 86400_000; // 1y
}

type Props = {
  totalUsd: number;
  curve: BalancePoint[];
};

// ─────────────────────────────────────────────────────────────────
// 커스텀 드롭다운 — 테마 매칭 (pill + popover)
// ─────────────────────────────────────────────────────────────────
function RangeDropdown({
  value,
  onChange,
}: {
  value: Range;
  onChange: (r: Range) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = RANGES.find((r) => r.value === value) ?? RANGES[0];

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("click", onDoc);
    return () => document.removeEventListener("click", onDoc);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-[12px] border border-ink-12 hover:bg-ink-06 ink-60 cursor-pointer"
      >
        <span>{current.label}</span>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          width="11"
          height="11"
          className={`transition-transform ${open ? "rotate-180" : ""}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-2 bg-white border border-ink-12 rounded-[12px] p-1 z-20 min-w-[160px]"
          style={{
            boxShadow:
              "0 12px 32px -12px color-mix(in srgb, var(--color-ink) 20%, transparent)",
          }}
        >
          {RANGES.map((r) => {
            const active = r.value === value;
            return (
              <button
                key={r.value}
                type="button"
                onClick={() => {
                  onChange(r.value);
                  setOpen(false);
                }}
                className={`w-full text-left px-3 py-2 rounded-[8px] text-[12.5px] hover:bg-ink-06 flex items-center justify-between cursor-pointer ${
                  active ? "bg-ink-06" : ""
                }`}
              >
                <span>{r.label}</span>
                {active && (
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="var(--color-accent)"
                    strokeWidth="2.4"
                    width="14"
                    height="14"
                  >
                    <polyline points="5 12 10 17 19 8" />
                  </svg>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function HeroTotal({ totalUsd, curve }: Props) {
  const [range, setRange] = useState<Range>("24h");

  const filtered = useMemo<BalancePoint[]>(() => {
    const ms = rangeMs(range);
    if (ms === null) return curve;
    const cutoff = Date.now() - ms;
    const inRange = curve.filter((p) => p.ts >= cutoff);
    if (inRange.length === 0 || inRange[0].ts > cutoff) {
      const idxFirstInRange = curve.findIndex((p) => p.ts >= cutoff);
      const priorValue =
        idxFirstInRange > 0
          ? curve[idxFirstInRange - 1].value
          : (inRange[0]?.value ?? totalUsd);
      return [{ ts: cutoff, value: priorValue }, ...inRange];
    }
    return inRange;
  }, [range, curve, totalUsd]);

  const first = filtered[0]?.value ?? totalUsd;
  const last = filtered[filtered.length - 1]?.value ?? totalUsd;
  const deltaAbs = last - first;
  const deltaPct = first > 0 ? (deltaAbs / first) * 100 : 0;
  const up = deltaAbs >= 0;
  const intPart = "$" + Math.floor(totalUsd).toLocaleString("en-US");
  const decPart = "." + totalUsd.toFixed(2).split(".")[1];

  const rangeSuffix = RANGES.find((r) => r.value === range)?.label.replace(
    "지난 ",
    "",
  );

  return (
    <div className="bg-white border border-ink-12 rounded-[18px] p-7 flex flex-col justify-between min-h-[260px]">
      <div className="flex justify-between items-start">
        <div className="text-[12px] ink-45 uppercase tracking-[0.12em]">
          총 자산 (USD)
        </div>
        <RangeDropdown value={range} onChange={setRange} />
      </div>
      <div>
        <div
          className="my-4"
          style={{
            fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`,
            fontSize: "88px",
            lineHeight: 1,
            letterSpacing: "-0.03em",
          }}
        >
          <span>{intPart}</span>
          <span className="ink-45 text-[46px]">{decPart}</span>
        </div>
        <div className="inline-flex items-center gap-2.5 text-[14px]">
          <span
            className="px-2.5 py-0.5 rounded-full text-[12px] font-medium"
            style={{
              background: up ? "var(--color-accent)" : "var(--color-ink)",
              color: "var(--color-bg)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {up ? "+" : ""}
            {deltaPct.toFixed(2)}%
          </span>
          <span className="ink-60" style={{ fontFamily: "var(--font-mono)" }}>
            {up ? "+ " : "– "}$
            {Math.abs(deltaAbs).toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}{" "}
            · {rangeSuffix}
          </span>
        </div>
      </div>
      <div className="mt-4">
        <Sparkline points={filtered} />
      </div>
    </div>
  );
}
