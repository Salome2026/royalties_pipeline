export type View =
  | "menu"
  | "statement"
  | "royalties"
  | "custom-reports"
  | "participation"
  | "digital-income"
  | "royalties-dashboard"
  | "source-monitor"
  | "catalog"
  | "distributor-config"
  | "booking"
  | "booking-lab"
  | "booking-summary"
  | "commissions"
  | "booking-artist-summary"
  | "artist-finance"
  | "finance-movements"
  | "artists"
  | "employees"
  | "caserio";

export type BookingWorkspaceMode = "individual" | "shared";

export const VIEW_MODULE_KEYS: Partial<Record<View, string>> = {
  statement: "statement_reports",
  royalties: "royalty_reports",
  "custom-reports": "custom_reports",
  participation: "participation",
  "digital-income": "digital_income",
  "royalties-dashboard": "royalties_dashboard",
  "source-monitor": "source_monitor",
  "distributor-config": "distributor_config",
  booking: "booking",
  "booking-lab": "booking_lab",
  "booking-summary": "booking_summary",
  commissions: "booking_commissions",
  "booking-artist-summary": "booking_detail",
  "artist-finance": "artist_finance",
  "finance-movements": "finance_movements",
  artists: "artists",
  employees: "employees",
  caserio: "caserio",
  catalog: "catalog",
};

export function moduleForBookingMode(mode: BookingWorkspaceMode) {
  return mode === "individual" ? "booking" : "composite_booking";
}

export function canShowView(view: View, canAccessModule: (moduleKey: string) => boolean) {
  if (view === "menu") return true;
  if (view === "booking") {
    return canAccessModule("booking_agenda")
      || canAccessModule(moduleForBookingMode("individual"))
      || canAccessModule(moduleForBookingMode("shared"));
  }
  const moduleKey = VIEW_MODULE_KEYS[view];
  return moduleKey ? canAccessModule(moduleKey) : false;
}
