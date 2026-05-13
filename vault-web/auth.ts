import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import { authConfig } from "./auth.config";

/**
 * 회사 도메인 화이트리스트 — env 로 콤마 구분 가능.
 * 예: AUTH_ALLOWED_DOMAINS="despell.io,depsell.io"
 */
const ALLOWED_DOMAINS = (process.env.AUTH_ALLOWED_DOMAINS ?? "despell.io")
  .split(",")
  .map((d) => d.trim().toLowerCase())
  .filter(Boolean);

// Auth.js v5 는 기본적으로 AUTH_GOOGLE_ID / AUTH_GOOGLE_SECRET 만 자동 인식.
// 우리는 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET 로 env 저장했으니 명시적으로 전달.
const GOOGLE_CLIENT_ID =
  process.env.GOOGLE_CLIENT_ID || process.env.AUTH_GOOGLE_ID || "";
const GOOGLE_CLIENT_SECRET =
  process.env.GOOGLE_CLIENT_SECRET || process.env.AUTH_GOOGLE_SECRET || "";

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  providers: [
    Google({
      clientId: GOOGLE_CLIENT_ID,
      clientSecret: GOOGLE_CLIENT_SECRET,
      // 매번 계정 선택 화면 강제 — 브라우저가 자동으로 단일 Google 계정으로
      // 로그인되는 동작 방지. select_account + consent 둘 다 줘서 picker 가
      // 무조건 뜨게 함.
      authorization: {
        params: { prompt: "select_account", access_type: "offline" },
      },
    }),
  ],
  callbacks: {
    ...authConfig.callbacks,
    /**
     * Google OAuth 로 인증된 사용자의 email 도메인 검증.
     * 허용 도메인이 아니면 false 반환 → Auth.js 가 /login?error=AccessDenied 로 리다이렉트.
     */
    async signIn({ user }) {
      const email = user.email?.toLowerCase() ?? "";
      const domain = email.split("@")[1] ?? "";
      if (!domain) return false;
      return ALLOWED_DOMAINS.includes(domain);
    },
  },
});
