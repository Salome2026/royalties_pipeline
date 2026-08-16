import { NextResponse } from "next/server";
import { apiConfig } from "../../../_auth";

export async function GET() {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const response = await fetch(`${config.apiUrl}/booking/events/options`, {
    headers: {
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    return NextResponse.json(
      { error: payload.detail || payload.error || "No se pudo cargar Booking." },
      { status: response.status },
    );
  }
  return NextResponse.json(await response.json());
}
