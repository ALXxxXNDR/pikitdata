type Props = { points: number[] };

export function Sparkline({ points }: Props) {
  const w = 600;
  const h = 64;
  const pad = 4;
  if (points.length < 2) {
    return (
      <svg className="block w-full h-16" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" />
    );
  }
  const max = Math.max(...points);
  const min = Math.min(...points);
  const span = max - min || 1;
  const step = (w - pad * 2) / (points.length - 1);
  const ys = points.map((v) => h - pad - ((v - min) / span) * (h - pad * 2));
  const d = ys.map((y, i) => `${i === 0 ? "M" : "L"} ${pad + i * step} ${y}`).join(" ");
  const area = `${d} L ${pad + (points.length - 1) * step} ${h} L ${pad} ${h} Z`;
  return (
    <svg
      className="block w-full h-16"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
    >
      <path
        d={area}
        fill="color-mix(in srgb, var(--color-accent) 8%, transparent)"
      />
      <path
        d={d}
        fill="none"
        stroke="var(--color-accent)"
        strokeWidth="1.6"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle
        cx={pad + (points.length - 1) * step}
        cy={ys[ys.length - 1]}
        r="3"
        fill="var(--color-accent)"
      />
    </svg>
  );
}
