import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../../../../_auth";

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ receiptId: string }> },
) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const { receiptId } = await context.params;
  const response = await fetch(`${config.apiUrl}/finance/receipts/${receiptId}/pdf`, {
    headers: {
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
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

  const buffer = await response.arrayBuffer();
  return new NextResponse(buffer, {
    headers: {
      "Content-Type": response.headers.get("Content-Type") || "application/pdf",
      "Content-Disposition": response.headers.get("Content-Disposition") || "inline",
    },
  });
}
