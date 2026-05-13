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
  mark: string; // 단일/두 글자 라벨
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
