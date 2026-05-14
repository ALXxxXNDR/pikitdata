import { ImageResponse } from "next/og";

// Next.js 가 자동 인식 — /opengraph-image 라우트 + layout 메타에 자동 연결.
export const runtime = "edge";
export const alt = "DeSpell Vault — Soneium 운영 지갑 모니터링";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Google Fonts API 에서 필요한 글자만 subset fetch.
// 옛 UA 를 보내야 woff2 대신 ttf 응답 — ImageResponse 는 ttf/otf 만 지원.
async function loadGoogleFont(
  family: string,
  weight: number,
  text: string,
): Promise<ArrayBuffer> {
  const url = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(
    family,
  )}:wght@${weight}&text=${encodeURIComponent(text)}`;
  const css = await fetch(url, {
    headers: {
      // IE6 UA → ttf 응답
      "user-agent":
        "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1)",
    },
  }).then((r) => r.text());
  const match = css.match(
    /src:\s*url\(([^)]+)\)\s*format\('truetype'\)/,
  );
  if (!match) throw new Error(`Font URL not found for ${family}`);
  const fontRes = await fetch(match[1]);
  if (!fontRes.ok) throw new Error(`Font fetch failed: ${family}`);
  return fontRes.arrayBuffer();
}

const ORIGIN = "https://dashboard.despell.io";

export default async function OgImage() {
  // 카드에 등장하는 모든 글자 (한글 + 영문 + 기호) — Noto Sans KR 로 subset
  const sansText =
    "DeSpellVaultSoneium운영지갑모니터링PIKITPressAPnyxdashboard.despell.ioL2·•";
  // 영문 큰 제목 — Instrument Serif
  const serifText = "DeSpell Vault";

  const [serifFont, sansFont] = await Promise.all([
    loadGoogleFont("Instrument Serif", 400, serifText),
    loadGoogleFont("Noto Sans KR", 500, sansText),
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
          fontFamily: "NotoSansKR",
        }}
      >
        {/* 상단: 로고 + 우상단 L2 표시 */}
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
                borderRadius: 10,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                overflow: "hidden",
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${ORIGIN}/logos/despell.png`}
                width={30}
                height={30}
                alt=""
              />
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
          name: "NotoSansKR",
          data: sansFont,
          weight: 500,
          style: "normal",
        },
      ],
    },
  );
}
