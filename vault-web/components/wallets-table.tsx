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

export function WalletsTable({ projectKey, rows }: Props) {
  return (
    <div className="bg-white border border-ink-12 rounded-[18px] p-7">
      <div className="flex items-center justify-between mb-5">
        <h2
          className="m-0 text-[26px]"
          style={{ fontFamily: "var(--font-serif)", letterSpacing: "-0.01em" }}
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
            <th
              className="text-right font-normal ink-45 text-[11.5px] uppercase tracking-[0.1em] pb-3 px-2.5 border-b border-ink-06"
            >
              잔액
            </th>
            <th
              className="text-right font-normal ink-45 text-[11.5px] uppercase tracking-[0.1em] pb-3 px-2.5 border-b border-ink-06"
            >
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
                <div
                  className="ink-45 text-[12px]"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  {shortAddr(w.address)}
                </div>
              </td>
              <td className="py-3.5 px-2.5 border-b border-ink-06 align-middle">
                <div className="flex items-center gap-2.5">
                  <span
                    className="grid place-items-center w-6 h-6 rounded-md text-[10px] font-medium"
                    style={{
                      background:
                        w.kind === "revenue"
                          ? "var(--color-accent)"
                          : "var(--color-ink)",
                      color: "var(--color-bg)",
                      fontFamily: "var(--font-mono)",
                      letterSpacing: "-0.04em",
                    }}
                  >
                    {w.kind === "revenue" ? "R" : "V"}
                  </span>
                  <span className="text-[13px]">
                    {w.kind === "revenue" ? "운영 수익" : "리워드"}
                  </span>
                </div>
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
