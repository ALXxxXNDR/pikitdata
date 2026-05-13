import { signIn } from "@/auth";

type SearchParams = { error?: string; callbackUrl?: string };

const ERROR_MESSAGES: Record<string, string> = {
  AccessDenied:
    "허용된 회사 도메인 이메일이 아니에요. IT 관리자에게 도메인 등록을 문의하세요.",
  Configuration:
    "인증 서비스 설정에 문제가 있어요. 잠시 후 다시 시도하거나 관리자에게 문의하세요.",
  default: "로그인 중 문제가 발생했어요. 다시 시도해주세요.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const errorKey = sp.error;
  const errorMsg = errorKey
    ? (ERROR_MESSAGES[errorKey] ?? ERROR_MESSAGES.default)
    : null;
  const callbackUrl = sp.callbackUrl ?? "/";

  return (
    <div className="min-h-screen grid place-items-center px-6">
      <div
        className="w-full max-w-[420px] bg-white border border-ink-12 rounded-[18px] p-10"
        style={{
          boxShadow:
            "0 24px 48px -16px color-mix(in srgb, var(--color-ink) 16%, transparent)",
        }}
      >
        <div className="flex items-center gap-2 mb-8">
          <div
            className="grid place-items-center w-[22px] h-[22px] rounded-md"
            style={{
              background: "var(--color-ink)",
              color: "var(--color-bg)",
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              fontWeight: 600,
              letterSpacing: "-0.04em",
            }}
          >
            V
          </div>
          <div className="text-[15px] font-semibold">Vault Stack</div>
        </div>

        <h1
          className="m-0 text-[36px]"
          style={{
            fontFamily: "var(--font-serif)",
            letterSpacing: "-0.02em",
            lineHeight: 1.1,
          }}
        >
          회사 계정으로
          <br />
          로그인하세요
        </h1>
        <p className="ink-60 text-[13.5px] mt-3 mb-7 leading-relaxed">
          허용된 회사 도메인 이메일만 대시보드에 접근할 수 있어요.
        </p>

        {errorMsg && (
          <div
            className="mb-5 text-[12.5px] px-3 py-3 rounded-[10px]"
            style={{
              background:
                "color-mix(in srgb, var(--color-ink) 4%, transparent)",
              border:
                "1px solid color-mix(in srgb, var(--color-ink) 12%, transparent)",
              color: "color-mix(in srgb, var(--color-ink) 80%, transparent)",
            }}
          >
            {errorMsg}
          </div>
        )}

        <form
          action={async () => {
            "use server";
            await signIn("google", { redirectTo: callbackUrl });
          }}
        >
          <button
            type="submit"
            className="w-full inline-flex items-center justify-center gap-3 py-3 rounded-[12px] font-medium text-[14px] cursor-pointer"
            style={{
              background: "var(--color-ink)",
              color: "var(--color-surface)",
              border: "1px solid var(--color-ink)",
            }}
          >
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
            >
              <path
                fill="#FFFFFF"
                d="M21.35 11.1H12v2.92h5.27c-.23 1.43-1.66 4.2-5.27 4.2-3.17 0-5.76-2.62-5.76-5.85S8.83 6.52 12 6.52c1.8 0 3.01.77 3.71 1.43l2.53-2.43C16.65 4.07 14.55 3 12 3 6.95 3 2.86 7.08 2.86 12.12S6.95 21.24 12 21.24c6.93 0 9.5-4.86 9.5-7.36 0-.49-.05-.86-.15-1.78Z"
              />
            </svg>
            Google 로 로그인
          </button>
        </form>

        <p
          className="ink-45 text-[11.5px] mt-6 leading-relaxed"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          접속 시 동의: 인증 목적의 Google 이메일/프로필 정보 사용
        </p>
      </div>
    </div>
  );
}
