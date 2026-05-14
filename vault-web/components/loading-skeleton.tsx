import Link from "next/link";
import type { ProjectConfig, WalletConfig } from "@/lib/types";

/**
 * 페이지 전환 시 server component fetch 동안 표시되는 skeleton 모음.
 * Suspense fallback 으로 사용. 즉시 가용한 정보 (PROJECTS config 기반의
 * wallet 이름/주소, 라벨 등) 는 그대로 노출하고, 외부 데이터 의존 부분만
 * `filter: blur` + 중앙 spinner 로 처리.
 */

function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--color-accent)"
      strokeWidth="2.4"
      strokeLinecap="round"
      className="spin-icon"
      width={size}
      height={size}
      aria-hidden="true"
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}

function LoadingBadge() {
  return (
    <div
      className="flex items-center gap-2 text-[12.5px] bg-white border border-ink-12 rounded-full px-3 py-1.5 ink-60"
      style={{
        boxShadow:
          "0 4px 14px -6px color-mix(in srgb, var(--color-ink) 14%, transparent)",
      }}
    >
      <Spinner size={13} />
      <span>불러오는 중</span>
    </div>
  );
}

function MetricSkeleton() {
  return (
    <div
      className="bg-white border border-ink-12 rounded-[18px] p-6 relative overflow-hidden"
      style={{ minHeight: 140 }}
    >
      <div
        style={{ filter: "blur(6px)", opacity: 0.32, pointerEvents: "none" }}
      >
        <div className="text-[12px] ink-45 uppercase tracking-[0.12em]">
          불러오는 중
        </div>
        <div
          className="text-[32px] mt-3"
          style={{
            fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`,
            letterSpacing: "-0.02em",
          }}
        >
          $0,000.00
        </div>
        <div
          className="ink-45 text-[12px] mt-1"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          0건
        </div>
      </div>
    </div>
  );
}

function CardSkeleton({
  minHeight = 260,
  title,
}: {
  minHeight?: number;
  title?: string;
}) {
  return (
    <div
      className="bg-white border border-ink-12 rounded-[18px] p-7 relative overflow-hidden"
      style={{ minHeight }}
    >
      <div
        style={{ filter: "blur(8px)", opacity: 0.3, pointerEvents: "none" }}
      >
        {title && (
          <div
            className="m-0 text-[26px]"
            style={{
              fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`,
              letterSpacing: "-0.01em",
            }}
          >
            {title}
          </div>
        )}
        <div className="mt-4 flex flex-col gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="flex items-center justify-between py-1"
              style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}
            >
              <span>0xaaaa…bbbb</span>
              <span>$00,000.00</span>
            </div>
          ))}
        </div>
      </div>
      <div className="absolute inset-0 grid place-items-center pointer-events-none">
        <LoadingBadge />
      </div>
    </div>
  );
}

