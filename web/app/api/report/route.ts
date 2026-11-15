import { NextRequest, NextResponse } from "next/server";
import { get as httpGet } from "node:http";
import { get as httpsGet } from "node:https";
import { Readable } from "node:stream";
import { apiConfig, royaltyHeaders } from "../_auth";

export const maxDuration = 300;

function getDownload(url: URL, headers: Record<string, string>, signal: AbortSignal) {
  const get = url.protocol === "https:" ? httpsGet : httpGet;
  return new Promise<Response>((resolve, reject) => {
    const request = get(url, { headers, signal }, (incoming) => {
      const responseHeaders = new Headers();
      for (const name of ["content-disposition", "content-type", "content-length"]) {
        const value = incoming.headers[name];
        if (typeof value === "string") responseHeaders.set(name, value);
      }
      const status = incoming.statusCode ?? 502;
      const body = status === 204 || status === 205 || status === 304
        ? null
        : Readable.toWeb(incoming, { strategy: { highWaterMark: 1 } }) as ReadableStream<Uint8Array>;
      if (body === null) incoming.resume();
      resolve(new Response(body, { status, headers: responseHeaders }));
    });
    request.once("error", reject);
  });
}

async function backendError(response: Response, fallback: string) {
  let detail = fallback;
  const text = await response.text();
  try {
    const payload = JSON.parse(text);
    detail = payload.detail || payload.error || fallback;
  } catch {
    if (response.status < 500 && text) detail = text;
  }
  return NextResponse.json({ error: detail }, { status: response.status });
}

export async function POST(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const body = await request.json();
  const response = await fetch(`${config.apiUrl}/reports/jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...royaltyHeaders(config),
      "X-VPO-Username": config.user.username,
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!response.ok) {
    return backendError(response, "No se pudo iniciar el reporte.");
  }
  return NextResponse.json(await response.json(), { status: 202 });
}

export async function GET(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const jobId = request.nextUrl.searchParams.get("job_id");
  const download = request.nextUrl.searchParams.get("download") === "1";
  const limit = request.nextUrl.searchParams.get("limit") || "8";
  const part = request.nextUrl.searchParams.get("file") || "primary";
  if (part !== "primary" && part !== "detail") {
    return NextResponse.json({ error: "Archivo de reporte inválido." }, { status: 400 });
  }
  const endpoint = jobId
    ? `/reports/jobs/${encodeURIComponent(jobId)}${download ? "/download?file=" + part : ""}`
    : `/reports/jobs?limit=${encodeURIComponent(limit)}`;
  const headers = royaltyHeaders(config);
  const url = new URL(`${config.apiUrl}${endpoint}`);
  const response = download
    ? await getDownload(url, headers, request.signal)
    : await fetch(url, { headers, cache: "no-store" });
  if (!response.ok) {
    return backendError(response, download ? "No se pudo descargar el reporte." : "No se pudo consultar el reporte.");
  }

  if (!download) return NextResponse.json(await response.json());

  const disposition = response.headers.get("content-disposition");
  if (disposition?.startsWith("attachment;")) {
    const headers = new Headers({ "Content-Disposition": disposition, "Cache-Control": "private, no-store, no-transform" });
    for (const name of ["content-type", "content-length"]) {
      const value = response.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new NextResponse(response.body, { status: response.status, headers });
  }

  const payload = await response.json();
  let target: URL;
  try {
    target = new URL(String(payload.url || ""));
  } catch {
    return NextResponse.json({ error: "La descarga segura no es válida." }, { status: 502 });
  }
  if (target.protocol !== "https:" || target.hostname !== "storage.googleapis.com") {
    return NextResponse.json({ error: "La descarga segura no es válida." }, { status: 502 });
  }
  return NextResponse.redirect(target, 307);
}
