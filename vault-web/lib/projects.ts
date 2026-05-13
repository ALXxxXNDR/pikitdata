import type { ProjectConfig } from "./types";

export const PROJECTS: ProjectConfig[] = [
  {
    key: "pikit",
    name: "PIKIT",
    mark: "P",
    description: "PIKIT 메인 프로젝트",
    team: "Soneium · Game",
    wallets: [
      {
        key: "revenue",
        name: "운영 수익 지갑",
        address: "0x79fc40D88496b6b92EB789d28974dd6C162e8D6E",
        description: "PIKIT 운영 수익이 모이는 지갑",
        kind: "revenue",
        pnlMode: "income",
        alertThresholdUsd: null,
      },
      {
        key: "reward_vault",
        name: "유저 리워드 Vault",
        address: "0xee5c5c0f3817563d924c563294b8d4c56d3bd722",
        description: "유저에게 지급되는 리워드 컨트랙트",
        kind: "reward",
        pnlMode: "treasury",
        alertThresholdUsd: 300,
      },
    ],
  },
  {
    key: "press_a",
    name: "Press A",
    mark: "A",
    description: "Press A 프로젝트",
    team: "Soneium · Game",
    wallets: [
      {
        key: "revenue",
        name: "운영 수익 지갑",
        address: "", // TODO: 주소 등록
        description: "Press A 운영 수익",
        kind: "revenue",
        pnlMode: "income",
        alertThresholdUsd: null,
      },
      {
        key: "reward_pool",
        name: "리워드 풀",
        address: "", // TODO: 주소 등록
        description: "Press A 리워드 지급 풀",
        kind: "reward",
        pnlMode: "treasury",
        alertThresholdUsd: 300,
      },
    ],
  },
  {
    key: "pnyx",
    name: "Pnyx",
    mark: "X",
    description: "Pnyx · 준비 중",
    team: "Coming soon",
    comingSoon: true,
    wallets: [],
  },
];

export function getProject(key: string | undefined): ProjectConfig {
  if (!key) return PROJECTS[0];
  return PROJECTS.find((p) => p.key === key) ?? PROJECTS[0];
}

export function activeWallets(): {
  project: ProjectConfig;
  wallet: ProjectConfig["wallets"][number];
}[] {
  const out: { project: ProjectConfig; wallet: ProjectConfig["wallets"][number] }[] = [];
  for (const p of PROJECTS) {
    if (p.comingSoon) continue;
    for (const w of p.wallets) {
      if (!w.address) continue;
      out.push({ project: p, wallet: w });
    }
  }
  return out;
}