export function WalletDetailSkeleton({
  project,
  wallet,
}: {
  project: ProjectConfig;
  wallet: WalletConfig;
}) {
  return (
    <>
      {/* 헤더 — wallet 메타는 즉시 표시 가능 (PROJECTS config). 알림 버튼은
          alertConfig fetch 가 끝나야 정확해서 일단 placeholder 로. */}
      <div className="mt-3 flex items-center gap-3 flex-wrap">
        <Link
          href={`/?project=${project.key}`}
          className="inline-flex items-center gap-1.5 text-[13px] px-3 py-1.5 rounded-full border border-ink-12 hover:bg-ink-06"
        >
          ← 프로젝트
        </Link>
        <div
          className="text-[13px] ink-60 flex-1 min-w-0 truncate"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          {wallet.address}
        </div>
        <button
          type="button"
          disabled
          aria-busy="true"
          className="inline-flex items-center gap-2 pl-2.5 pr-3.5 py-1.5 rounded-full text-[12.5px] border border-ink-12 ink-45 cursor-default"
          style={{ opacity: 0.65 }}
        >
          <Spinner size={12} />
          알림 설정
        </button>
      </div>

      <h2
        className="mt-4 text-[40px]"
        style={{
          fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`,
          letterSpacing: "-0.02em",
        }}
      >
        {wallet.name}
      </h2>
      <p className="ink-60 text-[14px] mt-1">{wallet.description}</p>

      <div className="mt-5 flex items-center gap-2 ink-60 text-[13px]">
        <Spinner size={14} />
        <span>잔고 · 거래 내역 불러오는 중…</span>
      </div>

      <section
        className="grid gap-6 mt-4"
        style={{ gridTemplateColumns: "repeat(4, 1fr)" }}
      >
        {[1, 2, 3, 4].map((i) => (
          <MetricSkeleton key={i} />
        ))}
      </section>

      <section
        className="mt-6 grid gap-6"
        style={{ gridTemplateColumns: "1.4fr 1fr" }}
      >
        <CardSkeleton title="카운터파티" minHeight={460} />
        <CardSkeleton title="보유 토큰" minHeight={460} />
      </section>

      <div className="mt-6">
        <CardSkeleton title="최근 활동" minHeight={360} />
      </div>
    </>
  );
}

export function ProjectOverviewSkeleton({
  project,
}: {
  project: ProjectConfig;
}) {
  return (
    <>
      {/* Hero — 총 USD + sparkline. fetch 의존이라 통째로 blur. */}
      <section className="mt-3">
        <div
          className="bg-white border border-ink-12 rounded-[18px] p-8 relative overflow-hidden"
          style={{ minHeight: 280 }}
        >
          <div
            style={{
              filter: "blur(10px)",
              opacity: 0.28,
              pointerEvents: "none",
            }}
          >
            <div className="text-[12px] ink-45 uppercase tracking-[0.12em]">
              총 자산
            </div>
            <div
              className="text-[68px] mt-3"
              style={{
                fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`,
                letterSpacing: "-0.025em",
                lineHeight: 1,
              }}
            >
              $00,000,000.00
            </div>
            <div
              className="mt-6 h-[80px] rounded-md"
              style={{
                background:
                  "color-mix(in srgb, var(--color-accent) 8%, transparent)",
              }}
            />
          </div>
          <div className="absolute inset-0 grid place-items-center pointer-events-none">
            <LoadingBadge />
          </div>
        </div>
      </section>

      <section
        className="grid gap-6 mt-6"
        style={{ gridTemplateColumns: "1.6fr 1fr" }}
      >
        {/* Contract 표 — row 는 즉시, 잔액만 blur */}
        <div className="bg-white border border-ink-12 rounded-[18px] p-7">
          <div className="flex items-center justify-between mb-5">
            <h2
              className="m-0 text-[26px]"
              style={{
                fontFamily: `var(--font-instrument-serif), "Instrument Serif", serif`,
                letterSpacing: "-0.01em",
              }}
            >
              Contract
            </h2>
            <div className="flex items-center gap-2 text-[12.5px] ink-60">
              <Spinner size={13} />
              <span>잔액 불러오는 중…</span>
            </div>
          </div>
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr>
                <th className="text-left font-normal ink-45 text-[11.5px] uppercase tracking-[0.1em] pb-3 px-2.5 border-b border-ink-06">
                  라벨 / 주소
                </th>
                <th className="text-left font-normal ink-45 text-[11.5px] uppercase tracking-[0.1em] pb-3 px-2.5 border-b border-ink-06">
                  유형
                </th>
                <th className="text-right font-normal ink-45 text-[11.5px] uppercase tracking-[0.1em] pb-3 px-2.5 border-b border-ink-06">
                  잔액
                </th>
                <th className="text-right font-normal ink-45 text-[11.5px] uppercase tracking-[0.1em] pb-3 px-2.5 border-b border-ink-06">
                  상세
                </th>
              </tr>
            </thead>
            <tbody>
              {project.wallets.map((w) => (
                <tr key={w.key}>
                  <td className="py-3.5 px-2.5 border-b border-ink-06 align-middle">
                    <div className="font-medium">{w.name}</div>
                    <div
                      className="ink-45"
                      style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}
                    >
                      {w.address
                        ? `${w.address.slice(0, 6)}…${w.address.slice(-4)}`
                        : "—"}
                    </div>
                  </td>
                  <td className="py-3.5 px-2.5 border-b border-ink-06 align-middle">
                    <span
                      className="inline-flex items-center px-2.5 py-1 rounded-md text-[12px] font-medium"
                      style={{
                        background:
                          w.kind === "revenue"
                            ? "var(--color-accent)"
                            : "var(--color-ink)",
                        color: "var(--color-surface)",
                        letterSpacing: "-0.005em",
                      }}
                    >
                      {w.kind === "revenue" ? "운영 수익" : "리워드"}
                    </span>
                  </td>
                  <td
                    className="py-3.5 px-2.5 border-b border-ink-06 align-middle text-right"
                    style={{ fontFamily: "var(--font-mono)" }}
                  >
                    <span
                      style={{
                        filter: "blur(5px)",
                        opacity: 0.4,
                        display: "inline-block",
                      }}
                    >
                      $00,000.00
                    </span>
                  </td>
                  <td className="py-3.5 px-2.5 border-b border-ink-06 align-middle text-right">
                    <span className="text-[12px] ink-45">—</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <CardSkeleton title="자산" minHeight={460} />
      </section>

      <div className="mt-6">
        <CardSkeleton title="최근 활동" minHeight={360} />
      </div>
    </>
  );
}
