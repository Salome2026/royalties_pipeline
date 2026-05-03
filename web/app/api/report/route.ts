import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "vpo_web_session";

export const maxDuration = 300;

export async function POST(request: NextRequest) {
  const cookieStore = await cookies();
  if (cookieStore.get(SESSION_COOKIE)?.value !== "ok") {
    return NextResponse.json({ error: "No autorizado." }, { status: 401 });
  }

  const apiUrl = process.env.VPO_API_URL;
  const apiKey = process.env.VPO_API_KEY;

  if (!apiUrl || !apiKey) {
    return NextResponse.json({ error: "VPO_API_URL o VPO_API_KEY no estan configurados." }, { status: 500 });
  }

  const body = await request.json();
  const output = body.output === "google_sheet" ? "google_sheet" : "excel";
  const endpoint = output === "google_sheet" ? "reports/google-sheet" : "reports/keyword";
  delete body.output;

  const response = await fetch(`${apiUrl.replace(/\/$/, "")}/${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": apiKey,
    },
    body: JSON.stringify(body),
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

  if (output === "google_sheet") {
    const payload = await response.json();
    return NextResponse.json(payload);
  }

  const buffer = await response.arrayBuffer();
  const disposition = response.headers.get("content-disposition") || "";
  const filenameMatch = disposition.match(/filename="?([^"]+)"?/i);
  const filename = filenameMatch?.[1] || "vpo_corp_report.xlsx";

  return new NextResponse(buffer, {
    status: 200,
    headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  });
}
