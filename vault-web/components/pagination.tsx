"use client";

type Props = {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
};

export function Pagination({ page, pageSize, total, onChange }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-end gap-2 mt-3 text-[12px]">
      <button
        type="button"
        onClick={() => onChange(Math.max(0, page - 1))}
        disabled={page === 0}
        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-ink-12 hover:bg-ink-06 ink-60 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        aria-label="이전 페이지"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="12" height="12">
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
      <span
        className="ink-60 px-2 min-w-[60px] text-center"
        style={{ fontFamily: "var(--font-mono)" }}
      >
        {page + 1} / {totalPages}
      </span>
      <button
        type="button"
        onClick={() => onChange(Math.min(totalPages - 1, page + 1))}
        disabled={page >= totalPages - 1}
        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-ink-12 hover:bg-ink-06 ink-60 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        aria-label="다음 페이지"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="12" height="12">
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </button>
    </div>
  );
}
