import type { ProjectConfig } from "@/lib/types";

export function ComingSoon({ project }: { project: ProjectConfig }) {
  return (
    <div
      className="bg-transparent border border-dashed border-ink-12 rounded-[18px] py-16 px-8 text-center"
      style={{ marginTop: "12px" }}
    >
      <div className="text-[12px] ink-45 uppercase tracking-[0.12em] mb-3">
        Coming soon
      </div>
      <div
        className="text-[40px]"
        style={{ fontFamily: "var(--font-serif)", letterSpacing: "-0.02em" }}
      >
        {project.name}
      </div>
      <div className="ink-60 text-[14px] mt-3">{project.description}</div>
    </div>
  );
}
