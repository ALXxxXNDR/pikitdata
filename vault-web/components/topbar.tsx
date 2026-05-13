import Image from "next/image";
import { auth, signOut } from "@/auth";
import { RefreshControl } from "./refresh-control";

export async function Topbar() {
  const session = await auth();
  const user = session?.user;
  const initials = user?.email
    ? user.email.slice(0, 2).toUpperCase()
    : user?.name?.slice(0, 2).toUpperCase() ?? "??";

  return (
    <header className="flex items-center justify-between gap-6 py-2 pb-7 border-b border-ink-12">
      <div className="flex items-center gap-2.5 text-[15px] font-semibold">
        <div
          className="grid place-items-center w-[28px] h-[28px] rounded-md overflow-hidden"
          style={{ background: "var(--color-ink)" }}
        >
          <Image
            src="/logos/despell.png"
            alt="DeSpell"
            width={20}
            height={20}
            style={{ objectFit: "contain" }}
            priority
          />
        </div>
        DeSpell Vault{" "}
        <small className="ink-45 font-normal ml-1">· 프로젝트 대시보드</small>
      </div>
      <div className="flex items-center gap-2.5">
        <RefreshControl />

        {user ? (
          <>
            <span
              className="inline-flex items-center gap-2 px-3 py-2 rounded-full text-[12.5px] border border-ink-12"
              title={user.email ?? user.name ?? "user"}
            >
              <span
                className="grid place-items-center w-5 h-5 rounded-full"
                style={{
                  background: "var(--color-ink)",
                  color: "var(--color-bg)",
                  fontFamily: "var(--font-mono)",
                  fontSize: 9,
                  fontWeight: 600,
                }}
              >
                {initials}
              </span>
              <span
                className="ink-60 max-w-[140px] truncate"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {user.email ?? user.name}
              </span>
            </span>
            <form
              action={async () => {
                "use server";
                await signOut({ redirectTo: "/login" });
              }}
            >
              <button
                type="submit"
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-full text-[13px] border border-ink-12 hover:bg-ink-06 cursor-pointer"
                title="로그아웃"
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  width="14"
                  height="14"
                >
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
                로그아웃
              </button>
            </form>
          </>
        ) : null}
      </div>
    </header>
  );
}
