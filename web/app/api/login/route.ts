import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "vpo_web_session";

export async function POST(request: NextRequest) {
  const { password } = await request.json();
  const expected = process.env.VPO_WEB_PASSWORD;

  if (!expected || expected === "change-me") {
    return NextResponse.json({ error: "VPO_WEB_PASSWORD is not configured." }, { status: 500 });
  }

  if (password !== expected) {
    return NextResponse.json({ error: "Contrasena incorrecta." }, { status: 401 });
  }

  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE, "ok", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 8,
  });

  return NextResponse.json({ ok: true });
}
