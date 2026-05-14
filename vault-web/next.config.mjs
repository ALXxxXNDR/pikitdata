import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Content Security Policy — Next.js + Tailwind v4 + React 19 가 inline script/style 를
// 주입하므로 'unsafe-inline' 허용. connect-src 는 실제 외부 API 만.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https:",
  "font-src 'self' data:",
  "connect-src 'self' https://api.resend.com https://api.vercel.com https://soneium.blockscout.com https://api.coingecko.com https://rpc.soneium.org https://soneium.drpc.org https://*.gateway.tenderly.co",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: __dirname,
  // OG 이미지 생성 시 폰트 파일을 deployment 에 명시적 include.
  outputFileTracingIncludes: {
    "/opengraph-image": ["./app/_assets/**/*"],
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
          { key: "Content-Security-Policy", value: CSP },
        ],
      },
    ];
  },
};

export default nextConfig;
