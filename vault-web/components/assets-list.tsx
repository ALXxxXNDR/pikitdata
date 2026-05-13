import type { Allocation } from "@/lib/soneium";
import type { TokenHolding } from "@/lib/types";

type Item = {
  symbol: string;
  name: string;
  amount: number;
  usd: number;
  share: number; // 0~100
};

type Props = {
  items: Item[];
  allocation?: Allocation[];
};

// 3색 팔레트 안에서 ink 톤 변형 4분할 (자산 분포 막대 + 점)
function shade(i: number): string {
  const shades = [
    "var(--color-ink)",
    "color-mix(in srgb, var(--color-ink) 55%, var(--color-bg))",
    "color-mix(in srgb, var(--color-ink) 30%, var(--color-bg))",
    "var(--color-accent)",
  ];
  return shades[i % shades.length];
}

function AllocationSection({ items }: { items: Allocation[] }) {
  if (items.length === 0) return null;
  return (
    <div className="mb-6">
      <div className="text-[12px] ink-45 uppercase tracking-[0.12em] mb-3">
        자산 분포
      </div>
      <div className="flex h-2 rounded-full overflow-hidden bg-ink-06">
        {items.map((c, i) => (
          <span
            key={c.name + i}
            className="block h-full"
            style={{ width: `${c.pct}%`, background: shade(i) }}
          />
        ))}
      </div>
      <div className="mt-3 flex flex-col gap-2">
        {items.map((c, i) => (
          <div
            key={c.name + i}
            className="grid items-center gap-3 text-[12.5px]"
            style={{ gridTemplateColumns: "10px 1fr auto auto" }}
          >
            <span
              className="w-2 h-2 rounded-full block"
              style={{ background: shade(i) }}
            />
            <span>{c.name}</span>
            <span
              className="ink-45 min-w-[40px] text-right"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              {c.pct.toFixed(1)}%
            </span>
            <span
              className="min-w-[88px] text-right"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              $
              {c.usd.toLocaleString("en-US", {
                maximumFractionDigits: 2,
              })}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function AssetsList({ items, allocation }: Props) {
  return (
    <div className="bg-white border border-ink-12 rounded-[18px] p-7">
      <div className="flex items-center justify-between mb-5">
        <h2
          className="m-0 text-[26px]"
          style={{
            fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`,
            letterSpacing: "-0.01em",
          }}
        >
          보유 자산
        </h2>
      </div>

      {allocation && allocation.length > 0 && (
        <>
          <AllocationSection items={allocation} />
          <div className="h-px bg-ink-06 -mx-1 mb-5" />
        </>
      )}

      <div className="text-[12px] ink-45 uppercase tracking-[0.12em] mb-2">
        보유 현황
      </div>
      <div className="flex flex-col">
        {items.length === 0 && (
          <div className="text-center ink-45 text-[13px] py-8">자산 없음</div>
        )}
        {items.map((a, i) => (
          <div
            key={a.symbol + i}
            className="grid items-center gap-3.5 py-3 px-1 border-b border-ink-06 last:border-b-0"
            style={{ gridTemplateColumns: "32px 1fr auto" }}
          >
            <div
              className="grid place-items-center w-8 h-8 rounded-full bg-ink-06 text-[11px]"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              {a.symbol.slice(0, 4)}
            </div>
            <div>
              <div className="text-[14px] font-medium">{a.name || a.symbol}</div>
              <div
                className="text-[12px] ink-45 mt-0.5"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {a.amount > 0
                  ? `${a.amount.toLocaleString("en-US", { maximumFractionDigits: 4 })} ${a.symbol}`
                  : "—"}
              </div>
            </div>
            <div className="text-right">
              <div
                className="text-[13.5px]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                $
                {a.usd.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </div>
              <div className="text-[11.5px] ink-45 mt-0.5">
                {a.share.toFixed(1)}%
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function holdingsToItems(
  tokens: TokenHolding[],
  ethUsd: number,
  ethAmt: number,
): Item[] {
  const items: Item[] = [];
  const total = tokens.reduce((s, t) => s + t.usd, 0) + ethUsd;
  if (ethAmt > 0) {
    items.push({
      symbol: "ETH",
      name: "Ethereum",
      amount: ethAmt,
      usd: ethUsd,
      share: total > 0 ? (ethUsd / total) * 100 : 0,
    });
  }
  for (const t of tokens) {
    items.push({
      symbol: t.symbol,
      name: t.name || t.symbol,
      amount: t.value,
      usd: t.usd,
      share: total > 0 ? (t.usd / total) * 100 : 0,
    });
  }
  return items.sort((a, b) => b.usd - a.usd);
}
