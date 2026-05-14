/**
 * 사용자 정의 알림 설정 — Vercel Edge Config 백엔드.
 *
 * 읽기: @vercel/edge-config (EDGE_CONFIG env 자동 감지, 매우 빠름)
 * 쓰기: Vercel REST API PATCH (VERCEL_API_TOKEN 필요, 전파 ~30초)
 *
 * 키 구조 (flat — Edge Config 는 키에 alphanumeric/_/-/ 만 허용):
 *   "alert_cfg_pikit_revenue"      → AlertConfig
 *   "alert_cfg_pikit_reward_vault" → ...
 *   "alert_state_pikit_revenue"    → AlertState (cooldown 추적)
 *
 * env 미설정 시: lib/projects.ts 의 alertThresholdUsd 정적 fallback.
 */

import { get, has } from "@vercel/edge-config";
import { PROJECTS } from "./projects";

export type AlertDirection = "above" | "below";

export type AlertConfig = {
  enabled: boolean;
  threshold: number;
  direction: AlertDirection;
};

export type AlertState = {
  lastAlertTs: number;
  lastTotal: number;
};

const CFG_PREFIX = "alert_cfg_";
const STATE_PREFIX = "alert_state_";

// ─────────────────────────────────────────────────────────────────
// 설정 감지
// ─────────────────────────────────────────────────────────────────

function edgeConfigUrl(): string | undefined {
  return process.env.EDGE_CONFIG?.trim();
}

export function isKvConfigured(): boolean {
  return !!edgeConfigUrl();
}

function extractEdgeConfigId(url: string): string | null {
  const m = url.match(/ecfg_[A-Za-z0-9]+/);
  return m ? m[0] : null;
}

function vercelApiToken(): string | null {
  const t = process.env.VERCEL_API_TOKEN?.trim();
  return t ? t : null;
}

function vercelTeamId(): string | null {
  const t = process.env.VERCEL_TEAM_ID?.trim();
  return t ? t : null;
}

// ─────────────────────────────────────────────────────────────────
// 키 헬퍼
// ─────────────────────────────────────────────────────────────────

function cfgKey(projectKey: string, walletKey: string): string {
  return `${CFG_PREFIX}${projectKey}_${walletKey}`;
}

function stateKey(projectKey: string, walletKey: string): string {
  return `${STATE_PREFIX}${projectKey}_${walletKey}`;
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

function parseState(raw: unknown): AlertState | null {
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
  return {
    lastAlertTs: Number(o.lastAlertTs) || 0,
    lastTotal: Number(o.lastTotal) || 0,
  };
}

function staticFallback(
  projectKey: string,
  walletKey: string,
): AlertConfig {
  const proj = PROJECTS.find((p) => p.key === projectKey);
  const wal = proj?.wallets.find((w) => w.key === walletKey);
  const threshold = wal?.alertThresholdUsd ?? 300;
  return {
    enabled: wal?.alertThresholdUsd != null,
    threshold,
    direction: "below",
  };
}

// ─────────────────────────────────────────────────────────────────
// 읽기 (Edge Config)
// ─────────────────────────────────────────────────────────────────

export async function getAlertConfig(
  projectKey: string,
  walletKey: string,
): Promise<AlertConfig> {
  if (!isKvConfigured()) return staticFallback(projectKey, walletKey);
  try {
    const raw = await get(cfgKey(projectKey, walletKey));
    return parseConfig(raw) ?? staticFallback(projectKey, walletKey);
  } catch {
    return staticFallback(projectKey, walletKey);
  }
}

export async function getAlertState(
  projectKey: string,
  walletKey: string,
): Promise<AlertState | null> {
  if (!isKvConfigured()) return null;
  try {
    const raw = await get(stateKey(projectKey, walletKey));
    return parseState(raw);
  } catch {
    return null;
  }
}

// ─────────────────────────────────────────────────────────────────
// 쓰기 (Vercel REST API)
// ─────────────────────────────────────────────────────────────────

type EdgeItem = {
  operation: "create" | "update" | "upsert" | "delete";
  key: string;
  value?: unknown;
};

async function edgePatch(items: EdgeItem[]): Promise<void> {
  const url = edgeConfigUrl();
  if (!url) throw new Error("EDGE_CONFIG_NOT_SET");
  const token = vercelApiToken();
  if (!token) throw new Error("VERCEL_API_TOKEN_NOT_SET");
  const id = extractEdgeConfigId(url);
  if (!id) throw new Error("EDGE_CONFIG_ID_PARSE_FAILED");

  const teamId = vercelTeamId();
  const endpoint = `https://api.vercel.com/v1/edge-config/${id}/items${teamId ? `?teamId=${teamId}` : ""}`;

  const r = await fetch(endpoint, {
    method: "PATCH",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ items }),
  });
  if (!r.ok) {
    const t = await r.text();
    console.error(`[edgePatch] Vercel API ${r.status}`, t);
    throw new Error("EDGE_PATCH_FAILED");
  }
}

export async function setAlertConfig(
  projectKey: string,
  walletKey: string,
  config: AlertConfig,
): Promise<void> {
  await edgePatch([
    { operation: "upsert", key: cfgKey(projectKey, walletKey), value: config },
  ]);
}

export async function setAlertState(
  projectKey: string,
  walletKey: string,
  state: AlertState,
): Promise<void> {
  try {
    await edgePatch([
      { operation: "upsert", key: stateKey(projectKey, walletKey), value: state },
    ]);
  } catch {
    // state 쓰기 실패는 best-effort (cooldown 만 영향)
  }
}

export async function clearAlertState(
  projectKey: string,
  walletKey: string,
): Promise<void> {
  try {
    if (await has(stateKey(projectKey, walletKey))) {
      await edgePatch([
        { operation: "delete", key: stateKey(projectKey, walletKey) },
      ]);
    }
  } catch {
    // best-effort
  }
}
