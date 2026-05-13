"use client";

import { useMemo, useRef, useState } from "react";
import type { BalancePoint } from "@/lib/types";

const VB_W = 600;
const VB_H = 64;
const PAD = 4;

type Props = { points: BalancePoint[]; height?: number };

function fmtDate(ts: number): string {
  const d = new Date(ts);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function fmtUsd(v: number): string {
  return `$${v.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function Sparkline({ points, height = 64 }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const xyPoints = useMemo(() => {
    if (points.length < 2) return [];
    const max = Math.max(...points.map((p) => p.value));
    const min = Math.min(...points.map((p) => p.value));
    const span = max - min || 1;
    const step = (VB_W - PAD * 2) / (points.length - 1);
    return points.map((p, i) => ({
      x: PAD + i * step,
      y: VB_H - PAD - ((p.value - min) / span) * (VB_H - PAD * 2),
      ts: p.ts,
      value: p.value,
    }));
  }, [points]);

  if (xyPoints.length < 2) {
    return (
      <div
        className="w-full grid place-items-center ink-45 text-[12px]"
        style={{ height }}
      >
        데이터 부족
      </div>
    );
  }

  const linePath = xyPoints
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
    .join(" ");
  const areaPath = `${linePath} L ${xyPoints[xyPoints.length - 1].x} ${VB_H} L ${xyPoints[0].x} ${VB_H} Z`;

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const rect = wrap.getBoundingClientRect();
    const cssX = e.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, cssX / rect.width));
    const idx = Math.round(ratio * (xyPoints.length - 1));
    setHoverIdx(idx);
  }

  function onLeave() {
    setHoverIdx(null);
  }

  const hover = hoverIdx !== null ? xyPoints[hoverIdx] : null;
  // viewBox 좌표 → CSS % 비율
  const hoverXPct = hover ? (hover.x / VB_W) * 100 : 0;
  const hoverYPct = hover ? (hover.y / VB_H) * 100 : 0;

  return (
    <div
      ref={wrapRef}
      className="relative w-full"
      style={{ height }}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
    >
      <svg
        className="block w-full h-full"
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        preserveAspectRatio="none"
      >
        <path
          d={areaPath}
          fill="color-mix(in srgb, var(--color-accent) 8%, transparent)"
        />
        <path
          d={linePath}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth="1.6"
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        {/* 끝점 강조 */}
        <circle
          cx={xyPoints[xyPoints.length - 1].x}
          cy={xyPoints[xyPoints.length - 1].y}
          r="3"
          fill="var(--color-accent)"
        />
        {/* 호버 가이드라인 */}
        {hover && (
          <line
            x1={hover.x}
            y1={0}
            x2={hover.x}
            y2={VB_H}
            stroke="color-mix(in srgb, var(--color-ink) 18%, transparent)"
            strokeWidth="1"
            strokeDasharray="2 3"
            vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>

      {/* 호버 마커 (CSS overlay — preserveAspectRatio="none" 라 SVG circle 이 찌그러져서 div 로) */}
      {hover && (
        <div
          className="absolute pointer-events-none"
          style={{
            left: `calc(${hoverXPct}% - 4px)`,
            top: `calc(${hoverYPct}% - 4px)`,
            width: 8,
            height: 8,
            borderRadius: 9999,
            background: "var(--color-accent)",
            border: "2px solid var(--color-surface)",
            boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-ink) 20%, transparent)",
          }}
        />
      )}

      {/* 툴팁 */}
      {hover && (
        <div
          className="absolute pointer-events-none"
          style={{
            left: `${hoverXPct}%`,
            top: -4,
            transform: hoverXPct > 70
              ? "translate(-100%, -100%)"
              : hoverXPct < 30
                ? "translate(0, -100%)"
                : "translate(-50%, -100%)",
            background: "var(--color-ink)",
            color: "var(--color-bg)",
            padding: "6px 9px",
            borderRadius: 8,
            fontSize: 11,
            fontFamily: "var(--font-mono)",
            whiteSpace: "nowrap",
            boxShadow: "0 4px 12px color-mix(in srgb, var(--color-ink) 30%, transparent)",
          }}
        >
          <div style={{ opacity: 0.6, fontSize: 10 }}>{fmtDate(hover.ts)}</div>
          <div style={{ fontWeight: 500, marginTop: 1 }}>{fmtUsd(hover.value)}</div>
        </div>
      )}
    </div>
  );
}
