import { NextResponse } from "next/server";
import { apiConfig } from "../../_auth";

async function apiError(response: Response) {
  let detail = `Error API ${response.status}`;
  try {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      detail = payload.detail || payload.error || detail;
    } else {
      const text = await response.text();
      detail = text || detail;
    }
  } catch {
    detail = `Error API ${response.status}`;
  }
  return NextResponse.json({ error: detail }, { status: response.status });
}

export async function GET() {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const response = await fetch(`${config.apiUrl}/employees/finance-options`, {
    headers: {
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
    cache: "no-store",
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}
