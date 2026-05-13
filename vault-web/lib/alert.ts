import { activeWallets } from "./projects";
import { getWalletSnapshot } from "./soneium";

export type AlertResult = {
  project: string;
  wallet: string;
  name: string;
  threshold: number;
  current: number;
  triggered: boolean;
  sent: boolean;
  cooldown?: boolean;
  error?: string;
  sendError?: string;
};

const ALERT_EMAIL_TO = (process.env.ALERT_EMAIL_TO ?? "alex@depsell.io").trim();
const RESEND_API_KEY = (process.env.RESEND_API_KEY ?? "").trim();
const RESEND_FROM =
  (process.env.RESEND_FROM ?? "Vault Alert <onboarding@resend.dev>").trim();

type SendResult = { ok: boolean; error?: string };

async function sendEmail(subject: string, body: string): Promise<SendResult> {
  if (!RESEND_API_KEY) {
    console.log(`[ALERT][stdout] ${subject}\n${body}`);
    return { ok: false, error: "RESEND_API_KEY 미설정 (stdout 로그만)" };
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
      const msg = `HTTP ${r.status}: ${t}`;
      console.error(`[ALERT][resend] ${msg}`);
      return { ok: false, error: msg };
    }
    return { ok: true };
  } catch (e) {
    const msg = String(e);
    console.error("[ALERT][resend] failed", e);
    return { ok: false, error: msg };
  }
}

// 단순한 in-memory 쿨다운 — Vercel serverless 라 cold start 시 리셋되지만
// Vercel Cron 이 1시간마다 도는 기본 가정 (Pro+ 면 더 짧게)
// 영구 cooldown 필요하면 Vercel KV / Upstash 필요.
const memCooldown: Map<string, number> = new Map();
const COOLDOWN_MS = Number(process.env.ALERT_COOLDOWN_HOURS ?? "1") * 3600_000;

export async function runAlertCheck(force = false): Promise<AlertResult[]> {
  const out: AlertResult[] = [];
  const wallets = activeWallets();
  for (const { project, wallet } of wallets) {
    const threshold = wallet.alertThresholdUsd;
    if (threshold === null) continue;
    const key = `${project.key}__${wallet.key}`;
    const proj = project.name;
    const wname = wallet.name;

    let snap;
    try {
      snap = await getWalletSnapshot(wallet.address);
    } catch (e) {
      out.push({
        project: project.key,
        wallet: wallet.key,
        name: `${proj} · ${wname}`,
        threshold,
        current: 0,
        triggered: false,
        sent: false,
        error: String(e),
      });
      continue;
    }

    const current = snap.totalUsd;
    if (current >= threshold) {
      memCooldown.delete(key);
      out.push({
        project: project.key,
        wallet: wallet.key,
        name: `${proj} · ${wname}`,
        threshold,
        current,
        triggered: false,
        sent: false,
      });
      continue;
    }

    const lastAlertTs = memCooldown.get(key) ?? 0;
    const now = Date.now();
    if (!force && now - lastAlertTs < COOLDOWN_MS) {
      out.push({
        project: project.key,
        wallet: wallet.key,
        name: `${proj} · ${wname}`,
        threshold,
        current,
        triggered: true,
        sent: false,
        cooldown: true,
      });
      continue;
    }

    const subject = `[${proj}] ${wname} 잔고 $${current.toFixed(2)} (< $${threshold})`;
    const tokenLines =
      snap.tokens
        .map((t) => `  - ${t.symbol}: ${t.value.toFixed(4)} ($${t.usd.toFixed(2)})`)
        .join("\n") || "  (보유 토큰 없음)";
    const body = `Vault 잔고 알림

프로젝트: ${proj}
지갑: ${wname}
주소: ${wallet.address}
설명: ${wallet.description ?? ""}

현재 총 USD: $${current.toFixed(2)}
임계값: $${threshold}
부족분: $${(threshold - current).toFixed(2)}

보유 내역:
  - ETH: ${snap.eth.toFixed(6)} ($${snap.ethUsd.toFixed(2)})
${tokenLines}

탐색기: https://soneium.blockscout.com/address/${wallet.address}
대시보드: ${process.env.NEXT_PUBLIC_BASE_URL ?? ""}/?project=${project.key}&wallet=${wallet.key}

발송 시각: ${new Date().toISOString()}
`;
    const result = await sendEmail(subject, body);
    if (result.ok || !RESEND_API_KEY) memCooldown.set(key, now);
    out.push({
      project: project.key,
      wallet: wallet.key,
      name: `${proj} · ${wname}`,
      threshold,
      current,
      triggered: true,
      sent: result.ok,
      sendError: result.error,
    });
  }
  return out;
}
