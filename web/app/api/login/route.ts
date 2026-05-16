import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { authenticateUser, createSessionToken, SESSION_COOKIE } from "../_auth";

export async function POST(request: NextRequest) {
  const { username, password } = await request.json();
  const user = authenticateUser(username || "ruben", password || "");

  if (!user) {
    return NextResponse.json({ error: "Usuario o contrasena incorrectos." }, { status: 401 });
  }

  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE, createSessionToken(user), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 8,
  });

  return NextResponse.json({ ok: true, user });
}
