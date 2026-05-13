import { NextResponse } from "next/server";
import { runAlertCheck } from "@/lib/alert";

export const dynamic = "force-dynamic";

function authorized(req: Request): boolean {
  const secret = (process.env.CRON_SECRET ?? "").trim();
  if (!secret) return true; // 시크릿 미설정 시 누구나 호출 가능 (개발용)
  const auth = req.headers.get("authorization") ?? "";
  if (auth === `Bearer ${secret}`) return true;
  const qSecret = new URL(req.url).searchParams.get("secret");
  return qSecret === secret;
}

export async function GET(req: Request) {
  if (!authorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const force = new URL(req.url).searchParams.get("force") === "1";
  const results = await runAlertCheck(force);
  return NextResponse.json({
    ok: true,
    checked: results.length,
    triggered: results.filter((r) => r.triggered).length,
    sent: results.filter((r) => r.sent).length,
    results,
  });
}

// Vercel Cron 은 POST 도 호출 가능
export const POST = GET;
