import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const SESSION_COOKIE = "vpo_web_session";

export async function GET() {
  const cookieStore = await cookies();
  return NextResponse.json({ authenticated: cookieStore.get(SESSION_COOKIE)?.value === "ok" });
}
