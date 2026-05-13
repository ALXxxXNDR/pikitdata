import type { NextAuthConfig } from "next-auth";

/**
 * 미들웨어(Edge runtime) 와 풀 auth.ts 양쪽에서 공유하는 설정.
 * providers 는 여기에 두지 않음 — Edge 환경에선 Google provider 가 안 돌아감.
 */
export const authConfig = {
  pages: {
    signIn: "/login",
    error: "/login",
  },
  callbacks: {
    /**
     * 미들웨어에서 사용. 미인증이면 자동으로 signIn 페이지로 리다이렉트.
     * 공개 경로는 true 반환.
     */
    authorized({ auth, request }) {
      const { pathname } = request.nextUrl;
      // 인증 흐름 자체 / 로그인 페이지 / cron 알림 엔드포인트 / 정적 자원 → 공개
      if (pathname.startsWith("/login")) return true;
      if (pathname.startsWith("/api/auth")) return true;
      if (pathname.startsWith("/api/alert")) return true;
      return !!auth?.user;
    },
  },
  providers: [],
} satisfies NextAuthConfig;
