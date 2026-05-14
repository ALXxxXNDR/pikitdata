import { Suspense } from "react";
import { Topbar } from "@/components/topbar";
import { ProjectSwitcher } from "@/components/project-switcher";
import { HeroTotal } from "@/components/hero-total";
import { WalletsTable } from "@/components/wallets-table";
import { AssetsList, holdingsToItems } from "@/components/assets-list";
import { ActivityList } from "@/components/activity-list";
import { ComingSoon } from "@/components/coming-soon";
import { LiveTimestamp } from "@/components/live-timestamp";
import { WalletDetail } from "@/components/wallet-detail";
import {
  ProjectOverviewSkeleton,
  WalletDetailSkeleton,
} from "@/components/loading-skeleton";
import { getAlertConfig, isKvConfigured } from "@/lib/alert-config";
import { PROJECTS, getProject } from "@/lib/projects";
import {
  buildBalanceCurve,
  computeAllocation,
  getCombinedHistory,
  getWalletSnapshot,
} from "@/lib/soneium";
import type { Allocation } from "@/lib/soneium";
import type {
  ProjectConfig,
  TokenHolding,
  Transfer,
  WalletOption,
  WalletSnapshot,
} from "@/lib/types";

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
          serverTimeMs={Date.now()}
        />
      </section>

      <MainContent project={project} walletKey={walletKey} />

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

/**
 * 메인 콘텐츠 분기 — Suspense 로 wrap 해서 server-side streaming.
 * 페이지 자체는 즉시 응답 → 헤더/스위처/푸터 painting, 데이터 의존 섹션은
 * skeleton fallback 표시 → fetch 끝나면 자동 swap.
 */
function MainContent({
  project,
  walletKey,
}: {
  project: ProjectConfig;
  walletKey: string | undefined;
}) {
  if (project.comingSoon) {
    return <ComingSoon project={project} />;
  }
  if (walletKey) {
    const wallet = project.wallets.find((w) => w.key === walletKey);
    if (!wallet || !wallet.address) {
      return (
        <div className="bg-white border border-ink-12 rounded-[18px] p-8 mt-3 ink-60">
          지갑 정보를 찾을 수 없습니다.
        </div>
      );
    }
    return (
      <Suspense
        key={`${project.key}/${walletKey}`}
        fallback={<WalletDetailSkeleton project={project} wallet={wallet} />}
      >
        <WalletDetailSection
          projectKey={project.key}
          walletKey={walletKey}
        />
      </Suspense>
    );
  }
  return (
    <Suspense
      key={project.key}
      fallback={<ProjectOverviewSkeleton project={project} />}
    >
      <ProjectOverview projectKey={project.key} />
    </Suspense>
  );
}

function ProjectMeta({
  walletCount,
  chainCount,
  serverTimeMs,
}: {
  walletCount: number;
  chainCount: number;
  serverTimeMs: number;
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
          style={{ color: "var(--color-ink)" }}
        >
          <LiveTimestamp serverTimeMs={serverTimeMs} />
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

  // 총자산 곡선 — 현재 잔고에서 역방향으로 거래 적용 (전체 합계)
  const allHistory = histories.flat();
  const balanceCurve = buildBalanceCurve(totalUsd, allHistory);

  // contract 셀렉터 옵션 — 전체 + 각 활성 지갑
  const walletOptions: WalletOption[] = [
    { key: "_all", name: "전체 (Total)", totalUsd, curve: balanceCurve },
    ...activeWallets.map((w, i) => {
      const snap = snapshots[i];
      const hist = histories[i] ?? [];
      const wTotal = snap?.totalUsd ?? 0;
      return {
        key: w.key,
        name: w.name,
        totalUsd: wTotal,
        curve: buildBalanceCurve(wTotal, hist),
      };
    }),
  ];

  // 활동 — 최근 200건 (페이지네이션이 클라에서 처리)
  const allRecent = allHistory
    .sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1))
    .slice(0, 200);

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
      <section className="mt-3">
        <HeroTotal options={walletOptions} />
      </section>

      <section
        className="grid gap-6 mt-6"
        style={{ gridTemplateColumns: "1.6fr 1fr" }}
      >
        <WalletsTable projectKey={project.key} rows={rows} />
        <AssetsList items={assetItems} allocation={allocation} />
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
  const [snapshot, history, alertConfig] = await Promise.all([
    getWalletSnapshot(wallet.address).catch(() => null as WalletSnapshot | null),
    getCombinedHistory(wallet.address, 2000).catch(() => [] as Transfer[]),
    getAlertConfig(project.key, wallet.key),
  ]);
  return (
    <WalletDetail
      project={project}
      wallet={wallet}
      snapshot={snapshot}
      history={history}
      alertConfig={alertConfig}
      kvConfigured={isKvConfigured()}
    />
  );
}
