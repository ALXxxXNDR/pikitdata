/**
 * 사용자 정의 알림 설정 — wallet 단위 on/off + threshold + direction.
 *
 * 저장소: Upstash Redis (Vercel Marketplace 로 1-click 프로비저닝).
 * env 미설정 시: 정적 PROJECTS config 의 alertThresholdUsd 를 fallback 으로 사용.
 *
 * Key 구조 (Hash):
 *   vault:alert:configs
 *     ├── "pikit:revenue"        → {"enabled":false,"threshold":300,"direction":"below"}
 *     ├── "pikit:reward_vault"   → {"enabled":true, "threshold":300,"direction":"below"}
 *     └── "press_a:reward_pool"  → ...
 *
 *   vault:alert:state
 *     └── {project}:{wallet}     → {"lastAlertTs":epoch_ms,"lastTotal":number}
 */

import { Redis } from "@upstash/redis";
import { PROJECTS } from "./projects";

export type AlertDirection = "above" | "below";

export type AlertConfig = {
  enabled: boolean;
  threshold: number;
  direction: AlertDirection;
};

const CONFIGS_KEY = "vault:alert:configs";
const STATE_KEY = "vault:alert:state";

let _redis: Redis | null = null;
let _redisChecked = false;

function getRedis(): Redis | null {
  if (_redisChecked) return _redis;
  _redisChecked = true;
  const url =
    process.env.UPSTASH_REDIS_REST_URL ||
    process.env.KV_REST_API_URL ||
    process.env.KV_URL;
  const token =
    process.env.UPSTASH_REDIS_REST_TOKEN || process.env.KV_REST_API_TOKEN;
  if (!url || !token) {
    _redis = null;
    return null;
  }
  try {
    _redis = new Redis({ url, token });
  } catch {
    _redis = null;
  }
  return _redis;
}

export function isKvConfigured(): boolean {
  return getRedis() !== null;
}

function staticFallback(
  projectKey: string,
  walletKey: string,
): AlertConfig {
  const proj = PROJECTS.find((p) => p.key === projectKey);
  const wal = proj?.wallets.find((w) => w.key === walletKey);
  const threshold = wal?.alertThresholdUsd ?? 300;
  return {
    enabled: wal?.alertThresholdUsd != null, // 정적 임계 설정된 wallet 만 기본 enabled
    threshold,
    direction: "below",
  };
}

function configKey(projectKey: string, walletKey: string): string {
  return `${projectKey}:${walletKey}`;
}

function parseConfig(raw: unknown): AlertConfig | null {
  if (raw == null) return null;
  let obj: unknown = raw;
  if (typeof raw === "string") {
    try {
      obj = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (typeof obj !== "object" || obj === null) return null;
  const o = obj as Record<string, unknown>;
  const threshold = Number(o.threshold);
  const direction = o.direction === "above" ? "above" : "below";
  const enabled = Boolean(o.enabled);
  if (!Number.isFinite(threshold) || threshold < 0) return null;
  return { enabled, threshold, direction };
}

export async function getAlertConfig(
  projectKey: string,
  walletKey: string,
): Promise<AlertConfig> {
  const r = getRedis();
  if (!r) return staticFallback(projectKey, walletKey);
  try {
    const raw = await r.hget(CONFIGS_KEY, configKey(projectKey, walletKey));
    const parsed = parseConfig(raw);
    return parsed ?? staticFallback(projectKey, walletKey);
  } catch {
    return staticFallback(projectKey, walletKey);
  }
}

export async function setAlertConfig(
  projectKey: string,
  walletKey: string,
  config: AlertConfig,
): Promise<void> {
  const r = getRedis();
  if (!r) {
    throw new Error("KV_NOT_CONFIGURED");
  }
  await r.hset(CONFIGS_KEY, {
    [configKey(projectKey, walletKey)]: JSON.stringify(config),
  });
}

export async function getAllAlertConfigs(): Promise<
  Record<string, AlertConfig>
> {
  const r = getRedis();
  if (!r) {
    // KV 없을 때: 정적 fallback 으로 모든 wallet 생성
    const out: Record<string, AlertConfig> = {};
    for (const p of PROJECTS) {
      if (p.comingSoon) continue;
      for (const w of p.wallets) {
        if (!w.address) continue;
        out[configKey(p.key, w.key)] = staticFallback(p.key, w.key);
      }
    }
    return out;
  }
  try {
    const data = (await r.hgetall(CONFIGS_KEY)) as Record<string, unknown> | null;
    if (!data) return {};
    const out: Record<string, AlertConfig> = {};
    for (const [k, v] of Object.entries(data)) {
      const parsed = parseConfig(v);
      if (parsed) out[k] = parsed;
    }
    return out;
  } catch {
    return {};
  }
}

// ─────────────────────────────────────────────────────────────────
// 알림 상태 (쿨다운용)
// ─────────────────────────────────────────────────────────────────

export type AlertState = {
  lastAlertTs: number;
  lastTotal: number;
};

export async function getAlertState(
  projectKey: string,
  walletKey: string,
): Promise<AlertState | null> {
  const r = getRedis();
  if (!r) return null;
  try {
    const raw = await r.hget(STATE_KEY, configKey(projectKey, walletKey));
    if (raw == null) return null;
    const obj = typeof raw === "string" ? JSON.parse(raw) : (raw as unknown);
    if (typeof obj === "object" && obj !== null) {
      const o = obj as Record<string, unknown>;
      return {
        lastAlertTs: Number(o.lastAlertTs) || 0,
        lastTotal: Number(o.lastTotal) || 0,
      };
    }
    return null;
  } catch {
    return null;
  }
}

export async function setAlertState(
  projectKey: string,
  walletKey: string,
  state: AlertState,
): Promise<void> {
  const r = getRedis();
  if (!r) return;
  try {
    await r.hset(STATE_KEY, {
      [configKey(projectKey, walletKey)]: JSON.stringify(state),
    });
  } catch {
    // best-effort
  }
}

export async function clearAlertState(
  projectKey: string,
  walletKey: string,
): Promise<void> {
  const r = getRedis();
  if (!r) return;
  try {
    await r.hdel(STATE_KEY, configKey(projectKey, walletKey));
  } catch {
    // best-effort
  }
}
