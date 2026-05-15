"use client";

import {
  Suspense,
  use,
  useEffect,
  useMemo,
  useState,
  useTransition,
} from "react";
import Link from "next/link";
import { ActivityList } from "./activity-list";
import { AlertConfigButton } from "./alert-config-button";
import { Pagination } from "./pagination";
import { CardSkeleton, MetricSkeleton, Spinner } from "./loading-skeleton";
import { isEvmAddress, isTxHash } from "@/lib/format";
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
  // 각 promise 가 별도로 fetch. sub-section 별로 use() → 자기 데이터만 await.
  snapshotPromise: Promise<WalletSnapshot | null>;
  // Activity 첫 페이지용 — limit 20 의 빠른 fetch. 페이지 즉시 painting.
  recentHistoryPromise: Promise<Transfer[]>;
  // Metric / Counterparty / Activity 페이지네이션 — limit 500 의 느린 fetch.
  fullHistoryPromise: Promise<Transfer[]>;
  alertConfigPromise: Promise<AlertConfig>;
  kvConfigured: boolean;
};

export function WalletDetail({
  project,
  wallet,
  snapshotPromise,
  recentHistoryPromise,
  fullHistoryPromise,
  alertConfigPromise,
  kvConfigured,
}: Props) {
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
        <Suspense fallback={<AlertButtonPlaceholder />}>
          <AlertButtonLoader
            project={project}
            wallet={wallet}
            alertConfigPromise={alertConfigPromise}
            kvConfigured={kvConfigured}
          />
        </Suspense>
      </div>

      <h2
        className="mt-4 text-[40px]"
        style={{ fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`, letterSpacing: "-0.02em" }}
      >
        {wallet.name}
      </h2>
      <p className="ink-60 text-[14px] mt-1">{wallet.description}</p>

      <Suspense fallback={<MetricsFallback />}>
        <MetricsLoader
          snapshotPromise={snapshotPromise}
          historyPromise={fullHistoryPromise}
          wallet={wallet}
        />
      </Suspense>

      <section className="mt-6 grid gap-6" style={{ gridTemplateColumns: "1.4fr 1fr" }}>
        <Suspense
          fallback={<CardSkeleton title="카운터파티" minHeight={460} />}
        >
          <CounterpartyLoader
            historyPromise={fullHistoryPromise}
            pnlMode={wallet.pnlMode}
          />
        </Suspense>
        <Suspense
          fallback={<CardSkeleton title="보유 토큰" minHeight={460} />}
        >
          <TokensLoader snapshotPromise={snapshotPromise} />
        </Suspense>
      </section>

      <Suspense fallback={<CardSkeleton title="최근 활동" minHeight={360} />}>
        <ActivityLoader
          recentHistoryPromise={recentHistoryPromise}
          fullHistoryPromise={fullHistoryPromise}
        />
      </Suspense>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────
// Sub-section loaders — 각자 자기 promise 만 use() → 독립적 Suspense
// ─────────────────────────────────────────────────────────────────

function AlertButtonLoader({
  project,
  wallet,
  alertConfigPromise,
  kvConfigured,
}: {
  project: ProjectConfig;
  wallet: WalletConfig;
  alertConfigPromise: Promise<AlertConfig>;
  kvConfigured: boolean;
}) {
  const alertConfig = use(alertConfigPromise);
  return (
    <AlertConfigButton
      projectKey={project.key}
      walletKey={wallet.key}
      walletName={wallet.name}
      initial={alertConfig}
      kvConfigured={kvConfigured}
    />
  );
}

function AlertButtonPlaceholder() {
  return (
    <button
      type="button"
      disabled
      aria-busy="true"
      className="inline-flex items-center gap-2 pl-2.5 pr-3.5 py-1.5 rounded-full text-[12.5px] border border-ink-12 ink-45 cursor-default"
      style={{ opacity: 0.65 }}
    >
      <Spinner size={12} />
      <span>알림 설정</span>
    </button>
  );
}

function MetricsLoader({
  snapshotPromise,
  historyPromise,
  wallet,
}: {
  snapshotPromise: Promise<WalletSnapshot | null>;
  historyPromise: Promise<Transfer[]>;
  wallet: WalletConfig;
}) {
  // snapshot + history 둘 다 필요 — 둘 중 늦은 것 기준으로 unsuspend.
  // (총 USD 만 snapshot, 입출금/PNL 은 history. 같이 grid 라 묶음 처리.)
  const snapshot = use(snapshotPromise);
  const history = use(historyPromise);

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
      <Metric
        label={inLabel}
        value={fmtUsd(totalIn)}
        sub={`${countDir(history, "in")}건`}
      />
      <Metric
        label={outLabel}
        value={fmtUsd(totalOut)}
        sub={`${countDir(history, "out")}건`}
      />
      <Metric label={pnlLabel} value={fmtUsd(pnl)} accent={pnl > 0} />
    </section>
  );
}

function MetricsFallback() {
  return (
    <section
      className="grid gap-6 mt-6"
      style={{ gridTemplateColumns: "repeat(4, 1fr)" }}
    >
      {[1, 2, 3, 4].map((i) => (
        <MetricSkeleton key={i} />
      ))}
    </section>
  );
}

function CounterpartyLoader({
  historyPromise,
  pnlMode,
}: {
  historyPromise: Promise<Transfer[]>;
  pnlMode: "income" | "treasury";
}) {
  const history = use(historyPromise);
  return <CounterpartySection history={history} pnlMode={pnlMode} />;
}

function TokensLoader({
  snapshotPromise,
}: {
  snapshotPromise: Promise<WalletSnapshot | null>;
}) {
  const snapshot = use(snapshotPromise);
  return <TokensSection snapshot={snapshot} />;
}

function ActivityLoader({
  recentHistoryPromise,
  fullHistoryPromise,
}: {
  recentHistoryPromise: Promise<Transfer[]>;
  fullHistoryPromise: Promise<Transfer[]>;
}) {
  // recent (limit 20) — 즉시 첫 페이지 painting
  const recent = use(recentHistoryPromise);
  const [items, setItems] = useState(recent);
  const [, startTransition] = useTransition();

  // full (limit 500) — 백그라운드 도착 시 부드럽게 swap
  useEffect(() => {
    let cancelled = false;
    fullHistoryPromise.then((full) => {
      if (cancelled) return;
      // cache 깨짐/error 로 full 이 더 작으면 swap 안 함.
      if (full.length < recent.length) return;
      startTransition(() => setItems(full));
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullHistoryPromise]);

  return <ActivityList items={items} />;
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

// 카운터파티 행이 펼쳐졌을 때 보이는 트랜잭션 row 의 데이터.
type CpAgg = { count: number; usd: number; txs: Transfer[] };
type CpRow = [string, CpAgg];

function CounterpartySection({
  history,
  pnlMode,
}: {
  history: Transfer[];
  pnlMode: "income" | "treasury";
}) {
  const [query, setQuery] = useState("");

  const { inAll, outAll } = useMemo(() => {
    const inMap = new Map<string, Transfer[]>();
    const outMap = new Map<string, Transfer[]>();
    for (const t of history) {
      const map =
        t.direction === "in" ? inMap : t.direction === "out" ? outMap : null;
      if (!map) continue;
      const arr = map.get(t.counterparty);
      if (arr) arr.push(t);
      else map.set(t.counterparty, [t]);
    }
    const toRows = (m: Map<string, Transfer[]>): CpRow[] =>
      Array.from(m.entries())
        .map(([addr, txs]): CpRow => [
          addr,
          {
            count: txs.length,
            usd: txs.reduce((s, t) => s + (t.usd ?? 0), 0),
            txs,
          },
        ])
        .sort((a, b) => b[1].usd - a[1].usd);
    return { inAll: toRows(inMap), outAll: toRows(outMap) };
  }, [history]);

  const filter = (rows: CpRow[]): CpRow[] => {
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
  items: CpRow[];
  resetKey: string;
}) {
  const PAGE_SIZE = 10;
  const [page, setPage] = useState(0);
  // 펼쳐진 카운터파티 주소 set — 다중 토글 가능.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // query 또는 primary/secondary 섹션이 바뀌면 page + expand 둘 다 reset.
  useEffect(() => {
    setPage(0);
    setExpanded(new Set());
  }, [resetKey]);
  const toggle = (addr: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(addr)) next.delete(addr);
      else next.add(addr);
      return next;
    });
  };
  const start = page * PAGE_SIZE;
  const pageItems = items.slice(start, start + PAGE_SIZE);
  return (
    <>
      <CpRows items={pageItems} expanded={expanded} onToggle={toggle} />
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
  expanded,
  onToggle,
}: {
  items: CpRow[];
  expanded: Set<string>;
  onToggle: (addr: string) => void;
}) {
  if (items.length === 0) {
    return <div className="ink-45 text-[13px] py-4">없음</div>;
  }
  return (
    <div className="flex flex-col">
      {items.map(([addr, v]) => {
        const isOpen = expanded.has(addr);
        return (
          <div
            key={addr}
            className="border-b border-ink-06 last:border-b-0"
          >
            <div
              role="button"
              tabIndex={0}
              onClick={() => onToggle(addr)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onToggle(addr);
                }
              }}
              aria-expanded={isOpen}
              className={`grid items-center gap-3 py-2.5 cursor-pointer rounded-[8px] -mx-2 px-2 hover:bg-ink-03 ${
                isOpen ? "bg-ink-03" : ""
              }`}
              style={{ gridTemplateColumns: "16px 1fr auto auto" }}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                width="11"
                height="11"
                className={`ink-45 transition-transform ${
                  isOpen ? "rotate-90" : ""
                }`}
                aria-hidden="true"
              >
                <polyline points="9 6 15 12 9 18" />
              </svg>
              {isEvmAddress(addr) ? (
                <a
                  href={`https://soneium.blockscout.com/address/${addr}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
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
            {isOpen && <TxList txs={v.txs} />}
          </div>
        );
      })}
    </div>
  );
}

