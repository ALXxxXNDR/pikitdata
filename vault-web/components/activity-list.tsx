"use client";

import { useEffect, useMemo, useState } from "react";
import { Pagination } from "./pagination";
import { isTxHash } from "@/lib/format";
import type { Transfer } from "@/lib/types";

type Props = {
  items: Transfer[];
  pageSize?: number;
};

type Filter = "all" | "in" | "out";

function timeAgo(iso: string): string {
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "—";
  const sec = Math.max(0, (Date.now() - t) / 1000);
  if (sec < 60) return `${Math.floor(sec)}초 전`;
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}시간 전`;
  if (sec < 86400 * 7) return `${Math.floor(sec / 86400)}일 전`;
  return new Date(iso).toISOString().slice(0, 10);
}

function shortAddr(a: string): string {
  if (!a) return "";
  if (a.length < 12) return a;
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}

export function ActivityList({ items, pageSize = 10 }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [page, setPage] = useState(0);
  const filtered = useMemo(() => {
    if (filter === "all") return items;
    return items.filter((r) => r.direction === filter);
  }, [items, filter]);

  // 필터 바뀌면 첫 페이지로
  useEffect(() => {
    setPage(0);
  }, [filter]);

  const start = page * pageSize;
  const rows = filtered.slice(start, start + pageSize);

  const tabs: { value: Filter; label: string }[] = [
    { value: "all", label: "전체" },
    { value: "in", label: "입금" },
    { value: "out", label: "출금" },
  ];

  return (
    <div className="bg-white border border-ink-12 rounded-[18px] p-7 mt-6">
      <div className="flex items-center justify-between mb-5">
        <h2
          className="m-0 text-[26px]"
          style={{ fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`, letterSpacing: "-0.01em" }}
        >
          최근 활동
        </h2>
        <div className="flex gap-1 p-0.5 rounded-full bg-ink-06 text-[12px]">
          {tabs.map((t) => {
            const active = t.value === filter;
            return (
              <button
                key={t.value}
                onClick={() => setFilter(t.value)}
                className={`px-3 py-1 rounded-full ${
                  active ? "bg-white" : "ink-60"
                }`}
                style={
                  active
                    ? {
                        boxShadow:
                          "0 1px 2px color-mix(in srgb, var(--color-ink) 10%, transparent)",
                      }
                    : undefined
                }
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex flex-col">
        {rows.length === 0 && (
          <div className="text-center ink-45 text-[13px] py-8">
            {filter === "all" ? "활동 없음" : `${filter === "in" ? "입금" : "출금"} 없음`}
          </div>
        )}
        {rows.map((r, i) => {
          const isIn = r.direction === "in";
          // 업스트림 (Blockscout) 가 잘못된 hash 를 돌려줘도 javascript: URL 등 주입 차단.
          const txUrl = isTxHash(r.hash)
            ? `https://soneium.blockscout.com/tx/${r.hash}`
            : null;
          return (
            <div
              key={r.hash + i}
              className="grid items-center gap-4 py-3.5 border-b border-ink-06 last:border-b-0"
              style={{ gridTemplateColumns: "36px 1.4fr 1fr auto auto" }}
            >
              <div
                className="grid place-items-center w-9 h-9 rounded-full border border-ink-12"
                style={{
                  color: isIn ? "var(--color-accent)" : "var(--color-ink)",
                  opacity: isIn ? 1 : 0.6,
                }}
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  className="w-4 h-4"
                >
                  {isIn ? (
                    <>
                      <path d="M12 5v14" />
                      <polyline points="6 13 12 19 18 13" />
                    </>
                  ) : (
                    <>
                      <path d="M12 19V5" />
                      <polyline points="6 11 12 5 18 11" />
                    </>
                  )}
                </svg>
              </div>
              <div>
                <div className="text-[13.5px] font-medium">
                  {isIn ? "입금" : "출금"}
                </div>
                <div
                  className="text-[12px] ink-45 mt-0.5"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  {r.symbol}
                </div>
              </div>
              <div className="text-[12.5px]">
                {txUrl ? (
                  <a
                    href={txUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ink-60 hover:text-ink hover:underline underline-offset-2 inline-flex items-center gap-1"
                    style={{ fontFamily: "var(--font-mono)" }}
                    title="이 거래의 트랜잭션 페이지 (Blockscout)"
                  >
                    {shortAddr(r.counterparty)}
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
                  <span
                    className="ink-60"
                    style={{ fontFamily: "var(--font-mono)" }}
                  >
                    {shortAddr(r.counterparty)}
                  </span>
                )}
              </div>
              <div
                className="text-right"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                <div
                  className="text-[13.5px]"
                  style={{ color: isIn ? "var(--color-accent)" : undefined }}
                >
                  {isIn ? "+ " : "– "}
                  {r.value.toLocaleString("en-US", { maximumFractionDigits: 4 })}{" "}
                  {r.symbol}
                </div>
                <div className="ink-45 text-[11.5px] mt-0.5">
                  {r.usd !== null
                    ? `${isIn ? "+ " : "– "}$${r.usd.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                    : "—"}
                </div>
              </div>
              <div
                className="text-[12px] ink-45 text-right min-w-[64px]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {timeAgo(r.timestamp)}
              </div>
            </div>
          );
        })}
      </div>
      <Pagination
        page={page}
        pageSize={pageSize}
        total={filtered.length}
        onChange={setPage}
      />
    </div>
  );
}
