import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

// Next.js 가 자동 인식 — /opengraph-image 라우트 + layout 메타에 자동 연결.
// nodejs runtime — edge 의 1MB 함수 한도(Hobby) 회피. 폰트 사이즈 ~4MB.
// dynamic — 빌드 prerender 단계 회피 (run-time 에 매 요청마다 생성, 캐시 적용).
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const alt = "DeSpell Vault — Soneium 운영 지갑 모니터링";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// 폰트 파일은 next.config.mjs 의 outputFileTracingIncludes 로 deployment 에 포함됨.

export default async function OgImage() {
  // path resolve 는 함수 내부에서 — turbopack 빌드 시 top-level evaluate 회피.
  const serifFontPath = fileURLToPath(
    new URL("./_assets/InstrumentSerif-Regular.ttf", import.meta.url),
  );
  const sansFontPath = fileURLToPath(
    new URL("./_assets/PretendardJP-Medium.otf", import.meta.url),
  );
  const [serifFont, sansFont] = await Promise.all([
    readFile(serifFontPath),
    readFile(sansFontPath),
  ]);

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "#F4F3EE",
          color: "#0E0E0C",
          padding: 80,
          display: "flex",
          flexDirection: "column",
          fontFamily: "Pretendard",
        }}
      >
        {/* 상단: 로고 (inline 박스) + 우상단 L2 */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            width: "100%",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div
              style={{
                width: 44,
                height: 44,
                background: "#0E0E0C",
                color: "#F4F3EE",
                borderRadius: 10,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 22,
                fontWeight: 600,
                letterSpacing: "-0.02em",
              }}
            >
              D
            </div>
            <span
              style={{
                fontSize: 26,
                fontWeight: 500,
                letterSpacing: "-0.01em",
              }}
            >
              DeSpell
            </span>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              color: "rgba(14, 14, 12, 0.55)",
              fontSize: 20,
            }}
          >
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: 8,
                background: "#3B5BFD",
              }}
            />
            <span>Soneium · L2</span>
          </div>
        </div>

        {/* 가운데: 큰 제목 + 부제 */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            margin: "auto 0",
          }}
        >
          <div
            style={{
              fontFamily: "InstrumentSerif",
              fontSize: 152,
              letterSpacing: "-0.035em",
              lineHeight: 0.95,
              color: "#0E0E0C",
              display: "flex",
            }}
          >
            DeSpell Vault
          </div>
          <div
            style={{
              marginTop: 32,
              fontSize: 36,
              color: "rgba(14, 14, 12, 0.62)",
              letterSpacing: "-0.005em",
              display: "flex",
            }}
          >
            Soneium 운영 지갑 모니터링
          </div>
          <div
            style={{
              marginTop: 12,
              fontSize: 24,
              color: "rgba(14, 14, 12, 0.42)",
              letterSpacing: "0.02em",
              display: "flex",
            }}
          >
            PIKIT · Press A · Pnyx
          </div>
        </div>

        {/* 하단 우측: 도메인 + indigo dot */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
            gap: 12,
          }}
        >
          <span
            style={{
              fontSize: 22,
              color: "rgba(14, 14, 12, 0.6)",
              letterSpacing: "0.01em",
            }}
          >
            dashboard.despell.io
          </span>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: 8,
              background: "#3B5BFD",
            }}
          />
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        {
          name: "InstrumentSerif",
          data: serifFont,
          weight: 400,
          style: "normal",
        },
        {
          name: "Pretendard",
          data: sansFont,
          weight: 500,
          style: "normal",
        },
      ],
    },
  );
}