function TxList({ txs }: { txs: Transfer[] }) {
  // 최신순 — history 가 시간 역순 sort 되어 있어서 그대로면 최신순.
  if (txs.length === 0) {
    return (
      <div
        className="px-3 py-2 mb-1 rounded-[10px] ink-45 text-[12px]"
        style={{
          background: "color-mix(in srgb, var(--color-ink) 4%, transparent)",
          marginLeft: 8,
        }}
      >
        트랜잭션 없음
      </div>
    );
  }
  // grid 를 부모 컨테이너에 한 번만 정의 → 모든 row 가 같은 column track
  // 공유. 각 row 는 4개 sibling 셀만 emit (React.Fragment) → 같은 column
  // 위에서 align (USDSC 가 1 vs 20 처럼 폭 다른 amount 도 정렬됨).
  return (
    <div
      className="px-3 py-2 mb-1 rounded-[10px] grid items-center gap-x-3"
      style={{
        background: "color-mix(in srgb, var(--color-ink) 4%, transparent)",
        marginLeft: 8,
        gridTemplateColumns: "1.4fr 1fr auto auto",
      }}
    >
      {txs.map((t, i) => (
        <TxRowCells
          key={t.hash + i}
          tx={t}
          isLast={i === txs.length - 1}
        />
      ))}
    </div>
  );
}

