import type { Allocation } from "@/lib/soneium";

function shade(i: number): string {
  // 3색 팔레트 (디자인 토큰) 안에서 ink 의 톤 변형으로 4분할.
  const shades = [
    "var(--color-ink)",
    "color-mix(in srgb, var(--color-ink) 55%, var(--color-bg))",
    "color-mix(in srgb, var(--color-ink) 30%, var(--color-bg))",
    "var(--color-accent)",
  ];
  return shades[i % shades.length];
}

type Props = { items: Allocation[] };

export function AllocationCard({ items }: Props) {
  return (
    <div className="bg-white border border-ink-12 rounded-[18px] p-7">
      <h3 className="m-0 mb-4 text-[12px] ink-45 uppercase tracking-[0.12em] font-medium">
        자산 분포
      </h3>
      {items.length === 0 ? (
        <div className="ink-45 text-[13px] py-8 text-center">데이터 없음</div>
      ) : (
        <>
          <div className="flex h-2 rounded-full overflow-hidden bg-ink-06">
            {items.map((c, i) => (
              <span
                key={c.name + i}
                className="block h-full"
                style={{ width: `${c.pct}%`, background: shade(i) }}
              />
            ))}
          </div>
          <div className="mt-4 flex flex-col gap-3">
            {items.map((c, i) => (
              <div
                key={c.name + i}
                className="grid items-center gap-3 text-[13px]"
                style={{ gridTemplateColumns: "14px 1fr auto auto" }}
              >
                <span
                  className="w-2 h-2 rounded-full block"
                  style={{ background: shade(i) }}
                />
                <span>{c.name}</span>
                <span
                  className="ink-45 min-w-[48px] text-right"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  {c.pct.toFixed(1)}%
                </span>
                <span
                  className="min-w-[96px] text-right"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  ${c.usd.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
