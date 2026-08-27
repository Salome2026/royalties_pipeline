import type { CatalogData, CatalogQuery, CatalogUpdate } from "./types";

async function responseError(response: Response, fallback: string) {
  const payload = await response.json().catch(() => ({ error: fallback }));
  return typeof payload?.error === "string" ? payload.error : fallback;
}

export async function requestCatalog(query: CatalogQuery): Promise<CatalogData> {
  const params = new URLSearchParams();
  if (query.source) params.set("source", query.source);
  if (query.account) params.set("account", query.account);
  if (query.artist) params.set("artist", query.artist);
  if (query.keyword.trim()) params.set("keyword", query.keyword.trim());
  if (query.label) params.set("label", query.label);
  if (query.startMonth) params.set("start_month", query.startMonth);
  if (query.endMonth) params.set("end_month", query.endMonth);
  params.set("status", query.status);
  params.set("limit", String(query.limit));
  params.set("offset", String(query.offset));

  const response = await fetch(`/api/catalog?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(await responseError(response, "No se pudo cargar el catálogo."));
  return response.json();
}

export async function requestCatalogUpdate(update: CatalogUpdate): Promise<void> {
  const response = await fetch("/api/catalog", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!response.ok) throw new Error(await responseError(response, "No se pudo actualizar el catálogo."));
}
