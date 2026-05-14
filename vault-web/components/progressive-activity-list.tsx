"use client";

import { useEffect, useState, useTransition } from "react";
import { ActivityList } from "./activity-list";
import type { Transfer } from "@/lib/types";

/**
 * Two-phase activity feed.
 *  - 서버가 recent (20건) 만 await 해서 페이지 즉시 painting
 *  - 서버가 full (500건) 은 promise 로 전달 — client 의 useEffect 가 wait
 *  - full 도착하면 startTransition 으로 부드럽게 swap
 *
 * 사용자 인지: "활동 첫 페이지" 가 거의 즉시 보임 → 페이지 painted 시점이
 *           full fetch wall-time 만큼 단축됨 (보통 5-10초 → 100ms 수준).
 */
export function ProgressiveActivityList({
  recent,
  fullPromise,
}: {
  recent: Transfer[];
  fullPromise: Promise<Transfer[]>;
}) {
  const [items, setItems] = useState(recent);
  const [, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;
    fullPromise.then((full) => {
      if (cancelled) return;
      // recent 보다 작으면 (cache 깨짐/error) 그대로 둠.
      if (full.length < recent.length) return;
      startTransition(() => setItems(full));
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullPromise]);

  return <ActivityList items={items} />;
}
