"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import type { ProjectConfig } from "@/lib/types";

function Swatch({
  project,
  size,
}: {
  project: ProjectConfig;
  size: number;
}) {
  if (project.logo) {
    return (
      <span
        className="grid place-items-center overflow-hidden"
        style={{
          width: size,
          height: size,
          borderRadius: size <= 28 ? 8 : 10,
          background: "var(--color-surface)",
          border: "1px solid color-mix(in srgb, var(--color-ink) 8%, transparent)",
        }}
      >
        <Image
          src={project.logo}
          alt={`${project.name} logo`}
          width={size}
          height={size}
          style={{ objectFit: "contain", width: size, height: size }}
          priority={size >= 30}
        />
      </span>
    );
  }
  return (
    <span
      className="grid place-items-center"
      style={{
        width: size,
        height: size,
        borderRadius: size <= 28 ? 8 : 10,
        background: project.comingSoon ? "transparent" : "var(--color-ink)",
        color: project.comingSoon
          ? "color-mix(in srgb, var(--color-ink) 45%, transparent)"
          : "var(--color-bg)",
        fontFamily: "var(--font-mono)",
        fontSize: size <= 28 ? 11 : 14,
        fontWeight: 500,
        border: project.comingSoon
          ? "1px dashed color-mix(in srgb, var(--color-ink) 25%, transparent)"
          : "none",
      }}
    >
      {project.mark}
    </span>
  );
}

type Props = {
  projects: ProjectConfig[];
  currentKey: string;
};

export function ProjectSwitcher({ projects, currentKey }: Props) {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const sp = useSearchParams();
  const ref = useRef<HTMLDivElement>(null);

  const current = projects.find((p) => p.key === currentKey) ?? projects[0];

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("click", onDoc);
    return () => document.removeEventListener("click", onDoc);
  }, []);

  function select(key: string) {
    const params = new URLSearchParams(sp.toString());
    params.set("project", key);
    params.delete("wallet");
    router.push(`/?${params.toString()}`);
    setOpen(false);
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        className="flex items-center gap-3.5 bg-transparent p-0 text-left cursor-pointer"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        <Swatch project={current} size={36} />
        <span
          className="text-[44px] leading-none font-semibold"
          style={{ letterSpacing: "-0.025em" }}
        >
          {current.name}
        </span>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          className={`w-[18px] h-[18px] ink-45 transition-transform ${
            open ? "rotate-180" : ""
          }`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-3 bg-white border border-ink-12 rounded-[14px] min-w-[340px] p-1.5 z-30"
          style={{
            boxShadow:
              "0 12px 32px -12px color-mix(in srgb, var(--color-ink) 20%, transparent)",
          }}
        >
          {projects.map((p) => (
            <div
              key={p.key}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-[10px] cursor-pointer hover:bg-ink-06 ${
                p.key === currentKey ? "bg-ink-06" : ""
              }`}
              onClick={() => select(p.key)}
            >
              <Swatch project={p} size={28} />
              <div className="flex flex-col leading-tight">
                <b className="font-medium text-[14px]">{p.name}</b>
                <span className="text-[12px] ink-45">{p.team ?? ""}</span>
              </div>
              <svg
                className={`ml-auto w-4 h-4 ${
                  p.key === currentKey ? "opacity-100" : "opacity-0"
                }`}
                viewBox="0 0 24 24"
                fill="none"
                stroke="var(--color-accent)"
                strokeWidth="2.2"
              >
                <polyline points="5 12 10 17 19 8" />
              </svg>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
