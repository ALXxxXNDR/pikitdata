import NextAuth from "next-auth";
import { authConfig } from "./auth.config";

export default NextAuth(authConfig).auth;

export const config = {
  // 정적 자원, favicon, OG 메타데이터 라우트는 proxy 건너뜀.
  // OG 이미지는 외부 fetcher (노션/슬랙/카톡 등) 가 공개로 접근 필요.
  matcher: [
    "/((?!_next/static|_next/image|favicon\\.ico|logos/|opengraph-image|twitter-image).*)",
  ],
};
