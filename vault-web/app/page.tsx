import { Topbar } from "@/components/topbar";
import { ProjectSwitcher } from "@/components/project-switcher";
import { HeroTotal } from "@/components/hero-total";
import { AllocationCard } from "@/components/allocation-card";
import { WalletsTable } from "@/components/wallets-table";
import { AssetsList, holdingsToItems } from "@/components/assets-list";
import { ActivityList } from "@/components/activity-list";
import { ComingSoon } from "@/components/coming-soon";
import { WalletDetail } from "@/components/wallet-detail";
import { PROJECTS, getProject } from "@/lib/projects";
import {
  buildSparkline,
  computeAllocation,
  getCombinedHistory,
  getWalletSnapshot,
} from "@/lib/soneium";
import type { Allocation } from "@/lib/soneium";
import type { TokenHolding, Transfer, WalletSnapshot } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 60;

type SearchParams = { project?: string; wallet?: string };

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const project = getProject(sp.project);
  const walletKey = sp.wallet;

  return (
    <div className="max-w-[1320px] mx-auto px-10 pt-7 pb-20">
      <Topbar />

      <section className="flex items-end justify-between gap-6 pt-9 pb-4">
        <div>
          <div className="text-[12px] ink-45 uppercase tracking-[0.12em] mb-3.5">
            현재 프로젝트
          </div>
          <ProjectSwitcher projects={PROJECTS} currentKey={project.key} />
        </div>
        <ProjectMeta
          walletCount={project.wallets.length}
          chainCount={project.comingSoon ? 0 : 1}
        />
      </section>

      {project.comingSoon ? (
        <ComingSoon project={project} />
      ) : walletKey ? (
        <WalletDetailSection projectKey={project.key} walletKey={walletKey} />
      ) : (
        <ProjectOverview projectKey={project.key} />
      )}

      <footer className="mt-12 flex justify-between ink-45 text-[12px]">
        <div
          className="flex items-center gap-2"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          <span
            className="block w-1.5 h-1.5 rounded-full"
            style={{ background: "var(--color-accent)" }}
          />
          Soneium · L2
        </div>
        <div style={{ fontFamily: "var(--font-mono)" }}>Vault — v1</div>
      </footer>
    </div>
  );
}

function ProjectMeta({
  walletCount,
  chainCount,
}: {
  walletCount: number;
  chainCount: number;
}) {
  return (
    <div className="flex gap-8 items-end ink-60 text-[13px]">
      <div>
        지갑 수
        <b
          className="block text-[15px] font-medium mt-0.5"
          style={{ color: "var(--color-ink)", fontFamily: "var(--font-mono)" }}
        >
          {walletCount}
        </b>
      </div>
      <div>
        네트워크
        <b
          className="block text-[15px] font-medium mt-0.5"
          style={{ color: "var(--color-ink)", fontFamily: "var(--font-mono)" }}
        >
          {chainCount > 0 ? "Soneium" : "—"}
        </b>
      </div>
      <div>
        업데이트
        <b
          className="block text-[15px] font-medium mt-0.5"
          style={{ color: "var(--color-ink)", fontFamily: "var(--font-mono)" }}
        >
          방금 전
        </b>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// 프로젝트 개요 (Hero + 분포 + 지갑 + 자산 + 활동)
// ─────────────────────────────────────────────────────────────────

async function ProjectOverview({ projectKey }: { projectKey: string }) {
  const project = getProject(projectKey);
  const activeWallets = project.wallets.filter((w) => w.address);

  // 병렬로 snapshot + history 조회
  const snapshots = await Promise.all(
    activeWallets.map((w) =>
      getWalletSnapshot(w.address).catch(() => null as WalletSnapshot | null),
    ),
  );
  const histories = await Promise.all(
    activeWallets.map((w) =>
      getCombinedHistory(w.address, 500).catch(() => [] as Transfer[]),
    ),
  );

  // 총합
  let totalUsd = 0;
  const allTokens: Map<string, TokenHolding> = new Map();
  let totalEthUsd = 0;
  let totalEthAmt = 0;
  for (const s of snapshots) {
    if (!s) continue;
    totalUsd += s.totalUsd;
    totalEthUsd += s.ethUsd;
    totalEthAmt += s.eth;
    for (const t of s.tokens) {
      const prev = allTokens.get(t.symbol);
      if (prev) {
        prev.value += t.value;
        prev.usd += t.usd;
      } else {
        allTokens.set(t.symbol, { ...t });
      }
    }
  }
  const aggTokens = Array.from(allTokens.values());

  const allocation: Allocation[] = computeAllocation(aggTokens, totalEthUsd);
  const assetItems = holdingsToItems(aggTokens, totalEthUsd, totalEthAmt);

  // 24h 변화 — 최근 24h 의 net USD 흐름 합산
  const since = Date.now() - 24 * 3600 * 1000;
  let delta24h = 0;
  for (const h of histories) {
    for (const t of h) {
      const ts = new Date(t.timestamp).getTime();
      if (ts < since) continue;
      const usd = t.usd ?? 0;
      delta24h += t.direction === "in" ? usd : t.direction === "out" ? -usd : 0;
    }
  }
  const deltaPct = totalUsd > 0 ? (delta24h / totalUsd) * 100 : 0;

  // 스파크라인 — 모든 활동의 cumulative net USD
  const allHistory = histories.flat();
  const spark = buildSparkline(allHistory);

  // 활동 — 최근 8건
  const allRecent = allHistory
    .sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1))
    .slice(0, 12);

  const walletRows = activeWallets.map((w, i) => ({
    wallet: w,
    snapshot: snapshots[i],
  }));
  // 빈 주소도 row 로 (주소 미설정 안내)
  const placeholderRows = project.wallets
    .filter((w) => !w.address)
    .map((w) => ({ wallet: w, snapshot: null }));
  const rows = [...walletRows, ...placeholderRows];

  return (
    <>
      <section className="grid gap-6 mt-3" style={{ gridTemplateColumns: "1.4fr 1fr" }}>
        <HeroTotal
          totalUsd={totalUsd}
          deltaPct={deltaPct}
          deltaAbs={delta24h}
          spark={spark}
        />
        <AllocationCard items={allocation} />
      </section>

      <section className="grid gap-6 mt-6" style={{ gridTemplateColumns: "1.6fr 1fr" }}>
        <WalletsTable projectKey={project.key} rows={rows} />
        <AssetsList items={assetItems} />
      </section>

      <ActivityList items={allRecent} />
    </>
  );
}

async function WalletDetailSection({
  projectKey,
  walletKey,
}: {
  projectKey: string;
  walletKey: string;
}) {
  const project = getProject(projectKey);
  const wallet = project.wallets.find((w) => w.key === walletKey);
  if (!wallet || !wallet.address) {
    return (
      <div className="bg-white border border-ink-12 rounded-[18px] p-8 mt-3 ink-60">
        지갑 정보를 찾을 수 없습니다.
      </div>
    );
  }
  const [snapshot, history] = await Promise.all([
    getWalletSnapshot(wallet.address).catch(() => null as WalletSnapshot | null),
    getCombinedHistory(wallet.address, 2000).catch(() => [] as Transfer[]),
  ]);
  return (
    <WalletDetail
      project={project}
      wallet={wallet}
      snapshot={snapshot}
      history={history}
    />
  );
}
