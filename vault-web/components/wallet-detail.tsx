"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ActivityList } from "./activity-list";
import { AlertConfigButton } from "./alert-config-button";
import { Pagination } from "./pagination";
import { isEvmAddress } from "@/lib/format";
import type { AlertConfig } from "@/lib/alert-config";
import type {
  ProjectConfig,
  Transfer,
  WalletConfig,
  WalletSnapshot,
} from "@/lib/types";

type Props = {
  project: ProjectConfig;
  wallet: WalletConfig;
  snapshot: WalletSnapshot | null;
  history: Transfer[];
  alertConfig: AlertConfig;
  kvConfigured: boolean;
};

export function WalletDetail({
  project,
  wallet,
  snapshot,
  history,
  alertConfig,
  kvConfigured,
}: Props) {
  const totalIn = history
    .filter((t) => t.direction === "in")
    .reduce((s, t) => s + (t.usd ?? 0), 0);
  const totalOut = history
    .filter((t) => t.direction === "out")
    .reduce((s, t) => s + (t.usd ?? 0), 0);
  const isTreasury = wallet.pnlMode === "treasury";
  const pnl = isTreasury ? -totalOut : totalIn - totalOut;
  const inLabel = isTreasury ? "총 충전" : "총 입금";
  const outLabel = isTreasury ? "총 지급" : "총 출금";
  const pnlLabel = isTreasury ? "손익 (Owner PNL)" : "순 PNL";

  return (
    <>
      <div className="mt-3 flex items-center gap-3 flex-wrap">
        <Link
          href={`/?project=${project.key}`}
          className="inline-flex items-center gap-1.5 text-[13px] px-3 py-1.5 rounded-full border border-ink-12 hover:bg-ink-06"
        >
          ← 프로젝트
        </Link>
        <div
          className="text-[13px] ink-60 flex-1 min-w-0 truncate"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          {wallet.address}
        </div>
        <AlertConfigButton
          projectKey={project.key}
          walletKey={wallet.key}
          walletName={wallet.name}
          initial={alertConfig}
          kvConfigured={kvConfigured}
        />
      </div>

      <h2
        className="mt-4 text-[40px]"
        style={{ fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`, letterSpacing: "-0.02em" }}
      >
        {wallet.name}
      </h2>
      <p className="ink-60 text-[14px] mt-1">{wallet.description}</p>

      <section
        className="grid gap-6 mt-6"
        style={{ gridTemplateColumns: "repeat(4, 1fr)" }}
      >
        <Metric
          label="총 USD"
          value={`$${(snapshot?.totalUsd ?? 0).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}`}
        />
        <Metric label={inLabel} value={fmtUsd(totalIn)} sub={`${countDir(history, "in")}건`} />
        <Metric label={outLabel} value={fmtUsd(totalOut)} sub={`${countDir(history, "out")}건`} />
        <Metric label={pnlLabel} value={fmtUsd(pnl)} accent={pnl > 0} />
      </section>

      <section className="mt-6 grid gap-6" style={{ gridTemplateColumns: "1.4fr 1fr" }}>
        <CounterpartySection history={history} pnlMode={wallet.pnlMode} />
        <TokensSection snapshot={snapshot} />
      </section>

      <ActivityList items={history} />
    </>
  );
}

function Metric({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className="bg-white border border-ink-12 rounded-[18px] p-6">
      <div className="text-[12px] ink-45 uppercase tracking-[0.12em]">{label}</div>
      <div
        className="text-[32px] mt-3"
        style={{
          fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`,
          letterSpacing: "-0.02em",
          color: accent ? "var(--color-accent)" : undefined,
        }}
      >
        {value}
      </div>
      {sub && (
        <div
          className="ink-45 text-[12px] mt-1"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          {sub}
        </div>
      )}
    </div>
  );
}

