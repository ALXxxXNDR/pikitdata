import type {
  BalancePoint,
  Direction,
  TokenHolding,
  Transfer,
  WalletSnapshot,
} from "./types";

const BLOCKSCOUT_BASE = "https://soneium.blockscout.com/api/v2";
const COINGECKO_ETH = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd";

const OFFICIAL_RPCS = ["https://rpc.soneium.org", "https://soneium.drpc.org"];

function getRpcUrls(): string[] {
  const urls: string[] = [];
  let t = (process.env.TENDERLY_RPC_URL ?? "").trim();
  if (t.startsWith("wss://")) t = "https://" + t.slice("wss://".length);
  if (t.startsWith("ws://")) t = "http://" + t.slice("ws://".length);
  if (t) urls.push(t);
  urls.push(...OFFICIAL_RPCS);
  return urls;
}

const STABLE_SYMBOLS = new Set([
  "USDC", "USDT", "USDSC", "DAI", "BUSD", "TUSD", "USDD", "FRAX", "GUSD",
]);

export function isStablecoin(symbol: string | undefined, rate: number | null): boolean {
  if (symbol) {
    const s = symbol.toUpperCase().trim();
    if (STABLE_SYMBOLS.has(s)) return true;
    if (s.includes("USD") && s.length <= 8) return true;
  }
  if (rate !== null && rate >= 0.97 && rate <= 1.03) return true;
  return false;
}

function tokenToUsd(value: number, rate: number | null, symbol: string | undefined): number {
  if (isStablecoin(symbol, rate)) return value;
  if (rate === null) return 0;
  return value * rate;
}

// ─────────────────────────────────────────────────────────────────
// RPC — eth_getBalance with failover
// ─────────────────────────────────────────────────────────────────

async function rpcCall<T = unknown>(method: string, params: unknown[]): Promise<T> {
  let lastErr: unknown = null;
  for (const url of getRpcUrls()) {
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
        // 서버 컴포넌트의 fetch 는 next 캐시 사용
        next: { revalidate: 30 },
      });
      if (!r.ok) {
        lastErr = new Error(`RPC ${url} HTTP ${r.status}`);
        continue;
      }
      const data = await r.json();
      if (data.error) {
        lastErr = new Error(`RPC ${url} error: ${JSON.stringify(data.error)}`);
        continue;
      }
      return data.result as T;
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr ?? new Error("모든 RPC 실패");
}

async function getEthBalanceWei(address: string): Promise<bigint> {
  const hex = await rpcCall<string>("eth_getBalance", [address, "latest"]);
  return BigInt(hex);
}

// ─────────────────────────────────────────────────────────────────
// Blockscout REST
// ─────────────────────────────────────────────────────────────────

type BlockscoutPaginated<T> = {
  items?: T[];
  next_page_params?: Record<string, string | number | null> | null;
};

type BsToken = {
  symbol?: string;
  name?: string;
  decimals?: string | number;
  address_hash?: string;
  exchange_rate?: string | number | null;
};

type BsTokenHolding = {
  token?: BsToken;
  value?: string | number;
};

type BsAddressRef = { hash?: string };

type BsNativeTx = {
  hash?: string;
  timestamp?: string;
  from?: BsAddressRef;
  to?: BsAddressRef;
  value?: string | number;
};

type BsTokenTransfer = {
  transaction_hash?: string;
  tx_hash?: string;
  timestamp?: string;
  from?: BsAddressRef;
  to?: BsAddressRef;
  total?: { value?: string | number };
  token?: BsToken;
};

async function bsGet<T>(
  path: string,
  params?: Record<string, string>,
): Promise<BlockscoutPaginated<T>> {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const url = `${BLOCKSCOUT_BASE}${path}${qs}`;
  const r = await fetch(url, { next: { revalidate: 30 } });
  if (!r.ok) throw new Error(`Blockscout ${path} HTTP ${r.status}`);
  return (await r.json()) as BlockscoutPaginated<T>;
}

