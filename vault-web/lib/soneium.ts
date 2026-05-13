import type { Direction, TokenHolding, Transfer, WalletSnapshot } from "./types";

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

async function bsGet(path: string, params?: Record<string, string>): Promise<any> {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const url = `${BLOCKSCOUT_BASE}${path}${qs}`;
  const r = await fetch(url, { next: { revalidate: 30 } });
  if (!r.ok) throw new Error(`Blockscout ${path} HTTP ${r.status}`);
  return r.json();
}

async function bsGetPaginated(path: string, maxItems = 2000, maxPages = 50): Promise<any[]> {
  const items: any[] = [];
  let params: Record<string, string> | undefined;
  for (let i = 0; i < maxPages; i++) {
    const data: any = await bsGet(path, params);
    const page: any[] = data.items ?? [];
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
  const data: any = await bsGet(`/addresses/${address}/tokens`, { type: "ERC-20" });
  const items: any[] = data.items ?? [];
  return items.map((it) => {
    const tok = it.token ?? {};
    const decimals = Number(tok.decimals ?? 18) || 18;
    const raw = BigInt(it.value ?? 0);
    const divisor = 10 ** decimals;
    const value = Number(raw) / divisor;
    const rateStr = tok.exchange_rate;
    const rate = rateStr ? Number(rateStr) : null;
    const symbol: string = tok.symbol ?? "?";
    return {
      symbol,
      name: tok.name ?? "",
      decimals,
      contract: tok.address_hash ?? "",
      value,
      exchangeRate: Number.isFinite(rate as number) ? (rate as number) : null,
      usd: tokenToUsd(value, Number.isFinite(rate as number) ? (rate as number) : null, symbol),
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
    const txs = await bsGetPaginated(`/addresses/${address}/transactions`, limit);
    for (const tx of txs) {
      const ts: string = tx.timestamp ?? "";
      const fr: string = (tx.from?.hash ?? "").toLowerCase();
      const to: string = (tx.to?.hash ?? "").toLowerCase();
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
    const tts = await bsGetPaginated(`/addresses/${address}/token-transfers`, limit);
    for (const tt of tts) {
      const ts: string = tt.timestamp ?? "";
      const fr: string = (tt.from?.hash ?? "").toLowerCase();
      const to: string = (tt.to?.hash ?? "").toLowerCase();
      const tok = tt.token ?? {};
      const decimals = Number(tok.decimals ?? 18) || 18;
      const raw = BigInt(tt.total?.value ?? 0);
      const val = Number(raw) / 10 ** decimals;
      const rateStr = tok.exchange_rate;
      const rate = rateStr ? Number(rateStr) : null;
      const symbol: string = tok.symbol ?? "?";
      const usd =
        rate !== null || isStablecoin(symbol, null)
          ? tokenToUsd(val, Number.isFinite(rate as number) ? (rate as number) : null, symbol)
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

export function buildSparkline(history: Transfer[], buckets = 26): number[] {
  // 활동의 cumulative net (USD) 을 시간순으로 24~26 포인트로 압축
  if (history.length === 0) return new Array(buckets).fill(0);
  const sorted = [...history].sort((a, b) =>
    a.timestamp < b.timestamp ? -1 : a.timestamp > b.timestamp ? 1 : 0,
  );
  let cum = 0;
  const points: number[] = [];
  const step = Math.max(1, Math.floor(sorted.length / buckets));
  for (let i = 0; i < sorted.length; i++) {
    const t = sorted[i];
    const sign = t.direction === "in" ? 1 : t.direction === "out" ? -1 : 0;
    cum += sign * (t.usd ?? 0);
    if (i % step === 0) points.push(cum);
  }
  if (points.length < 2) points.push(cum);
  return points;
}
