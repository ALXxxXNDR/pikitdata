import Link from "next/link";
import type { ProjectConfig, WalletSnapshot } from "@/lib/types";

type Row = {
  wallet: ProjectConfig["wallets"][number];
  snapshot: WalletSnapshot | null;
};

type Props = {
  projectKey: string;
  rows: Row[];
};

function shortAddr(a: string): string {
  if (!a) return "—";
  if (a.length < 12) return a;
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}

// 유형 배지 — 텍스트 자체에 배경색을 칠하고 텍스트는 흰색.
function KindBadge({ kind }: { kind: "revenue" | "reward" }) {
  const isRevenue = kind === "revenue";
  return (
    <span
      className="inline-flex items-center px-2.5 py-1 rounded-md text-[12px] font-medium"
      style={{
        background: isRevenue ? "var(--color-accent)" : "var(--color-ink)",
        color: "var(--color-surface)",
        letterSpacing: "-0.005em",
      }}
    >
      {isRevenue ? "운영 수익" : "리워드"}
    </span>
  );
}

export function WalletsTable({ projectKey, rows }: Props) {
  return (
    <div className="bg-white border border-ink-12 rounded-[18px] p-7">
      <div className="flex items-center justify-between mb-5">
        <h2
          className="m-0 text-[26px]"
          style={{ fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`, letterSpacing: "-0.01em" }}
        >
          지갑
        </h2>
        <div
          className="flex gap-1 p-0.5 rounded-full bg-ink-06 text-[12px]"
        >
          <button
            className="px-3 py-1 rounded-full bg-white"
            style={{
              boxShadow:
                "0 1px 2px color-mix(in srgb, var(--color-ink) 10%, transparent)",
            }}
          >
            전체
          </button>
          <button className="px-3 py-1 rounded-full ink-60">수익</button>
          <button className="px-3 py-1 rounded-full ink-60">리워드</button>
        </div>
      </div>
      <table className="w-full border-collapse text-[13.5px]">
        <thead>
          <tr>
            <th className="text-left font-normal ink-45 text-[11.5px] uppercase tracking-[0.1em] pb-3 px-2.5 border-b border-ink-06">
              라벨 / 주소
            </th>
            <th className="text-left font-normal ink-45 text-[11.5px] uppercase tracking-[0.1em] pb-3 px-2.5 border-b border-ink-06">
              유형
            </th>
            <th className="text-right font-normal ink-45 text-[11.5px] uppercase tracking-[0.1em] pb-3 px-2.5 border-b border-ink-06">
              잔액
            </th>
            <th className="text-right font-normal ink-45 text-[11.5px] uppercase tracking-[0.1em] pb-3 px-2.5 border-b border-ink-06">
              상세
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} className="py-8 text-center ink-45 text-[13px]">
                등록된 지갑이 없습니다
              </td>
            </tr>
          )}
          {rows.map(({ wallet: w, snapshot: s }) => (
            <tr key={w.key}>
              <td className="py-3.5 px-2.5 border-b border-ink-06 align-middle">
                <div className="font-medium">{w.name}</div>
                {w.address ? (
                  <a
                    href={`https://soneium.blockscout.com/address/${w.address}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ink-45 hover:text-ink hover:underline underline-offset-2 inline-flex items-center gap-1"
                    style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}
                    title="Blockscout 에서 열기"
                  >
                    {shortAddr(w.address)}
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      width="10"
                      height="10"
                    >
                      <path d="M7 17 17 7" />
                      <path d="M7 7h10v10" />
                    </svg>
                  </a>
                ) : (
                  <div
                    className="ink-45"
                    style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}
                  >
                    —
                  </div>
                )}
              </td>
              <td className="py-3.5 px-2.5 border-b border-ink-06 align-middle">
                <KindBadge kind={w.kind} />
              </td>
              <td
                className="py-3.5 px-2.5 border-b border-ink-06 align-middle text-right"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {s ? (
                  <>
                    ${s.totalUsd.toLocaleString("en-US", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                    <div className="ink-45 text-[11.5px] mt-0.5">
                      {s.tokens[0]?.symbol ?? "USDSC"}
                    </div>
                  </>
                ) : (
                  <span className="ink-45">—</span>
                )}
              </td>
              <td className="py-3.5 px-2.5 border-b border-ink-06 align-middle text-right">
                {w.address ? (
                  <Link
                    href={`/?project=${projectKey}&wallet=${w.key}`}
                    className="inline-flex items-center gap-1 text-[12px] px-3 py-1 rounded-full border border-ink-12 hover:bg-ink-06"
                  >
                    보기 →
                  </Link>
                ) : (
                  <span className="text-[12px] ink-45">주소 미설정</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
