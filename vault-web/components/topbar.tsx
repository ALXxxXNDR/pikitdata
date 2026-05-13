export function Topbar() {
  return (
    <header className="flex items-center justify-between gap-6 py-2 pb-7 border-b border-ink-12">
      <div className="flex items-center gap-2.5 text-[15px] font-semibold">
        <div
          className="grid place-items-center w-[22px] h-[22px] rounded-md text-[12px] font-semibold"
          style={{
            background: "var(--color-ink)",
            color: "var(--color-bg)",
            fontFamily: "var(--font-mono)",
            letterSpacing: "-0.04em",
          }}
        >
          V
        </div>
        Vault Stack{" "}
        <small className="ink-45 font-normal ml-1">· 멀티 프로젝트 지갑 대시보드</small>
      </div>
      <div className="flex items-center gap-2.5">
        <button
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded-full text-[13px] border border-ink-12 hover:bg-ink-06"
        >
          <span
            className="block w-1.5 h-1.5 rounded-full"
            style={{ background: "var(--color-accent)" }}
          />
          실시간 동기화
        </button>
        <button className="inline-flex items-center gap-2 px-3.5 py-2 rounded-full text-[13px] border border-ink-12 hover:bg-ink-06">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            className="w-3.5 h-3.5"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          검색
        </button>
      </div>
    </header>
  );
}