function TxRowCells({ tx, isLast }: { tx: Transfer; isLast: boolean }) {
  const txValid = isTxHash(tx.hash);
  const hashShort = tx.hash
    ? `${tx.hash.slice(0, 10)}…${tx.hash.slice(-6)}`
    : "—";
  const dt = new Date(tx.timestamp);
  const valid = !Number.isNaN(dt.getTime());
  const cellBorder = isLast
    ? undefined
    : "1px solid color-mix(in srgb, var(--color-ink) 5%, transparent)";
  const cellStyle: React.CSSProperties = {
    fontFamily: "var(--font-mono)",
    paddingTop: 6,
    paddingBottom: 6,
    borderBottom: cellBorder,
  };
  return (
    <>
      <div style={cellStyle}>
        {txValid ? (
          <a
            href={`https://soneium.blockscout.com/tx/${tx.hash}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-[11.5px] ink-60 hover:text-[var(--color-accent)] hover:underline underline-offset-2 truncate block"
            title={tx.hash}
          >
            {hashShort}
          </a>
        ) : (
          <span className="text-[11.5px] ink-45 truncate block">
            {hashShort}
          </span>
        )}
      </div>
      <div
        className="text-[11.5px] ink-60"
        style={cellStyle}
        title={valid ? dt.toISOString() : ""}
      >
        {valid ? fmtTxDate(dt) : "—"}
      </div>
      <div className="text-[12px] text-right ink-60" style={cellStyle}>
        {tx.value.toLocaleString("en-US", {
          maximumFractionDigits: 4,
        })}{" "}
        {tx.symbol}
      </div>
      <div
        className="text-[12px] text-right"
        style={{ ...cellStyle, minWidth: 80 }}
      >
        {tx.usd != null
          ? `$${tx.usd.toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}`
          : "—"}
      </div>
    </>
  );
}

function fmtTxDate(d: Date): string {
  // YYYY-MM-DD HH:mm — local time
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${day} ${hh}:${mm}`;
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
