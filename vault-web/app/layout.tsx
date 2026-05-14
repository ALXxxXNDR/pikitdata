import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  weight: "400",
  subsets: ["latin"],
  display: "swap",
  preload: true,
  fallback: ["serif"],
});

const BASE_URL = "https://dashboard.despell.io";

export const metadata: Metadata = {
  metadataBase: new URL(BASE_URL),
  title: "DeSpell Vault — 프로젝트 대시보드",
  description: "DeSpell 프로젝트별 운영 지갑 모니터링 (PIKIT · Press A · Pnyx)",
  openGraph: {
    title: "DeSpell Vault",
    description: "Soneium 운영 지갑 모니터링 — PIKIT · Press A · Pnyx",
    url: BASE_URL,
    siteName: "DeSpell Vault",
    locale: "ko_KR",
    type: "website",
    // opengraph-image.tsx 가 자동으로 images 에 등록되므로 명시 불필요
  },
  twitter: {
    card: "summary_large_image",
    title: "DeSpell Vault",
    description: "Soneium 운영 지갑 모니터링 — PIKIT · Press A · Pnyx",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${instrumentSerif.variable}`}
      >
        {children}
      </body>
    </html>
  );
}
