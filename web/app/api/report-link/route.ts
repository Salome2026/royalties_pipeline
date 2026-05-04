import { createHmac } from "crypto";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "vpo_web_session";

function signaturePayload(params: {
  keywords: string;
  startMonth: string;
  endMonth: string;
  periodBasis: string;
  mode: string;
  rawLimit: number;
  refreshCache: boolean;
  expires: number;
}) {
  return [
    params.keywords,
    params.startMonth,
    params.endMonth,
    params.periodBasis,
    params.mode,
    String(params.rawLimit),
    params.refreshCache ? "1" : "0",
    String(params.expires),
  ].join("\n");
}

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
  const keywords = Array.isArray(body.keywords)
    ? body.keywords.map((item: unknown) => String(item).trim()).filter(Boolean).join(",")
    : String(body.keywords || "").trim();
  const startMonth = body.start_month || "";
  const endMonth = body.end_month || "";
  const periodBasis = body.period_basis === "statement_period" ? "statement_period" : "transaction_month";
  const mode = body.mode === "all" ? "all" : "any";
  const rawLimit = Number(body.raw_limit) || 0;
  const refreshCache = Boolean(body.refresh_cache);
  const expires = Math.floor(Date.now() / 1000) + 15 * 60;

  if (!keywords) {
    return NextResponse.json({ error: "Ingrese al menos una palabra clave." }, { status: 400 });
  }

  const sig = createHmac("sha256", apiKey)
    .update(signaturePayload({
      keywords,
      startMonth,
      endMonth,
      periodBasis,
      mode,
      rawLimit,
      refreshCache,
      expires,
    }))
    .digest("hex");

  const url = new URL(`${apiUrl.replace(/\/$/, "")}/reports/keyword-download`);
  url.searchParams.set("keywords", keywords);
  url.searchParams.set("start_month", startMonth);
  url.searchParams.set("end_month", endMonth);
  url.searchParams.set("period_basis", periodBasis);
  url.searchParams.set("mode", mode);
  url.searchParams.set("raw_limit", String(rawLimit));
  url.searchParams.set("refresh_cache", refreshCache ? "true" : "false");
  url.searchParams.set("expires", String(expires));
  url.searchParams.set("sig", sig);

  return NextResponse.json({ url: url.toString() });
}
