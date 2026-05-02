import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "vpo_web_session";

export async function GET(request: NextRequest) {
  const cookieStore = await cookies();
  if (cookieStore.get(SESSION_COOKIE)?.value !== "ok") {
    return NextResponse.json({ error: "No autorizado." }, { status: 401 });
  }

  const apiUrl = process.env.VPO_API_URL;
  const apiKey = process.env.VPO_API_KEY;

  if (!apiUrl || !apiKey) {
    return NextResponse.json({ error: "VPO_API_URL o VPO_API_KEY no estan configurados." }, { status: 500 });
  }

  const params = new URLSearchParams();
  params.set("refresh_cache", request.nextUrl.searchParams.get("refresh") === "1" ? "true" : "false");
  params.set("preset", request.nextUrl.searchParams.get("preset") || "last_year");

  const startMonth = request.nextUrl.searchParams.get("start_month");
  const endMonth = request.nextUrl.searchParams.get("end_month");
  if (startMonth) params.set("start_month", startMonth);
  if (endMonth) params.set("end_month", endMonth);

  const response = await fetch(`${apiUrl.replace(/\/$/, "")}/participation/distributors?${params.toString()}`, {
    headers: { "X-VPO-API-Key": apiKey },
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

  return NextResponse.json(await response.json());
}
