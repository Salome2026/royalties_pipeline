import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { createSessionToken, currentUser, SESSION_COOKIE } from "../_auth";

export async function POST(request: NextRequest) {
  const user = await currentUser();
  if (!user) {
    return NextResponse.json({ error: "No autorizado." }, { status: 401 });
  }

  const { currentPassword, newPassword } = await request.json();
  const apiUrl = process.env.VPO_API_URL?.replace(/\/$/, "");
  const apiKey = process.env.VPO_API_KEY;

  if (!apiUrl || !apiKey) {
    return NextResponse.json({ error: "VPO_API_URL o VPO_API_KEY no estan configurados." }, { status: 500 });
  }

  const response = await fetch(`${apiUrl}/auth/change-password`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": apiKey,
    },
    body: JSON.stringify({
      username: user.username,
      current_password: currentPassword || "",
      new_password: newPassword || "",
    }),
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `Error API ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.error || detail;
    } catch {
      const text = await response.text();
      detail = text || detail;
    }
    return NextResponse.json({ error: detail }, { status: response.status });
  }

  const data = await response.json();
  const nextUser = data.user || { ...user, mustChangePassword: false };
  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE, createSessionToken(nextUser), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 8,
  });

  return NextResponse.json({ ok: true, user: nextUser });
}
