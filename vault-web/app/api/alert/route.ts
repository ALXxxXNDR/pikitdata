import { NextResponse } from "next/server";
import { runAlertCheck } from "@/lib/alert";

export const dynamic = "force-dynamic";

function authorized(req: Request): boolean {
  const secret = (process.env.CRON_SECRET ?? "").trim();
  if (!secret) {
    console.error("[/api/alert] CRON_SECRET not set — refusing request");
    return false;
  }
  const auth = req.headers.get("authorization") ?? "";
  return auth === `Bearer ${secret}`;
}

export async function GET(req: Request) {
  if (!authorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  // force 는 prod 비활성 — 로컬 디버깅 전용. 쿨다운 우회로 이메일 폭탄 방지.
  const force =
    process.env.NODE_ENV !== "production" &&
    new URL(req.url).searchParams.get("force") === "1";
  const result = await runAlertCheck(force);
  return NextResponse.json(result);
}

// Vercel Cron 은 POST 도 호출 가능
export const POST = GET;
