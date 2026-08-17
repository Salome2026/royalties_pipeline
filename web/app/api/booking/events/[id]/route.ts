import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../../../_auth";

async function apiError(response: Response) {
  let detail = `Error API ${response.status}`;
  try {
    const payload = await response.json();
    detail = typeof payload.detail === "string" ? payload.detail : payload.detail?.message || payload.error || detail;
  } catch {
    const text = await response.text();
    detail = text || detail;
  }
  return NextResponse.json({ error: detail }, { status: response.status });
}

export async function PUT(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const { id } = await context.params;
  const response = await fetch(`${config.apiUrl}/booking/events/${id}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
    body: JSON.stringify(await request.json()),
  });
  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function DELETE(_request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const { id } = await context.params;
  const response = await fetch(`${config.apiUrl}/booking/events/${id}`, {
    method: "DELETE",
    headers: {
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
  });
  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}
