export type PeriodProfile =
  | "monthly_report"
  | "custom_report"
  | "preset_or_range"
  | "dashboard_period"
  | "activity_window"
  | "commission_period"
  | "validity_range";

export type PeriodMode =
  | "all"
  | "single_month"
  | "closed_range"
  | "last_6_months"
  | "last_12_months"
  | "from_month"
  | "until_month";

export type PeriodSelection = {
  mode: PeriodMode;
  startMonth?: string;
  endMonth?: string;
};

export type ResolvedPeriod = {
  mode: PeriodMode;
  startMonth: string | null;
  endMonth: string | null;
  label: string;
};

export const MONTH_NAMES_SHORT = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

export function isMonthValue(value?: string | null) {
  return Boolean(value && /^\d{4}-\d{2}$/.test(value));
}

export function formatMonth(value?: string | null) {
  if (!isMonthValue(value)) return "";
  const year = String(value).slice(0, 4);
  const monthIndex = Number(String(value).slice(5, 7)) - 1;
  return `${MONTH_NAMES_SHORT[monthIndex] || String(value).slice(5, 7)} ${year}`;
}

export function selectionFromMonths(startMonth: string, endMonth: string): PeriodSelection {
  if (startMonth && endMonth) {
    return {
      mode: startMonth === endMonth ? "single_month" : "closed_range",
      startMonth,
      endMonth,
    };
  }
  if (startMonth) {
    return { mode: "single_month", startMonth, endMonth: startMonth };
  }
  if (endMonth) {
    return { mode: "single_month", startMonth: endMonth, endMonth };
  }
  return { mode: "all" };
}

export function selectionFromUntil(endMonth: string): PeriodSelection {
  return endMonth ? { mode: "until_month", endMonth } : { mode: "all" };
}

export function resolvePeriod(selection: PeriodSelection, _profile: PeriodProfile): ResolvedPeriod {
  if (selection.mode === "all") {
    return { mode: "all", startMonth: null, endMonth: null, label: "Todo" };
  }
  if (selection.mode === "last_6_months") {
    return { mode: "last_6_months", startMonth: null, endMonth: null, label: "Últimos 6 meses" };
  }
  if (selection.mode === "last_12_months") {
    return { mode: "last_12_months", startMonth: null, endMonth: null, label: "Últimos 12 meses" };
  }
  if (selection.mode === "until_month") {
    const endMonth = selection.endMonth || selection.startMonth || "";
    return {
      mode: "until_month",
      startMonth: null,
      endMonth: endMonth || null,
      label: endMonth ? `Hasta ${formatMonth(endMonth)}` : "Todo",
    };
  }
  if (selection.mode === "from_month") {
    const startMonth = selection.startMonth || selection.endMonth || "";
    return {
      mode: "from_month",
      startMonth: startMonth || null,
      endMonth: null,
      label: startMonth ? `Desde ${formatMonth(startMonth)}` : "Todo",
    };
  }
  if (selection.mode === "single_month") {
    const month = selection.startMonth || selection.endMonth || "";
    return {
      mode: "single_month",
      startMonth: month || null,
      endMonth: month || null,
      label: month ? formatMonth(month) : "Todo",
    };
  }

  const startMonth = selection.startMonth || "";
  const endMonth = selection.endMonth || startMonth;
  return {
    mode: "closed_range",
    startMonth: startMonth || null,
    endMonth: endMonth || null,
    label: startMonth && endMonth ? `${formatMonth(startMonth)} - ${formatMonth(endMonth)}` : "Todo",
  };
}

export function isResolvedPeriodInvalid(period: ResolvedPeriod) {
  return Boolean(period.startMonth && period.endMonth && period.startMonth > period.endMonth);
}
