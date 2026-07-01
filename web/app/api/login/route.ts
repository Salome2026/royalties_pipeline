import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { createSessionToken, SESSION_COOKIE } from "../_auth";

export async function POST(request: NextRequest) {
  const { username, password } = await request.json();
  let user = null;
  const normalizedUsername = String(username || "").trim();

  const apiUrl = process.env.VPO_API_URL?.replace(/\/$/, "");
  const apiKey = process.env.VPO_API_KEY;
  if (apiUrl && apiKey) {
    const response = await fetch(`${apiUrl}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-VPO-API-Key": apiKey,
      },
      body: JSON.stringify({ username: normalizedUsername, password: password || "" }),
      cache: "no-store",
    }).catch(() => null);

    if (response?.ok) {
      const data = await response.json();
      user = data.user || null;
    }
  }

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