async function bsGetPaginated<T>(
  path: string,
  maxItems = 2000,
  maxPages = 50,
): Promise<T[]> {
  const items: T[] = [];
  let params: Record<string, string> | undefined;
  for (let i = 0; i < maxPages; i++) {
    const data = await bsGet<T>(path, params);
    const page = data.items ?? [];
    items.push(...page);
    if (items.length >= maxItems) return items.slice(0, maxItems);
    const next = data.next_page_params;
    if (!next) return items;
    // next_page_params 는 객체 → 쿼리스트링으로 변환
    const obj: Record<string, string> = {};
    for (const [k, v] of Object.entries(next)) {
      if (v === null || v === undefined) continue;
      obj[k] = String(v);
    }
    params = obj;
  }
  return items;
}

// ETH/USD 캐시 — CoinGecko 60s
let ethRateCache: { ts: number; value: number } | null = null;

async function getEthUsd(): Promise<number> {
  const now = Date.now();
  if (ethRateCache && now - ethRateCache.ts < 60_000) return ethRateCache.value;
  try {
    const r = await fetch(COINGECKO_ETH, { next: { revalidate: 60 } });
    if (!r.ok) throw new Error("coingecko");
    const data = await r.json();
    const v = Number(data?.ethereum?.usd ?? 0);
    if (!Number.isFinite(v) || v <= 0) throw new Error("rate invalid");
    ethRateCache = { ts: now, value: v };
    return v;
  } catch {
    return ethRateCache?.value ?? 0;
  }
}

// ─────────────────────────────────────────────────────────────────
// Public — wallet snapshot + history
// ─────────────────────────────────────────────────────────────────

export async function getTokenHoldings(address: string): Promise<TokenHolding[]> {
  const data = await bsGet<BsTokenHolding>(`/addresses/${address}/tokens`, {
    type: "ERC-20",
  });
  const items = data.items ?? [];
  return items.map((it) => {
    const tok = it.token ?? {};
    const decimals = Number(tok.decimals ?? 18) || 18;
    const raw = BigInt(it.value ?? 0);
    const divisor = 10 ** decimals;
    const value = Number(raw) / divisor;
    const rateRaw = tok.exchange_rate;
    const rateNum = rateRaw != null ? Number(rateRaw) : NaN;
    const rate = Number.isFinite(rateNum) ? rateNum : null;
    const symbol = tok.symbol ?? "?";
    return {
      symbol,
      name: tok.name ?? "",
      decimals,
      contract: tok.address_hash ?? "",
      value,
      exchangeRate: rate,
      usd: tokenToUsd(value, rate, symbol),
    };
  });
}

export async function getWalletSnapshot(address: string): Promise<WalletSnapshot> {
  const [wei, rate, tokens] = await Promise.all([
    getEthBalanceWei(address).catch(() => 0n),
    getEthUsd(),
    getTokenHoldings(address).catch(() => [] as TokenHolding[]),
  ]);
  const eth = Number(wei) / 1e18;
  const ethUsd = eth * rate;
  const tokensUsd = tokens.reduce((s, t) => s + t.usd, 0);
  return {
    address,
    eth,
    ethUsdRate: rate,
    ethUsd,
    tokens,
    tokensUsd,
    totalUsd: ethUsd + tokensUsd,
  };
}

