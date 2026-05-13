"use client";

import { useEffect, useState } from "react";

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function format(d: Date): string {
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

type Props = { serverTimeMs: number };

/**
 * 마지막 데이터 갱신 시각을 yyyy.mm.dd HH:mm:ss 형식으로 표시.
 *
 * serverTimeMs 는 서버 렌더 시각 (Date.now() in page.tsx). router.refresh()
 * 가 일어나면 서버 재렌더 → 새 prop → 자동으로 갱신.
 *
 * 컴포넌트 마운트 후 hydration 시점에 한 번 client now 로 재포맷 (서버/클라
 * 시간대 차이 보정). 그 뒤로는 prop 갱신을 기다림.
 */
export function LiveTimestamp({ serverTimeMs }: Props) {
  const [display, setDisplay] = useState(() => format(new Date(serverTimeMs)));

  useEffect(() => {
    setDisplay(format(new Date(serverTimeMs)));
  }, [serverTimeMs]);

  return (
    <span style={{ fontFamily: "var(--font-mono)" }}>{display}</span>
  );
}
