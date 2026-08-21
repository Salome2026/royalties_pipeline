import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../_auth";

export const maxDuration = 300;

export async function POST(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const body = await request.json();
  const output = body.output === "google_sheet"
    ? "google_sheet"
    : body.output === "executive_pdf"
      ? "executive_pdf"
      : "excel";
  const endpoint = output === "google_sheet"
    ? "reports/google-sheet"
    : output === "executive_pdf"
      ? "reports/executive"
      : "reports/keyword";
  delete body.output;

  const response = await fetch(`${config.apiUrl}/${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": config.apiKey,
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
  const filename = filenameMatch?.[1] || (output === "executive_pdf" ? "vpo_corp_report.pdf" : "vpo_corp_report.xlsx");

  return new NextResponse(buffer, {
    status: 200,
    headers: {
      "Content-Type": output === "executive_pdf"
        ? "application/pdf"
        : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  });
}
