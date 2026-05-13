import { Sparkline } from "./sparkline";

type Props = {
  totalUsd: number;
  deltaPct: number;
  deltaAbs: number;
  spark: number[];
};

export function HeroTotal({ totalUsd, deltaPct, deltaAbs, spark }: Props) {
  const intPart = "$" + Math.floor(totalUsd).toLocaleString("en-US");
  const decPart = "." + totalUsd.toFixed(2).split(".")[1];
  const up = deltaPct >= 0;
  return (
    <div className="bg-white border border-ink-12 rounded-[18px] p-7 flex flex-col justify-between min-h-[240px]">
      <div className="flex justify-between items-start">
        <div className="text-[12px] ink-45 uppercase tracking-[0.12em]">총 자산 (USD)</div>
        <select className="range-select bg-transparent border border-ink-12 rounded-full px-3 py-1.5 text-[12px] ink-60 cursor-pointer">
          <option>지난 24시간</option>
          <option>지난 7일</option>
          <option>지난 30일</option>
          <option>전체</option>
        </select>
      </div>
      <div>
        <div
          className="my-4"
          style={{
            fontFamily: "var(--font-serif)",
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
            · 24h
          </span>
        </div>
      </div>
      <div className="mt-4">
        <Sparkline points={spark} />
      </div>
    </div>
  );
}
