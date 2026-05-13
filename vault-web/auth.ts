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

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  providers: [Google],
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
