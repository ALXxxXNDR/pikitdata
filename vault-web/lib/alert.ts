/**
 * 통합 알림 — 매일 cron 이 모든 활성 wallet 의 사용자 정의 조건을 확인하고
 * 트리거된 wallet 만 한 통의 메일로 묶어 발송.
 *
 * 흐름:
 *   1) activeWallets() → 각 (project, wallet)
 *   2) getAlertConfig() → KV (또는 정적 fallback) 에서 조건 조회
 *   3) enabled 면 현재 balance vs threshold + direction 비교
 *   4) 트리거된 항목 수집
 *   5) 0건이면 메일 생략. 1건 이상이면 단일 요약 메일.
 */

import {
  type AlertConfig,
  getAlertConfig,
  getAlertState,
  setAlertState,
} from "./alert-config";
import { activeWallets } from "./projects";
import type { ProjectConfig, WalletConfig } from "./types";
import { getWalletSnapshot } from "./soneium";

const ALERT_EMAIL_TO = (process.env.ALERT_EMAIL_TO ?? "alex@depsell.io").trim();
const RESEND_API_KEY = (process.env.RESEND_API_KEY ?? "").trim();
const RESEND_FROM =
  (process.env.RESEND_FROM ?? "Vault Alert <onboarding@resend.dev>").trim();
const COOLDOWN_MS = Number(process.env.ALERT_COOLDOWN_HOURS ?? "20") * 3600_000;

export type AlertRow = {
  projectKey: string;
  walletKey: string;
  projectName: string;
  walletName: string;
  address: string;
  config: AlertConfig;
  currentUsd: number;
  triggered: boolean;
  inCooldown: boolean;
  error?: string;
};

export type AlertResult = {
  ok: boolean;
  checkedCount: number;
  enabledCount: number;
  triggeredCount: number;
  sent: boolean;
  sendError?: string;
  rows: AlertRow[];
};

function evaluate(config: AlertConfig, currentUsd: number): boolean {
  if (!config.enabled) return false;
  if (!Number.isFinite(currentUsd)) return false;
  if (config.direction === "below") return currentUsd < config.threshold;
  return currentUsd > config.threshold;
}

function fmtUsd(n: number): string {
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function buildSubject(rows: AlertRow[]): string {
  const triggered = rows.filter((r) => r.triggered);
  if (triggered.length === 0) return "[DeSpell Vault] 알림 없음";
  if (triggered.length === 1) {
    const r = triggered[0];
    return `[DeSpell Vault] ${r.projectName} · ${r.walletName} ${fmtUsd(r.currentUsd)}`;
  }
  return `[DeSpell Vault] 알림 ${triggered.length}건 — 잔고 조건 충족`;
}

function buildBody(rows: AlertRow[], baseUrl: string): string {
  const triggered = rows.filter((r) => r.triggered);
  const lines: string[] = [];
  lines.push("DeSpell Vault 일일 알림");
  lines.push("");
  if (triggered.length === 0) {
    lines.push("오늘 트리거된 조건이 없습니다.");
  } else {
    lines.push(`아래 ${triggered.length}건의 잔고 조건이 충족되었습니다:`);
    lines.push("");
    for (const r of triggered) {
      const cond =
        r.config.direction === "below"
          ? `< ${fmtUsd(r.config.threshold)}`
          : `> ${fmtUsd(r.config.threshold)}`;
      const phrase =
        r.config.direction === "below"
          ? `${r.projectName} 의 ${r.walletName} 잔고가 ${fmtUsd(r.currentUsd)} (임계 ${fmtUsd(r.config.threshold)} 아래)`
          : `${r.projectName} 의 ${r.walletName} 잔고가 ${fmtUsd(r.currentUsd)} (임계 ${fmtUsd(r.config.threshold)} 이상)`;
      lines.push(`• ${phrase}`);
      lines.push(`  조건: ${cond} · 주소: ${r.address}`);
      lines.push(
        `  대시보드: ${baseUrl}/?project=${r.projectKey}&wallet=${r.walletKey}`,
      );
      lines.push("");
    }
  }
  lines.push("");
  lines.push(`발송 시각: ${new Date().toISOString()}`);
  return lines.join("\n");
}

async function sendEmail(
  subject: string,
  body: string,
): Promise<{ ok: boolean; error?: string }> {
  if (!RESEND_API_KEY) {
    if (process.env.NODE_ENV === "production") {
      console.error(
        "[ALERT] RESEND_API_KEY missing in production — alert dropped",
      );
      return { ok: false, error: "RESEND_API_KEY 미설정 (production)" };
    }
    // dev: 본문은 로깅하지 않음 (지갑 잔고 leak 방지) — 제목만.
    console.log(`[ALERT][dev] would send: ${subject}`);
    void body;
    return { ok: false, error: "RESEND_API_KEY 미설정 (dev — 제목만 stdout)" };
  }
  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${RESEND_API_KEY}`,
      },
      body: JSON.stringify({
        from: RESEND_FROM,
        to: ALERT_EMAIL_TO,
        subject,
        text: body,
      }),
    });
    if (!r.ok) {
      const t = await r.text();
      return { ok: false, error: `HTTP ${r.status}: ${t}` };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function runAlertCheck(force = false): Promise<AlertResult> {
  const wallets = activeWallets();
  const rows: AlertRow[] = [];
  const now = Date.now();

  for (const { project, wallet } of wallets) {
    const config = await getAlertConfig(project.key, wallet.key);
    let currentUsd = 0;
    let err: string | undefined;
    try {
      const snap = await getWalletSnapshot(wallet.address);
      currentUsd = snap.totalUsd;
    } catch (e) {
      err = String(e);
    }
    const meetsCond = err == null && evaluate(config, currentUsd);

    // cooldown check (KV 에 저장된 last 알림 시각 기준)
    let inCooldown = false;
    if (meetsCond && !force) {
      const state = await getAlertState(project.key, wallet.key);
      if (state && now - state.lastAlertTs < COOLDOWN_MS) {
        inCooldown = true;
      }
    }

    rows.push({
      projectKey: project.key,
      walletKey: wallet.key,
      projectName: project.name,
      walletName: wallet.name,
      address: wallet.address,
      config,
      currentUsd,
      triggered: meetsCond && !inCooldown,
      inCooldown,
      error: err,
    });
  }

  const triggeredRows = rows.filter((r) => r.triggered);
  const enabledCount = rows.filter((r) => r.config.enabled).length;

  if (triggeredRows.length === 0) {
    return {
      ok: true,
      checkedCount: rows.length,
      enabledCount,
      triggeredCount: 0,
      sent: false,
      rows,
    };
  }

  const baseUrl = (process.env.NEXT_PUBLIC_BASE_URL ?? "").replace(/\/$/, "");
  const subject = buildSubject(rows);
  const body = buildBody(rows, baseUrl);
  const sendResult = await sendEmail(subject, body);

  // 상태 업데이트 — 메일 발송 성공 시 (또는 SMTP 미설정 stdout 으로도 성공으로 간주)
  const succeeded = sendResult.ok || !RESEND_API_KEY;
  if (succeeded) {
    for (const r of triggeredRows) {
      await setAlertState(r.projectKey, r.walletKey, {
        lastAlertTs: now,
        lastTotal: r.currentUsd,
      });
    }
  }

  return {
    ok: true,
    checkedCount: rows.length,
    enabledCount,
    triggeredCount: triggeredRows.length,
    sent: sendResult.ok,
    sendError: sendResult.error,
    rows,
  };
}