export async function getCombinedHistory(address: string, limit = 2000): Promise<Transfer[]> {
  const addrLo = address.toLowerCase();
  const out: Transfer[] = [];

  // native txs (ETH transfers)
  try {
    const txs = await bsGetPaginated<BsNativeTx>(
      `/addresses/${address}/transactions`,
      limit,
    );
    for (const tx of txs) {
      const ts = tx.timestamp ?? "";
      const fr = (tx.from?.hash ?? "").toLowerCase();
      const to = (tx.to?.hash ?? "").toLowerCase();
      const valWei = BigInt(tx.value ?? 0);
      const valEth = Number(valWei) / 1e18;
      if (valEth === 0) continue;
      const direction: Direction = fr === to ? "self" : to === addrLo ? "in" : "out";
      out.push({
        hash: tx.hash ?? "",
        timestamp: ts,
        direction,
        counterparty: direction === "in" ? fr : to,
        symbol: "ETH",
        value: valEth,
        usd: null,
        kind: "native",
      });
    }
  } catch {
    // ignore
  }

  // ERC20 transfers
  try {
    const tts = await bsGetPaginated<BsTokenTransfer>(
      `/addresses/${address}/token-transfers`,
      limit,
    );
    for (const tt of tts) {
      const ts = tt.timestamp ?? "";
      const fr = (tt.from?.hash ?? "").toLowerCase();
      const to = (tt.to?.hash ?? "").toLowerCase();
      const tok = tt.token ?? {};
      const decimals = Number(tok.decimals ?? 18) || 18;
      const raw = BigInt(tt.total?.value ?? 0);
      const val = Number(raw) / 10 ** decimals;
      const rateRaw = tok.exchange_rate;
      const rateNum = rateRaw != null ? Number(rateRaw) : NaN;
      const rate = Number.isFinite(rateNum) ? rateNum : null;
      const symbol = tok.symbol ?? "?";
      const usd =
        rate !== null || isStablecoin(symbol, null)
          ? tokenToUsd(val, rate, symbol)
          : null;
      const direction: Direction = fr === to ? "self" : to === addrLo ? "in" : "out";
      out.push({
        hash: tt.transaction_hash ?? tt.tx_hash ?? "",
        timestamp: ts,
        direction,
        counterparty: direction === "in" ? fr : to,
        symbol,
        value: val,
        usd,
        kind: "token",
      });
    }
  } catch {
    // ignore
  }

  out.sort((a, b) => (a.timestamp < b.timestamp ? 1 : a.timestamp > b.timestamp ? -1 : 0));
  return out.slice(0, limit);
}

// ─────────────────────────────────────────────────────────────────
// 분석 헬퍼
// ─────────────────────────────────────────────────────────────────

export type Allocation = { name: string; pct: number; usd: number };

export function computeAllocation(tokens: TokenHolding[], ethUsd: number): Allocation[] {
  const total = tokens.reduce((s, t) => s + t.usd, 0) + ethUsd;
  if (total <= 0) return [];
  const rows: Allocation[] = [];
  if (ethUsd > 0) rows.push({ name: "ETH", pct: (ethUsd / total) * 100, usd: ethUsd });
  for (const t of tokens) {
    rows.push({ name: t.symbol, pct: (t.usd / total) * 100, usd: t.usd });
  }
  rows.sort((a, b) => b.usd - a.usd);
  return rows;
}

export function buildBalanceCurve(
  currentUsd: number,
  history: Transfer[],
): BalancePoint[] {
  // 거래 내역을 역방향으로 적용해서 시간별 잔고 곡선 재구성.
  // 가정: 현재 USD 가치 기준의 잔고. (과거 시점의 정확한 USD 가치는 모름 —
  // stablecoin 위주 wallet 이라 큰 오차 없음. 비-stablecoin 이라면 표시 가치는
  // 액면가 ± 현재 환율로 근사.)
  if (history.length === 0) {
    return [{ ts: Date.now(), value: currentUsd }];
  }
  const sorted = [...history].sort((a, b) =>
    a.timestamp > b.timestamp ? -1 : a.timestamp < b.timestamp ? 1 : 0,
  );
  let balance = currentUsd;
  const points: BalancePoint[] = [{ ts: Date.now(), value: balance }];
  for (const t of sorted) {
    const ts = new Date(t.timestamp).getTime();
    if (!Number.isFinite(ts)) continue;
    const effect =
      t.direction === "in"
        ? t.usd ?? 0
        : t.direction === "out"
          ? -(t.usd ?? 0)
          : 0;
    balance = balance - effect;
    points.push({ ts, value: Math.max(0, balance) });
  }
  // 시간 오름차순으로 반환 (차트는 left→right 시간 순)
  return points.reverse();
}
