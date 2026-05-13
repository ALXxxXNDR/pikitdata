"use client";

import { useMemo, useState } from "react";
import { Sparkline } from "./sparkline";
import type { BalancePoint } from "@/lib/types";

type Range = "24h" | "7d" | "30d" | "all";

const RANGES: { value: Range; label: string }[] = [
  { value: "24h", label: "지난 24시간" },
  { value: "7d", label: "지난 7일" },
  { value: "30d", label: "지난 30일" },
  { value: "all", label: "전체" },
];

function rangeMs(r: Range): number | null {
  if (r === "all") return null;
  if (r === "24h") return 24 * 3600_000;
  if (r === "7d") return 7 * 86400_000;
  return 30 * 86400_000;
}

type Props = {
  totalUsd: number;
  curve: BalancePoint[];
};

export function HeroTotal({ totalUsd, curve }: Props) {
  const [range, setRange] = useState<Range>("24h");

  const filtered = useMemo<BalancePoint[]>(() => {
    const ms = rangeMs(range);
    if (ms === null) return curve;
    const cutoff = Date.now() - ms;
    const inRange = curve.filter((p) => p.ts >= cutoff);
    // 첫 시점이 cutoff 보다 뒤라면 (= 그 사이 거래 없음) cutoff 기준 시작점도 채워
    // 평탄한 선이 나오게.
    if (inRange.length === 0 || inRange[0].ts > cutoff) {
      // cutoff 시점 직전의 마지막 잔고 = inRange 직전 포인트의 value
      const idxFirstInRange = curve.findIndex((p) => p.ts >= cutoff);
      const priorValue =
        idxFirstInRange > 0
          ? curve[idxFirstInRange - 1].value
          : (inRange[0]?.value ?? totalUsd);
      return [{ ts: cutoff, value: priorValue }, ...inRange];
    }
    return inRange;
  }, [range, curve, totalUsd]);

  // 델타 = 끝 - 시작 (filtered 기준)
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
        <select
          className="range-select bg-transparent border border-ink-12 rounded-full px-3 py-1.5 text-[12px] ink-60 cursor-pointer"
          value={range}
          onChange={(e) => setRange(e.target.value as Range)}
        >
          {RANGES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
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
