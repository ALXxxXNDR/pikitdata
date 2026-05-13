import NextAuth from "next-auth";
import { authConfig } from "./auth.config";

export default NextAuth(authConfig).auth;

export const config = {
  // 정적 자원과 favicon 은 미들웨어 건너뜀.
  matcher: ["/((?!_next/static|_next/image|favicon\\.ico|logos/).*)"],
};
