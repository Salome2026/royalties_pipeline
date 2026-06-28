import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { createSessionToken, currentUser, SESSION_COOKIE } from "../_auth";

export async function GET() {
  const user = await currentUser();
  if (!user) {
    return NextResponse.json({ authenticated: false, user: null });
  }

  const apiUrl = process.env.VPO_API_URL?.replace(/\/$/, "");
  const apiKey = process.env.VPO_API_KEY;
  if (!apiUrl || !apiKey) {
    const cookieStore = await cookies();
    cookieStore.set(SESSION_COOKIE, "", {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 0,
    });
    return NextResponse.json({ authenticated: false, user: null });
  }

  const response = await fetch(`${apiUrl}/auth/session`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": apiKey,
    },
    body: JSON.stringify({ username: user.username }),
    cache: "no-store",
  }).catch(() => null);

  if (!response?.ok) {
    const cookieStore = await cookies();
    cookieStore.set(SESSION_COOKIE, "", {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 0,
    });
    return NextResponse.json({ authenticated: false, user: null });
  }

  const data = await response.json();
  const liveUser = data.user || null;
  if (!liveUser) {
    return NextResponse.json({ authenticated: false, user: null });
  }

  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE, createSessionToken(liveUser), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 8,
  });

  return NextResponse.json({ authenticated: true, user: liveUser });
}
