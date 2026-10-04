import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const privateRoots = ["/dashboard", "/profile", "/cvs", "/jobs", "/matches", "/applications", "/email", "/settings", "/privacy", "/admin", "/auth", "/login", "/register", "/forgot-password", "/reset-password", "/verify-email"];
export function middleware(request: NextRequest) {
  const response = NextResponse.next();
  if (privateRoots.some((root) => request.nextUrl.pathname === root || request.nextUrl.pathname.startsWith(`${root}/`))) {
    response.headers.set("X-Robots-Tag", "noindex, nofollow, noarchive");
  }
  return response;
}
export const config = { matcher: ["/:path*"] };
