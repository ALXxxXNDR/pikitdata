import type { WalletConfig } from "@/lib/types";

function shortAddr(a: string): string {
  if (!a) return "";
  if (a.length < 12) return a;
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}

type Props = {
  wallets: WalletConfig[];
};

export function TrackingRow({ wallets }: Props) {
  const active = wallets.filter((w) => w.address);
  if (active.length === 0) return null;

  return (
    <div className="flex items-center gap-2 flex-wrap text-[11px] ink-45 mt-4">
      <span
        className="uppercase tracking-[0.12em]"
        style={{ fontSize: 10 }}
      >
        Tracking
      </span>
      {active.map((w, i) => (
        <span key={w.key} className="flex items-center gap-2">
          {i > 0 && <span className="ink-25">·</span>}
          <a
            href={`https://soneium.blockscout.com/address/${w.address}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 hover:underline underline-offset-2"
            style={{ color: "color-mix(in srgb, var(--color-ink) 70%, transparent)" }}
            title="Blockscout 에서 열기"
          >
            <span>{w.name}</span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                color:
                  "color-mix(in srgb, var(--color-ink) 45%, transparent)",
              }}
            >
              {shortAddr(w.address)}
            </span>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              width="9"
              height="9"
              style={{
                color:
                  "color-mix(in srgb, var(--color-ink) 35%, transparent)",
              }}
            >
              <path d="M7 17 17 7" />
              <path d="M7 7h10v10" />
            </svg>
          </a>
        </span>
      ))}
    </div>
  );
}
