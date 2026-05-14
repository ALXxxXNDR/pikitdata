"use server";

import { auth } from "@/auth";
import {
  type AlertConfig,
  type AlertDirection,
  setAlertConfig,
} from "@/lib/alert-config";

export type SaveAlertResult = {
  ok: boolean;
  error?: string;
};

export async function saveAlertConfigAction(
  projectKey: string,
  walletKey: string,
  enabled: boolean,
  threshold: number,
  direction: AlertDirection,
): Promise<SaveAlertResult> {
  // 인증 확인 — auth 안 된 호출 거부.
  const session = await auth();
  if (!session?.user?.email) {
    return { ok: false, error: "인증 필요" };
  }

  if (!projectKey || !walletKey) {
    return { ok: false, error: "프로젝트/지갑 키 누락" };
  }
  if (!Number.isFinite(threshold) || threshold < 0) {
    return { ok: false, error: "유효한 임계 금액이 아닙니다" };
  }
  if (direction !== "above" && direction !== "below") {
    return { ok: false, error: "잘못된 방향 값" };
  }

  const config: AlertConfig = {
    enabled,
    threshold,
    direction,
  };

  try {
    await setAlertConfig(projectKey, walletKey, config);
    return { ok: true };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg === "EDGE_CONFIG_NOT_SET" || msg === "EDGE_CONFIG_ID_PARSE_FAILED") {
      return {
        ok: false,
        error:
          "저장소(Vercel Edge Config) 가 아직 연결되지 않았습니다. Vercel 대시보드에서 Edge Config 를 생성하고 EDGE_CONFIG env 를 설정하세요.",
      };
    }
    if (msg === "VERCEL_API_TOKEN_NOT_SET") {
      return {
        ok: false,
        error:
          "쓰기 권한이 설정되지 않았습니다. VERCEL_API_TOKEN env 를 추가하세요.",
      };
    }
    return { ok: false, error: msg };
  }
}