function fmtUsd(n: number): string {
  const sign = n < 0 ? "-$" : "$";
  return `${sign}${Math.abs(n).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function countDir(history: Transfer[], dir: "in" | "out"): number {
  return history.filter((t) => t.direction === dir).length;
}

function shortAddr(a: string): string {
  if (!a) return "";
  if (a.length < 12) return a;
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}

function CounterpartySection({
  history,
  pnlMode,
}: {
  history: Transfer[];
  pnlMode: "income" | "treasury";
}) {
  const [query, setQuery] = useState("");

  const { inAll, outAll } = useMemo(() => {
    const inMap = new Map<string, { count: number; usd: number }>();
    const outMap = new Map<string, { count: number; usd: number }>();
    for (const t of history) {
      const map =
        t.direction === "in" ? inMap : t.direction === "out" ? outMap : null;
      if (!map) continue;
      const prev = map.get(t.counterparty) ?? { count: 0, usd: 0 };
      prev.count += 1;
      prev.usd += t.usd ?? 0;
      map.set(t.counterparty, prev);
    }
    const sort = (m: Map<string, { count: number; usd: number }>) =>
      Array.from(m.entries()).sort((a, b) => b[1].usd - a[1].usd);
    return { inAll: sort(inMap), outAll: sort(outMap) };
  }, [history]);

  const filter = (rows: [string, { count: number; usd: number }][]) => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(([addr]) => addr.toLowerCase().includes(q));
  };

  const inRows = filter(inAll);
  const outRows = filter(outAll);

  // Vault (treasury) 는 출금처 우선, income 은 입금처 우선
  const primary = pnlMode === "treasury" ? outRows : inRows;
  const secondary = pnlMode === "treasury" ? inRows : outRows;
  const primaryLabel =
    pnlMode === "treasury" ? `출금처 (${outRows.length})` : `입금처 (${inRows.length})`;
  const secondaryLabel =
    pnlMode === "treasury" ? `입금처 (${inRows.length})` : `출금처 (${outRows.length})`;

  return (
    <div className="bg-white border border-ink-12 rounded-[18px] p-7">
      <div className="flex items-center justify-between gap-4 mb-2">
        <h3
          className="m-0 text-[26px]"
          style={{
            fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`,
            letterSpacing: "-0.01em",
          }}
        >
          카운터파티
        </h3>
        <div className="relative">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            width="13"
            height="13"
            className="absolute left-3 top-1/2 -translate-y-1/2 ink-45 pointer-events-none"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="주소 검색 (예: 0xe)"
            className="bg-transparent border border-ink-12 rounded-full pl-8 pr-3 py-1.5 text-[12.5px] ink placeholder:ink-45 focus:outline-none focus:border-ink-25 w-[200px]"
            style={{ fontFamily: "var(--font-mono)" }}
            spellCheck={false}
            autoComplete="off"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              aria-label="검색 지우기"
              className="absolute right-2 top-1/2 -translate-y-1/2 grid place-items-center w-5 h-5 rounded-full hover:bg-ink-06 ink-45 cursor-pointer"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                width="11"
                height="11"
              >
                <path d="M18 6 6 18" />
                <path d="m6 6 12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      <div className="ink-45 text-[12px] uppercase tracking-[0.12em] mt-4 mb-2">
        {primaryLabel}
      </div>
      <PaginatedRows items={primary} resetKey={query + "_primary"} />
      <div className="ink-45 text-[12px] uppercase tracking-[0.12em] mt-6 mb-2">
        {secondaryLabel}
      </div>
      <PaginatedRows items={secondary} resetKey={query + "_secondary"} />
    </div>
  );
}

function PaginatedRows({
  items,
  resetKey,
}: {
  items: [string, { count: number; usd: number }][];
  resetKey: string;
}) {
  const PAGE_SIZE = 10;
  const [page, setPage] = useState(0);
  useEffect(() => {
    setPage(0);
  }, [resetKey]);
  const start = page * PAGE_SIZE;
  const pageItems = items.slice(start, start + PAGE_SIZE);
  return (
    <>
      <CpRows items={pageItems} />
      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={items.length}
        onChange={setPage}
      />
    </>
  );
}

function CpRows({
  items,
}: {
  items: [string, { count: number; usd: number }][];
}) {
  if (items.length === 0) {
    return <div className="ink-45 text-[13px] py-4">없음</div>;
  }
  return (
    <div className="flex flex-col">
      {items.map(([addr, v]) => (
        <div
          key={addr}
          className="grid items-center gap-3 py-2.5 border-b border-ink-06 last:border-b-0"
          style={{ gridTemplateColumns: "1fr auto auto" }}
        >
          {isEvmAddress(addr) ? (
            <a
              href={`https://soneium.blockscout.com/address/${addr}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[12px] ink hover:text-[var(--color-accent)] hover:underline underline-offset-2 break-all"
              style={{ fontFamily: "var(--font-mono)" }}
              title="Blockscout 에서 열기"
            >
              {addr}
            </a>
          ) : (
            <span
              className="text-[12px] ink-60 break-all"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              {addr}
            </span>
          )}
          <div
            className="ink-45 text-[12px]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {v.count}건
          </div>
          <div
            className="text-[13px] text-right min-w-[100px]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            $
            {v.usd.toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function TokensSection({ snapshot }: { snapshot: WalletSnapshot | null }) {
  return (
    <div className="bg-white border border-ink-12 rounded-[18px] p-7">
      <h3
        className="m-0 text-[26px]"
        style={{ fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`, letterSpacing: "-0.01em" }}
      >
        보유 토큰
      </h3>
      <div className="flex flex-col mt-4">
        {!snapshot || snapshot.tokens.length === 0 ? (
          <div className="ink-45 text-[13px] py-4">없음</div>
        ) : (
          snapshot.tokens.map((t) => (
            <div
              key={t.contract || t.symbol}
              className="grid items-center gap-3 py-3 border-b border-ink-06 last:border-b-0"
              style={{ gridTemplateColumns: "32px 1fr auto" }}
            >
              <div
                className="grid place-items-center w-8 h-8 rounded-full bg-ink-06 text-[11px]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {t.symbol.slice(0, 4)}
              </div>
              <div>
                <div className="text-[14px] font-medium">{t.name || t.symbol}</div>
                <div
                  className="text-[12px] ink-45 mt-0.5"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  {t.value.toLocaleString("en-US", {
                    maximumFractionDigits: 4,
                  })}{" "}
                  {t.symbol}
                </div>
              </div>
              <div
                className="text-right text-[13.5px]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                ${t.usd.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
