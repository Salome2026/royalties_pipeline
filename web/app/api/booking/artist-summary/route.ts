import { NextResponse } from "next/server";
import { apiConfig } from "../../_auth";

type BookingShowLike = {
  id: number;
  artist?: string;
  show_date?: string;
  venue?: string;
  city?: string | null;
  contracted_cachet_amount?: number;
  cachet_amount?: number;
  artist_cash_target_amount?: number;
  producer_cash_target_amount?: number;
  booking_commission_exempt?: number | boolean;
  booking_commission_notes?: string | null;
  settlement_status?: string | null;
  origin_type?: string | null;
  origin_id?: number | null;
};

async function apiError(response: Response) {
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

function numberValue(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function buildSummary(shows: BookingShowLike[], selectedArtist: string | null) {
  const artists = Array.from(new Set(shows.map((item) => item.artist).filter(Boolean) as string[])).sort((a, b) => a.localeCompare(b));
  const filtered = selectedArtist ? shows.filter((item) => item.artist === selectedArtist) : shows;

  const items = filtered.map((item) => {
    const indyanaIncome = numberValue(item.producer_cash_target_amount);
    const isCommissionable = !Boolean(item.booking_commission_exempt);
    return {
      id: item.id,
      artist: item.artist || "",
      show_date: item.show_date || "",
      venue: item.venue || "",
      city: item.city || "",
      cachet_total: numberValue(item.contracted_cachet_amount || item.cachet_amount),
      artist_income: numberValue(item.artist_cash_target_amount),
      indyana_income: indyanaIncome,
      is_commissionable: isCommissionable,
      commissionable_income: isCommissionable ? indyanaIncome : 0,
      non_commissionable_income: isCommissionable ? 0 : indyanaIncome,
      commission_notes: item.booking_commission_notes || "",
      settlement_status: item.settlement_status || "",
      origin_type: item.origin_type || null,
      origin_id: item.origin_id || null,
    };
  });

  const monthly: Record<string, {
    month: string;
    shows: number;
    cachet_total: number;
    artist_income: number;
    indyana_income: number;
    commissionable_income: number;
    non_commissionable_income: number;
  }> = {};

  for (const item of items) {
    const month = String(item.show_date || "").slice(0, 7);
    if (!month) continue;
    const bucket = monthly[month] ||= {
      month,
      shows: 0,
      cachet_total: 0,
      artist_income: 0,
      indyana_income: 0,
      commissionable_income: 0,
      non_commissionable_income: 0,
    };
    bucket.shows += 1;
    bucket.cachet_total += item.cachet_total;
    bucket.artist_income += item.artist_income;
    bucket.indyana_income += item.indyana_income;
    bucket.commissionable_income += item.commissionable_income;
    bucket.non_commissionable_income += item.non_commissionable_income;
  }

  return {
    generated_at: new Date().toISOString(),
    selected_artist: selectedArtist,
    artists,
    items,
    months: Object.values(monthly).sort((a, b) => b.month.localeCompare(a.month)),
    totals: {
      shows: items.length,
      cachet_total: items.reduce((total, item) => total + item.cachet_total, 0),
      artist_income: items.reduce((total, item) => total + item.artist_income, 0),
      indyana_income: items.reduce((total, item) => total + item.indyana_income, 0),
      commissionable_income: items.reduce((total, item) => total + item.commissionable_income, 0),
      non_commissionable_income: items.reduce((total, item) => total + item.non_commissionable_income, 0),
    },
  };
}

export async function GET(request: Request) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const url = new URL(request.url);
  const artist = url.searchParams.get("artist") || null;

  const response = await fetch(`${config.apiUrl}/booking/shows?limit=1000`, {
    headers: { "X-VPO-API-Key": config.apiKey },
    cache: "no-store",
  });

  if (!response.ok) return apiError(response);
  const payload = await response.json();
  return NextResponse.json(buildSummary(payload.items || [], artist));
}
