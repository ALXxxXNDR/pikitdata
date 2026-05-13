export type PnlMode = "income" | "treasury";
export type WalletKind = "revenue" | "reward";

export type WalletConfig = {
  key: string;
  name: string;
  address: string;
  description?: string;
  kind: WalletKind;
  pnlMode: PnlMode;
  alertThresholdUsd: number | null;
};

export type ProjectConfig = {
  key: string;
  name: string;
  mark: string; // 로고 미설정 시 fallback 글자
  logo?: string; // public/ 기준 경로 (예: "/logos/pikit.png")
  description?: string;
  team?: string;
  comingSoon?: boolean;
  wallets: WalletConfig[];
};

export type TokenHolding = {
  symbol: string;
  name: string;
  decimals: number;
  contract: string;
  value: number; // 토큰 액면 수량
  exchangeRate: number | null;
  usd: number; // stablecoin 은 액면가
};

export type WalletSnapshot = {
  address: string;
  eth: number;
  ethUsdRate: number; // ETH/USD
  ethUsd: number;
  tokens: TokenHolding[];
  tokensUsd: number;
  totalUsd: number;
};

export type Direction = "in" | "out" | "self";

export type BalancePoint = {
  ts: number; // epoch ms
  value: number; // USD
};

// HeroTotal 의 contract 셀렉터에 쓰이는 옵션 단위.
// '_all' 은 프로젝트 전체 합계를 의미.
export type WalletOption = {
  key: string; // "_all" | wallet.key
  name: string; // "전체" | wallet.name
  totalUsd: number;
  curve: BalancePoint[];
};

export type Transfer = {
  hash: string;
  timestamp: string; // ISO
  direction: Direction;
  counterparty: string;
  symbol: string;
  value: number;
  usd: number | null;
  kind: "native" | "token";
};
