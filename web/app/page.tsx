"use client";

import { FormEvent, MouseEvent, useEffect, useMemo, useState } from "react";

type Message = {
  type: "ok" | "error";
  text: string;
};

type WebUser = {
  username: string;
  role: "viewer" | "editor" | "admin";
  canEdit: boolean;
};

type View = "menu" | "statement" | "royalties" | "participation" | "booking" | "booking-lab" | "booking-summary" | "booking-artist-summary" | "artists" | "caserio" | "composite-booking";

type ParticipationItem = {
  source: string;
  amount_usd: number;
  percentage: number;
};

type ParticipationData = {
  updated_at: string;
  preset: string;
  start_month: string | null;
  end_month: string | null;
  start_date: string | null;
  end_date: string | null;
  available_start_month: string | null;
  available_end_month: string | null;
  total_amount_usd: number;
  items: ParticipationItem[];
};

type ParticipationCache = {
  data: ParticipationData;
  preset: string;
  startMonth: string;
  endMonth: string;
};

type BookingAdjustment = {
  id: number;
  show_id: number;
  concept: string;
  adjustment_type: string;
  area: string;
  impact: string;
  recoverable: boolean;
  amount: number;
  applied_amount: number;
  currency: "ARS" | "USD";
  artist_percent: number;
  producer_percent: number;
  artist_amount: number;
  producer_amount: number;
  notes: string | null;
};

type BookingExpense = {
  id: number;
  show_id: number;
  concept: string;
  category: string;
  amount: number;
  currency: "ARS" | "USD";
  notes: string | null;
};

type BookingPreSplitAdjustment = {
  id: number;
  show_id: number;
  concept: string;
  destination: "artist" | "producer";
  amount: number;
  currency: "ARS" | "USD";
  notes: string | null;
};

type BookingExternalShare = {
  id: number;
  show_id: number;
  name: string;
  role: "manager_externo" | "socio_externo" | "tercero" | "otro";
  percent: number | null;
  amount: number;
  currency: "ARS" | "USD";
  cash_handled_by_vpo: boolean;
  notes: string | null;
};

type BookingCashMovement = {
  id: number;
  show_id: number;
  recipient: "producer" | "artist";
  concept: string | null;
  payment_method: "transferencia" | "efectivo" | "seña" | "otro";
  amount: number;
  paid_by?: string | null;
  notes: string | null;
};

type BookingShow = {
  id: number;
  artist: string;
  show_date: string;
  venue: string;
  city: string | null;
  tour_manager: string | null;
  seller: string | null;
  status: string;
  currency: "ARS" | "USD";
  fx_rate: number | null;
  contracted_cachet_amount: number;
  venue_collected_amount: number;
  venue_balance_amount: number;
  venue_payment_status: string;
  venue_payment_notes: string | null;
  cachet_amount: number;
  expenses_amount: number;
  net_amount: number;
  pre_split_adjustments_amount: number;
  split_base_amount: number;
  artist_percent: number;
  producer_percent: number;
  artist_share_amount: number;
  producer_share_amount: number;
  artist_cash_target_amount: number;
  producer_cash_target_amount: number;
  artist_paid_amount: number;
  producer_received_amount: number;
  balance_artist_amount: number;
  balance_producer_amount: number;
  settlement_status: string | null;
  settlement_group: string | null;
  settlement_closed_at: string | null;
  settlement_notes: string | null;
  booking_commission_exempt: number;
  booking_commission_notes: string | null;
  show_expenses: BookingExpense[];
  cash_movements: BookingCashMovement[];
  pre_split_adjustments: BookingPreSplitAdjustment[];
  external_shares: BookingExternalShare[];
  artist_adjustments: BookingAdjustment[];
  receipt_refs: string[];
  notes: string | null;
};

type BookingArtistRecord = {
  id: number;
  stage_name: string;
  legal_name: string | null;
  cuit: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
};

type BookingArtistForm = {
  stageName: string;
  legalName: string;
  cuit: string;
  phone: string;
  email: string;
  address: string;
  notes: string;
  active: boolean;
};

type BookingSummaryMonth = {
  shows: number;
  indyana_total: number;
  commissionable_total: number;
  non_commissionable_total: number;
};

type BookingSummaryItem = {
  artist: string;
  shows: number;
  indyana_total: number;
  commissionable_total: number;
  non_commissionable_total: number;
  months: Record<string, BookingSummaryMonth>;
  notes: string[];
};

type BookingSummary = {
  generated_at: string;
  months: string[];
  items: BookingSummaryItem[];
  totals: {
    shows: number;
    indyana_total: number;
    commissionable_total: number;
    non_commissionable_total: number;
  };
};

type BookingArtistSummaryItem = {
  id: number;
  artist: string;
  show_date: string;
  venue: string;
  city: string;
  cachet_total: number;
  artist_income: number;
  indyana_income: number;
  is_commissionable: boolean;
  commissionable_income: number;
  non_commissionable_income: number;
  commission_notes: string;
  settlement_status: string;
  origin_type: string | null;
  origin_id: number | null;
};

type BookingArtistSummaryMonth = {
  month: string;
  shows: number;
  cachet_total: number;
  artist_income: number;
  indyana_income: number;
  commissionable_income: number;
  non_commissionable_income: number;
};

type BookingArtistSummary = {
  generated_at: string;
  selected_artist: string | null;
  artists: string[];
  items: BookingArtistSummaryItem[];
  months: BookingArtistSummaryMonth[];
  totals: {
    shows: number;
    cachet_total: number;
    artist_income: number;
    indyana_income: number;
    commissionable_income: number;
    non_commissionable_income: number;
  };
};

type CaserioEventLine = {
  id: number;
  event_id: number;
  line_type: string;
  description: string;
  artist: string | null;
  amount: number;
  booking_show_id: number | null;
  notes: string | null;
};

type CaserioEvent = {
  id: number;
  event_date: string;
  venue: string;
  city: string | null;
  responsible: string | null;
  status: string;
  currency: "ARS" | "USD";
  fx_rate: number | null;
  gross_amount: number;
  caserio_expected_amount: number;
  producer_expected_amount: number;
  total_expected_amount: number;
  received_amount: number;
  balance_amount: number;
  receipt_refs: string[];
  notes: string | null;
  lines: CaserioEventLine[];
};

type BookingCompositeEventExpense = {
  id: number;
  event_id: number;
  concept: string;
  category: string;
  amount: number;
  notes: string | null;
};

type BookingCompositeEventLine = {
  id: number;
  event_id: number;
  line_type: string;
  description: string;
  artist: string | null;
  amount: number;
  artist_percent: number;
  producer_percent: number;
  artist_paid_amount: number;
  producer_received_amount: number;
  booking_commission_exempt: number;
  booking_commission_notes: string | null;
  booking_show_id: number | null;
  notes: string | null;
  show_expenses?: BookingExpense[];
  external_shares?: BookingExternalShare[];
};

type BookingCompositeEvent = {
  id: number;
  event_date: string;
  venue: string;
  city: string | null;
  responsible: string | null;
  status: string;
  currency: "ARS" | "USD";
  gross_amount: number;
  general_expenses_amount: number;
  operational_expenses_amount: number;
  direct_commissions_amount: number;
  artist_base_amount: number;
  allocated_amount: number;
  producer_expected_amount: number;
  received_amount: number;
  balance_amount: number;
  receipt_refs: string[];
  notes: string | null;
  expenses: BookingCompositeEventExpense[];
  lines: BookingCompositeEventLine[];
};

type CaserioLineForm = {
  uid: string;
  lineType: "gasto_general" | "artista_externo" | "artista_vpo";
  description: string;
  amount: string;
  artist: string;
  artistPercent: string;
  producerPercent: string;
  showExpenses: BookingExpenseForm[];
  notes: string;
};

type CaserioForm = {
  eventDate: string;
  venue: string;
  city: string;
  responsible: string;
  grossAmount: string;
  currency: "ARS" | "USD";
  fxRate: string;
  status: string;
  receivedAmount: string;
  receiptRefs: string;
  notes: string;
  lines: CaserioLineForm[];
};

type BookingCompositeLineForm = {
  id?: number;
  uid: string;
  lineType: "artista_vpo" | "artista_externo" | "comision_externa";
  description: string;
  artist: string;
  amount: string;
  allocationMode: "manual" | "equal" | "net_percent";
  allocationPercent: string;
  baseAdjustment: string;
  artistPercent: string;
  producerPercent: string;
  artistPaidAmount: string;
  producerReceivedAmount: string;
  showExpenses: BookingExpenseForm[];
  externalShares: BookingExternalShareForm[];
  bookingCommissionExempt: boolean;
  bookingCommissionNotes: string;
  notes: string;
};

type BookingCompositeForm = {
  eventDate: string;
  venue: string;
  city: string;
  responsible: string;
  grossAmount: string;
  currency: "ARS" | "USD";
  fxRate: string;
  status: string;
  receivedAmount: string;
  receiptRefs: string;
  notes: string;
  expenses: BookingExpenseForm[];
  lines: BookingCompositeLineForm[];
};

type BookingLabThirdPartyForm = {
  uid: string;
  name: string;
  role: "manager_externo" | "socio_externo" | "tercero" | "otro";
  basis: "before_split" | "after_split";
  percent: string;
  amount: string;
  cashHandledByVpo: boolean;
  notes: string;
};

type BookingLabLineForm = {
  uid: string;
  lineType: "artista_vpo" | "artista_externo" | "comision_directa";
  description: string;
  artist: string;
  allocationMode: "equal" | "net_percent" | "manual";
  allocationPercent: string;
  amount: string;
  baseAdjustment: string;
  artistPercent: string;
  producerPercent: string;
  artistPaidAmount: string;
  producerReceivedAmount: string;
  showExpenses: BookingExpenseForm[];
  thirdParties: BookingLabThirdPartyForm[];
  bookingCommissionExempt: boolean;
  bookingCommissionNotes: string;
  recoveryEnabled: boolean;
  recoveryMode: "artist_share" | "pre_split" | "producer_share" | "manual";
  recoveryAmount: string;
  recoverySource: string;
  notes: string;
};

type BookingLabForm = {
  eventDate: string;
  venue: string;
  city: string;
  responsible: string;
  grossAmount: string;
  collectedAmount: string;
  currency: "ARS" | "USD";
  fxRate: string;
  status: "borrador" | "observado" | "cerrado" | "cerrado_cc";
  cashMovements: BookingCashMovementForm[];
  expenses: BookingExpenseForm[];
  directCommissions: BookingExpenseForm[];
  lines: BookingLabLineForm[];
  notes: string;
};

type BookingExpenseForm = {
  uid: string;
  concept: string;
  category: string;
  amount: string;
  commissionDestination?: "direct" | "artist_base";
  commissionTargetArtist?: string;
  notes: string;
};

type BookingAdjustmentForm = {
  uid: string;
  concept: string;
  amount: string;
  appliedAmount: string;
  adjustmentType: string;
  area: string;
  impact: string;
  recoverable: boolean;
  artistPercent: string;
  producerPercent: string;
  notes: string;
};

type BookingPreSplitAdjustmentForm = {
  uid: string;
  concept: string;
  destination: "artist" | "producer";
  amount: string;
  notes: string;
};

type BookingExternalShareForm = {
  uid: string;
  name: string;
  role: "manager_externo" | "socio_externo" | "tercero" | "otro";
  percent: string;
  amount: string;
  cashHandledByVpo: boolean;
  notes: string;
};

type BookingCashMovementForm = {
  uid: string;
  recipient: "producer" | "artist";
  concept: string;
  amount: string;
  paymentMethod: "transferencia" | "efectivo" | "seña" | "otro";
  paidBy: string;
  targetArtist?: string;
  notes: string;
};

type BookingForm = {
  artist: string;
  showDate: string;
  venue: string;
  city: string;
  tourManager: string;
  seller: string;
  status: string;
  currency: "ARS" | "USD";
  fxRate: string;
  cachetAmount: string;
  venuePaymentIssue: boolean;
  venueCollectedAmount: string;
  venuePaymentNotes: string;
  showExpenses: BookingExpenseForm[];
  cashMovements: BookingCashMovementForm[];
  preSplitAdjustments: BookingPreSplitAdjustmentForm[];
  externalShares: BookingExternalShareForm[];
  artistPaidAmount: string;
  producerReceivedAmount: string;
  artistPercent: string;
  producerPercent: string;
  bookingCommissionExempt: boolean;
  bookingCommissionNotes: string;
  artistAdjustments: BookingAdjustmentForm[];
  receiptRefs: string;
  notes: string;
};

const PIE_COLORS = ["#17324d", "#0f766e", "#b54708", "#6941c6", "#b42318", "#475467", "#2e90fa"];
const BOOKING_EXPENSE_CATEGORIES = [
  { value: "general", label: "General" },
  { value: "tour_manager", label: "Tour manager" },
  { value: "musicos", label: "Musicos" },
  { value: "sonido", label: "Sonido" },
  { value: "staff_stage", label: "Staff / stage" },
  { value: "animador", label: "Animador" },
  { value: "viaticos", label: "Viaticos" },
  { value: "traslado", label: "Traslado" },
  { value: "hotel", label: "Hotel" },
  { value: "comida", label: "Comida" },
  { value: "produccion", label: "Produccion" },
  { value: "comision_externa", label: "Comision externa" },
  { value: "varios", label: "Varios" },
];
const PARTICIPATION_CACHE_KEY = "vpo_participation_last_result";
const MONTH_NAMES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const MONTH_OPTIONS = Array.from({ length: 11 }, (_, yearIndex) => 2020 + yearIndex)
  .flatMap((year) => MONTH_NAMES.map((month, monthIndex) => {
    const value = `${year}-${String(monthIndex + 1).padStart(2, "0")}`;
    return { value, label: `${month} ${year}` };
  }));

type MonthSelectProps = {
  id: string;
  value: string;
  min?: string | null;
  onChange: (value: string) => void;
};

function filenameFromDisposition(disposition: string | null, fallback: string) {
  if (!disposition) return fallback;
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return match?.[1] || fallback;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function pct(value: number) {
  return `${value.toFixed(1)}%`;
}

function ars(value: number) {
  return new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 0 }).format(value);
}

function localAmount(value: number, currency: string) {
  if (currency === "USD") {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
  }
  return ars(value);
}

function suggestedAmount(value: number, currency: string) {
  const hasCents = Math.abs(value - Math.round(value)) > 0.001;
  if (currency === "USD") {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: hasCents ? 2 : 0,
      maximumFractionDigits: hasCents ? 2 : 0,
    }).format(value);
  }
  return new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: "ARS",
    minimumFractionDigits: hasCents ? 2 : 0,
    maximumFractionDigits: hasCents ? 2 : 0,
  }).format(value);
}

function amountToInput(value: number | null | undefined) {
  return value && value !== 0 ? String(value) : "";
}

function newBookingExpense(category = "general"): BookingExpenseForm {
  return {
    uid: `${Date.now()}-${Math.random()}`,
    concept: "",
    category,
    amount: "",
    commissionDestination: category.startsWith("comision") ? "direct" : undefined,
    commissionTargetArtist: "",
    notes: "",
  };
}

function isCommissionExpense(expense: BookingExpenseForm | BookingCompositeEventExpense) {
  return String(expense.category || "").startsWith("comision");
}

function encodeCommissionNotes(expense: BookingExpenseForm) {
  if (!isCommissionExpense(expense)) return expense.notes || null;

  const meta = {
    kind: "booking_direct_commission",
    destination: expense.commissionDestination || "direct",
    target_artist: expense.commissionTargetArtist || "",
  };
  const userNotes = expense.notes?.trim();
  return [`[vpo-meta]${JSON.stringify(meta)}`, userNotes].filter(Boolean).join("\n");
}

function decodeCommissionNotes(notes: string | null | undefined) {
  const raw = notes || "";
  const [firstLine, ...rest] = raw.split(/\r?\n/);
  if (!firstLine.startsWith("[vpo-meta]")) {
    return {
      commissionDestination: "direct" as const,
      commissionTargetArtist: "",
      notes: raw,
    };
  }

  try {
    const meta = JSON.parse(firstLine.replace("[vpo-meta]", ""));
    return {
      commissionDestination: meta.destination === "artist_base" ? "artist_base" as const : "direct" as const,
      commissionTargetArtist: String(meta.target_artist || ""),
      notes: rest.join("\n"),
    };
  } catch {
    return {
      commissionDestination: "direct" as const,
      commissionTargetArtist: "",
      notes: rest.join("\n") || raw,
    };
  }
}

function newBookingAdjustment(): BookingAdjustmentForm {
  return {
    uid: `${Date.now()}-${Math.random()}`,
    concept: "",
    amount: "",
    appliedAmount: "",
    adjustmentType: "recupero",
    area: "booking",
    impact: "pago_artista",
    recoverable: true,
    artistPercent: "70",
    producerPercent: "30",
    notes: "",
  };
}

function newBookingPreSplitAdjustment(destination: "artist" | "producer" = "producer"): BookingPreSplitAdjustmentForm {
  return {
    uid: `${Date.now()}-${Math.random()}`,
    concept: "",
    destination,
    amount: "",
    notes: "",
  };
}

function newBookingExternalShare(): BookingExternalShareForm {
  return {
    uid: `${Date.now()}-${Math.random()}`,
    name: "",
    role: "tercero",
    percent: "",
    amount: "",
    cashHandledByVpo: false,
    notes: "",
  };
}

function newBookingCashMovement(recipient: "producer" | "artist" = "producer"): BookingCashMovementForm {
  return {
    uid: `${Date.now()}-${Math.random()}`,
    recipient,
    concept: "Seña",
    amount: "",
    paymentMethod: "seña",
    paidBy: "",
    targetArtist: "",
    notes: "",
  };
}

function normalizeCashPaymentMethod(value: string | null | undefined): BookingCashMovementForm["paymentMethod"] {
  if (!value) return "seña";
  if (value === "transferencia" || value === "efectivo" || value === "otro") return value;
  if (value === "seña" || value === "sena" || value === "se?a" || value.includes("±")) return "seña";
  return "otro";
}

function newCaserioLine(lineType: CaserioLineForm["lineType"] = "gasto_general"): CaserioLineForm {
  return {
    uid: `${Date.now()}-${Math.random()}`,
    lineType,
    description: "",
    amount: "",
    artist: "",
    artistPercent: "70",
    producerPercent: "30",
    showExpenses: [],
    notes: "",
  };
}

function newCompositeBookingLine(lineType: BookingCompositeLineForm["lineType"] = "artista_vpo"): BookingCompositeLineForm {
  return {
    uid: `${Date.now()}-${Math.random()}`,
    lineType,
    description: "",
    artist: "",
    amount: "",
    allocationMode: lineType === "artista_vpo" ? "equal" : "manual",
    allocationPercent: "",
    baseAdjustment: "",
    artistPercent: lineType === "artista_vpo" ? "70" : "0",
    producerPercent: lineType === "artista_vpo" ? "30" : "0",
    artistPaidAmount: "",
    producerReceivedAmount: "",
    showExpenses: [],
    externalShares: [],
    bookingCommissionExempt: true,
    bookingCommissionNotes: "",
    notes: "",
  };
}

function newBookingLabThirdParty(basis: BookingLabThirdPartyForm["basis"] = "before_split"): BookingLabThirdPartyForm {
  return {
    uid: `${Date.now()}-${Math.random()}`,
    name: "",
    role: "tercero",
    basis,
    percent: "",
    amount: "",
    cashHandledByVpo: false,
    notes: "",
  };
}

function newBookingLabLine(lineType: BookingLabLineForm["lineType"] = "artista_vpo"): BookingLabLineForm {
  return {
    uid: `${Date.now()}-${Math.random()}`,
    lineType,
    description: "",
    artist: "",
    allocationMode: lineType === "artista_vpo" ? "equal" : "manual",
    allocationPercent: "",
    amount: "",
    baseAdjustment: "",
    artistPercent: lineType === "artista_vpo" ? "70" : "0",
    producerPercent: lineType === "artista_vpo" ? "30" : "0",
    artistPaidAmount: "",
    producerReceivedAmount: "",
    showExpenses: [],
    thirdParties: [],
    bookingCommissionExempt: false,
    bookingCommissionNotes: "",
    recoveryEnabled: false,
    recoveryMode: "artist_share",
    recoveryAmount: "",
    recoverySource: "",
    notes: "",
  };
}

function initialBookingLabForm(): BookingLabForm {
  return {
    eventDate: new Date().toISOString().slice(0, 10),
    venue: "",
    city: "",
    responsible: "",
    grossAmount: "",
    collectedAmount: "",
    currency: "ARS",
    fxRate: "",
    status: "borrador",
    cashMovements: [],
    expenses: [],
    directCommissions: [],
    lines: [newBookingLabLine("artista_vpo")],
    notes: "",
  };
}

function MonthSelect({ id, value, min, onChange }: MonthSelectProps) {
  const options = MONTH_OPTIONS.filter((option) => !min || option.value >= min);

  return (
    <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">Sin limite</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  );
}

export default function Home() {
  const demoMenuOnly = process.env.NEXT_PUBLIC_VPO_MENU_MODE === "demo";
  const [authenticated, setAuthenticated] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [view, setView] = useState<View>("menu");
  const [currentUser, setCurrentUser] = useState<WebUser | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [keywords, setKeywords] = useState("");
  const [startMonth, setStartMonth] = useState("");
  const [endMonth, setEndMonth] = useState("");
  const [periodBasis, setPeriodBasis] = useState("transaction_month");
  const [mode, setMode] = useState("any");
  const [rawLimit, setRawLimit] = useState("5000");
  const [statementMinTotal, setStatementMinTotal] = useState("0");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [statementLoading, setStatementLoading] = useState(false);
  const [participationLoading, setParticipationLoading] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);
  const [lastFile, setLastFile] = useState("");
  const [lastSheetUrl, setLastSheetUrl] = useState("");
  const [participation, setParticipation] = useState<ParticipationData | null>(null);
  const [participationPreset, setParticipationPreset] = useState("last_year");
  const [participationStartMonth, setParticipationStartMonth] = useState("");
  const [participationEndMonth, setParticipationEndMonth] = useState("");
  const [bookingLoading, setBookingLoading] = useState(false);
  const [bookingItems, setBookingItems] = useState<BookingShow[]>([]);
  const [bookingSearch, setBookingSearch] = useState("");
  const [bookingVisibleCount, setBookingVisibleCount] = useState(5);
  const [bookingArtists, setBookingArtists] = useState<string[]>([]);
  const [bookingSummary, setBookingSummary] = useState<BookingSummary | null>(null);
  const [bookingSummaryLoading, setBookingSummaryLoading] = useState(false);
  const [bookingArtistSummary, setBookingArtistSummary] = useState<BookingArtistSummary | null>(null);
  const [bookingArtistSummaryArtist, setBookingArtistSummaryArtist] = useState("");
  const [bookingArtistSummaryLoading, setBookingArtistSummaryLoading] = useState(false);
  const [bookingArtistSummaryLatestOnly, setBookingArtistSummaryLatestOnly] = useState(false);
  const [artistRecords, setArtistRecords] = useState<BookingArtistRecord[]>([]);
  const [artistRecordSearch, setArtistRecordSearch] = useState("");
  const [artistRecordLoading, setArtistRecordLoading] = useState(false);
  const [artistRecordEditingId, setArtistRecordEditingId] = useState<number | null>(null);
  const [artistRecordForm, setArtistRecordForm] = useState<BookingArtistForm>({
    stageName: "",
    legalName: "",
    cuit: "",
    phone: "",
    email: "",
    address: "",
    notes: "",
    active: true,
  });
  const [caserioLoading, setCaserioLoading] = useState(false);
  const [caserioEvents, setCaserioEvents] = useState<CaserioEvent[]>([]);
  const [compositeBookingEvents, setCompositeBookingEvents] = useState<BookingCompositeEvent[]>([]);
  const [compositeBookingLoading, setCompositeBookingLoading] = useState(false);
  const [compositeBookingEditingId, setCompositeBookingEditingId] = useState<number | null>(null);
  const [compositeBookingForm, setCompositeBookingForm] = useState<BookingCompositeForm>({
    eventDate: new Date().toISOString().slice(0, 10),
    venue: "",
    city: "",
    responsible: "",
    grossAmount: "",
    currency: "ARS",
    fxRate: "",
    status: "borrador",
    receivedAmount: "",
    receiptRefs: "",
    notes: "",
    expenses: [],
    lines: [],
  });
  const [bookingLabForm, setBookingLabForm] = useState<BookingLabForm>(() => initialBookingLabForm());
  const [caserioForm, setCaserioForm] = useState<CaserioForm>({
    eventDate: new Date().toISOString().slice(0, 10),
    venue: "",
    city: "",
    responsible: "",
    grossAmount: "",
    currency: "ARS",
    fxRate: "",
    status: "borrador",
    receivedAmount: "",
    receiptRefs: "",
    notes: "",
    lines: [],
  });
  const [bookingEditingId, setBookingEditingId] = useState<number | null>(null);
  const [bookingForm, setBookingForm] = useState<BookingForm>({
    artist: "",
    showDate: new Date().toISOString().slice(0, 10),
    venue: "",
    city: "",
    tourManager: "",
    seller: "",
    status: "realizado",
    currency: "ARS",
    fxRate: "",
    cachetAmount: "",
    venuePaymentIssue: false,
    venueCollectedAmount: "",
    venuePaymentNotes: "",
    showExpenses: [],
    cashMovements: [],
    preSplitAdjustments: [],
    externalShares: [],
    artistPaidAmount: "",
    producerReceivedAmount: "",
    artistPercent: "70",
    producerPercent: "30",
    bookingCommissionExempt: false,
    bookingCommissionNotes: "",
    artistAdjustments: [],
    receiptRefs: "",
    notes: "",
  });

  useEffect(() => {
    fetch("/api/session")
      .then((response) => response.json())
      .then((data) => {
        setAuthenticated(Boolean(data.authenticated));
        setCurrentUser(data.user || null);
      })
      .catch(() => {
        setAuthenticated(false);
        setCurrentUser(null);
      })
      .finally(() => setCheckingSession(false));
  }, []);

  useEffect(() => {
    if (authenticated && view === "participation" && !participation) {
      const cached = loadParticipationCache();
      if (cached) {
        setParticipation(cached.data);
        setParticipationPreset(cached.preset);
        setParticipationStartMonth(cached.startMonth);
        setParticipationEndMonth(cached.endMonth);
        return;
      }

      loadParticipation(false);
    }
  }, [authenticated, view, participation]);

  useEffect(() => {
    if (authenticated && view === "booking") {
      loadBookingArtists();
      loadBookingShows();
    }
  }, [authenticated, view]);

  useEffect(() => {
    setBookingVisibleCount(5);
  }, [bookingSearch]);

  useEffect(() => {
    if (authenticated && view === "artists") {
      loadArtistRecords();
    }
  }, [authenticated, view]);

  useEffect(() => {
    if (authenticated && view === "caserio") {
      loadBookingArtists();
      loadCaserioEvents();
    }
  }, [authenticated, view]);

  useEffect(() => {
    if (authenticated && view === "composite-booking") {
      loadBookingArtists();
      loadCompositeBookingEvents();
    }
  }, [authenticated, view]);

  useEffect(() => {
    if (authenticated && view === "booking-lab") {
      loadBookingArtists();
    }
  }, [authenticated, view]);

  useEffect(() => {
    if (authenticated && view === "booking-summary") {
      loadBookingSummary();
    }
  }, [authenticated, view]);

  useEffect(() => {
    if (authenticated && view === "booking-artist-summary") {
      loadBookingArtistSummary();
    }
  }, [authenticated, view, bookingArtistSummaryArtist]);

  const pieStyle = useMemo(() => {
    if (!participation?.items.length) return { background: "#e4e7ec" };

    let cursor = 0;
    const parts = participation.items.map((item, idx) => {
      const start = cursor;
      const end = cursor + item.percentage;
      cursor = end;
      return `${PIE_COLORS[idx % PIE_COLORS.length]} ${start}% ${end}%`;
    });

    return { background: `conic-gradient(${parts.join(", ")})` };
  }, [participation]);

  const bookingFxRate = parseMoneyInput(bookingForm.fxRate);
  const caserioFxRate = parseMoneyInput(caserioForm.fxRate);
  const compositeBookingFxRate = parseMoneyInput(compositeBookingForm.fxRate);
  const bookingLabFxRate = parseMoneyInput(bookingLabForm.fxRate);

  const bookingExpenseTotal = useMemo(() => {
    return bookingForm.showExpenses.reduce((total, expense) => (
      total + parseAmountInput(expense.amount, bookingFxRate)
    ), 0);
  }, [bookingForm.showExpenses, bookingFxRate]);

  const bookingPreSplitSummary = useMemo(() => {
    return bookingForm.preSplitAdjustments.reduce((totals, adjustment) => {
      const amount = parseAmountInput(adjustment.amount, bookingFxRate);
      totals.total += amount;
      if (adjustment.destination === "artist") {
        totals.artist += amount;
      } else {
        totals.producer += amount;
      }
      return totals;
    }, { total: 0, artist: 0, producer: 0 });
  }, [bookingForm.preSplitAdjustments, bookingFxRate]);

  const bookingCashSummary = useMemo(() => {
    return bookingForm.cashMovements.reduce((totals, movement) => {
      const amount = parseAmountInput(movement.amount, bookingFxRate);
      if (movement.recipient === "artist") {
        totals.artist += amount;
      } else {
        totals.producer += amount;
      }
      totals.total += amount;
      return totals;
    }, { artist: 0, producer: 0, total: 0 });
  }, [bookingForm.cashMovements, bookingFxRate]);

  const bookingEffectiveCachet = useMemo(() => {
    if (!bookingForm.venuePaymentIssue) {
      return parseAmountInput(bookingForm.cachetAmount, bookingFxRate);
    }
    return parseAmountInput(bookingForm.venueCollectedAmount, bookingFxRate);
  }, [bookingForm.cachetAmount, bookingForm.venueCollectedAmount, bookingForm.venuePaymentIssue, bookingFxRate]);

  const bookingVenueBalance = useMemo(() => {
    if (!bookingForm.venuePaymentIssue) return 0;
    return Math.max(0, parseAmountInput(bookingForm.cachetAmount, bookingFxRate) - parseAmountInput(bookingForm.venueCollectedAmount, bookingFxRate));
  }, [bookingForm.cachetAmount, bookingForm.venueCollectedAmount, bookingForm.venuePaymentIssue, bookingFxRate]);

  const bookingSuggestion = useMemo(() => {
    const cachet = bookingEffectiveCachet;
    const expenses = bookingExpenseTotal;
    const artistPercent = parseMoneyInput(bookingForm.artistPercent);
    const producerPercent = bookingForm.producerPercent
      ? parseMoneyInput(bookingForm.producerPercent)
      : Math.max(0, 100 - artistPercent);
    const net = cachet - expenses;
    const splitBase = net - bookingPreSplitSummary.total;

    return {
      net,
      splitBase,
      artistShare: splitBase * artistPercent / 100,
      producerShare: splitBase * producerPercent / 100,
    };
  }, [
    bookingEffectiveCachet,
    bookingExpenseTotal,
    bookingPreSplitSummary.total,
    bookingForm.artistPercent,
    bookingForm.producerPercent,
  ]);

  const bookingExternalShareSummary = useMemo(() => {
    return bookingForm.externalShares.reduce((totals, share) => {
      const percent = parseMoneyInput(share.percent);
      const manualAmount = parseAmountInput(share.amount, bookingFxRate);
      const amount = manualAmount > 0 ? manualAmount : bookingSuggestion.splitBase * percent / 100;
      if (amount <= 0) return totals;

      totals.amount += amount;
      totals.percent += percent;
      if (share.cashHandledByVpo) {
        totals.cashHandled += amount;
      }
      return totals;
    }, { amount: 0, percent: 0, cashHandled: 0 });
  }, [bookingForm.externalShares, bookingSuggestion.splitBase, bookingFxRate]);

  const bookingAdjustmentSuggestion = useMemo(() => {
    return bookingForm.artistAdjustments.reduce((totals, adjustment) => {
      const amount = parseAmountInput(adjustment.amount, bookingFxRate);
      const appliedAmount = parseAmountInput(adjustment.appliedAmount, bookingFxRate);
      const artistPercent = parseMoneyInput(adjustment.artistPercent);
      const producerPercent = adjustment.producerPercent
        ? parseMoneyInput(adjustment.producerPercent)
        : Math.max(0, 100 - artistPercent);

      totals.amount += amount;
      totals.appliedAmount += appliedAmount;
      totals.artistAmount += amount * artistPercent / 100;
      totals.producerAmount += amount * producerPercent / 100;
      return totals;
    }, { amount: 0, appliedAmount: 0, artistAmount: 0, producerAmount: 0 });
  }, [bookingForm.artistAdjustments, bookingFxRate]);

  const bookingFinalSuggestion = useMemo(() => {
    return {
      artistPayable: bookingSuggestion.artistShare + bookingPreSplitSummary.artist - bookingAdjustmentSuggestion.appliedAmount,
      producerCash: bookingSuggestion.producerShare + bookingPreSplitSummary.producer + bookingAdjustmentSuggestion.appliedAmount,
      externalShares: bookingExternalShareSummary.amount,
    };
  }, [bookingSuggestion, bookingPreSplitSummary, bookingAdjustmentSuggestion, bookingExternalShareSummary.amount]);

  const bookingSplitPercentSummary = useMemo(() => {
    const artistPercent = parseMoneyInput(bookingForm.artistPercent);
    const producerPercent = bookingForm.producerPercent ? parseMoneyInput(bookingForm.producerPercent) : 0;
    const externalPercent = bookingExternalShareSummary.percent;
    const assignedPercent = artistPercent + producerPercent + externalPercent;

    return {
      artistPercent,
      producerPercent,
      externalPercent,
      assignedPercent,
      remainingPercent: Math.max(0, 100 - artistPercent - externalPercent),
      overAssignedPercent: Math.max(0, assignedPercent - 100),
    };
  }, [bookingForm.artistPercent, bookingForm.producerPercent, bookingExternalShareSummary.percent]);

  const bookingControl = useMemo(() => {
    const pending = bookingItems.filter((item) => {
      const status = item.settlement_status || "pendiente";
      const venueStatus = item.venue_payment_status || "cobrado";
      return status === "pendiente" || status === "parcial" || venueStatus === "parcial" || venueStatus === "no_cobrado" || Math.abs(item.venue_balance_amount || 0) > 0.01;
    });
    const closed = bookingItems.filter((item) => {
      const status = item.settlement_status || "pendiente";
      return status === "cerrado" && Math.abs(item.balance_producer_amount || 0) <= 0.01;
    });
    const historical = bookingItems.filter((item) => (item.settlement_status || "") === "historico");

    return {
      totalShows: bookingItems.length,
      closedShows: closed.length,
      historicalShows: historical.length,
      pendingShows: pending.length,
      pendingAmount: pending.reduce((total, item) => total + Math.max(0, item.balance_producer_amount || 0) + Math.max(0, item.venue_balance_amount || 0), 0),
      venueDebtAmount: bookingItems.reduce((total, item) => total + Math.max(0, item.venue_balance_amount || 0), 0),
      pending: pending.slice(0, 12),
    };
  }, [bookingItems]);

  const filteredBookingItems = useMemo(() => {
    const query = bookingSearch.trim().toLowerCase();
    if (!query) return bookingItems;

    return bookingItems.filter((item) => [
      item.id,
      item.artist,
      item.show_date,
      item.venue,
      item.city,
      item.tour_manager,
      item.status,
      item.settlement_status,
      item.settlement_group,
      item.venue_payment_status,
      item.venue_payment_notes,
      item.notes,
    ].some((value) => String(value || "").toLowerCase().includes(query)));
  }, [bookingItems, bookingSearch]);

  const visibleBookingItems = useMemo(() => {
    return filteredBookingItems.slice(0, bookingVisibleCount);
  }, [filteredBookingItems, bookingVisibleCount]);

  const visibleBookingArtistSummaryItems = useMemo(() => {
    const items = bookingArtistSummary?.items || [];
    return bookingArtistSummaryLatestOnly ? items.slice(0, 5) : items;
  }, [bookingArtistSummary, bookingArtistSummaryLatestOnly]);

  const filteredArtistRecords = useMemo(() => {
    const query = artistRecordSearch.trim().toLowerCase();
    if (!query) return artistRecords;

    return artistRecords.filter((item) => [
      item.stage_name,
      item.legal_name,
      item.cuit,
      item.phone,
      item.email,
      item.address,
      item.notes,
      item.active ? "activo" : "inactivo",
    ].some((value) => String(value || "").toLowerCase().includes(query)));
  }, [artistRecords, artistRecordSearch]);

  const caserioPreview = useMemo(() => {
    const gross = parseAmountInput(caserioForm.grossAmount, caserioFxRate);
    const linesTotal = caserioForm.lines.reduce((total, line) => total + parseAmountInput(line.amount, caserioFxRate), 0);
    const producerExpected = caserioForm.lines.reduce((total, line) => {
      if (line.lineType !== "artista_vpo") return total;
      const cachet = parseAmountInput(line.amount, caserioFxRate);
      const expenses = line.showExpenses.reduce((sum, expense) => sum + parseAmountInput(expense.amount, caserioFxRate), 0);
      const producerPercent = line.producerPercent ? parseMoneyInput(line.producerPercent) : Math.max(0, 100 - parseMoneyInput(line.artistPercent));
      return total + Math.max(0, cachet - expenses) * producerPercent / 100;
    }, 0);
    const caserioExpected = gross - linesTotal;
    const totalExpected = caserioExpected + producerExpected;
    const received = parseAmountInput(caserioForm.receivedAmount, caserioFxRate);

    return {
      caserioExpected,
      producerExpected,
      totalExpected,
      balance: totalExpected - received,
    };
  }, [caserioForm, caserioFxRate]);

  const compositeBookingPreview = useMemo(() => {
    const gross = parseAmountInput(compositeBookingForm.grossAmount, compositeBookingFxRate);
    const operationalExpenses = compositeBookingForm.expenses
      .filter((expense) => !isCommissionExpense(expense))
      .reduce((total, expense) => total + parseAmountInput(expense.amount, compositeBookingFxRate), 0);
    const directCommissions = compositeBookingForm.expenses
      .filter((expense) => isCommissionExpense(expense))
      .reduce((total, expense) => total + parseAmountInput(expense.amount, compositeBookingFxRate), 0);
    const incorporatedCommissionsByArtist = compositeBookingForm.expenses
      .filter((expense) => isCommissionExpense(expense) && expense.commissionDestination === "artist_base" && expense.commissionTargetArtist)
      .reduce<Record<string, number>>((items, expense) => {
        const artist = String(expense.commissionTargetArtist || "").trim();
        if (!artist) return items;
        items[artist] = (items[artist] || 0) + parseAmountInput(expense.amount, compositeBookingFxRate);
        return items;
      }, {});
    const incorporatedCommissions = Object.values(incorporatedCommissionsByArtist).reduce((total, amount) => total + amount, 0);
    const artistBase = gross - operationalExpenses - directCommissions;
    const linePool = artistBase + incorporatedCommissions;
    const equalLines = compositeBookingForm.lines.filter((line) => line.lineType === "artista_vpo" && line.allocationMode === "equal").length;
    const equalShare = equalLines > 0 ? artistBase / equalLines : 0;
    const lineAmounts = compositeBookingForm.lines.reduce<Record<string, number>>((amounts, line) => {
      const commissionAdjustment = incorporatedCommissionsByArtist[line.artist] || 0;
      const adjustment = parseAmountInput(line.baseAdjustment, compositeBookingFxRate) + commissionAdjustment;
      if (line.lineType === "artista_vpo" && line.allocationMode === "equal") {
        amounts[line.uid] = equalShare + adjustment;
      } else if (line.lineType === "artista_vpo" && line.allocationMode === "net_percent") {
        amounts[line.uid] = artistBase * parseMoneyInput(line.allocationPercent) / 100 + adjustment;
      } else {
        amounts[line.uid] = parseAmountInput(line.amount, compositeBookingFxRate);
      }
      return amounts;
    }, {});
    const allocated = compositeBookingForm.lines.reduce((total, line) => total + (lineAmounts[line.uid] || 0), 0);
    const producerExpected = compositeBookingForm.lines.reduce((total, line) => {
      if (line.lineType !== "artista_vpo") return total;
      const amount = lineAmounts[line.uid] || 0;
      const showExpenses = line.showExpenses.reduce((sum, expense) => sum + parseAmountInput(expense.amount, compositeBookingFxRate), 0);
      const producerPercent = line.producerPercent ? parseMoneyInput(line.producerPercent) : Math.max(0, 100 - parseMoneyInput(line.artistPercent));
      return total + Math.max(0, amount - showExpenses) * producerPercent / 100;
    }, 0);
    const received = parseAmountInput(compositeBookingForm.receivedAmount, compositeBookingFxRate);

    return {
      gross,
      eventExpenses: operationalExpenses + directCommissions,
      operationalExpenses,
      directCommissions,
      incorporatedCommissions,
      incorporatedCommissionsByArtist,
      artistBase,
      linePool,
      equalShare,
      lineAmounts,
      allocated,
      unallocated: linePool - allocated,
      producerExpected,
      received,
      balance: producerExpected - received,
    };
  }, [compositeBookingForm, compositeBookingFxRate]);

  const compositeBookingSaveMode = useMemo(() => {
    if (compositeBookingEditingId) return "composite";
    const vpoLines = compositeBookingForm.lines.filter((line) => line.lineType === "artista_vpo");
    const externalArtistLines = compositeBookingForm.lines.filter((line) => line.lineType === "artista_externo");
    if (vpoLines.length === 1 && externalArtistLines.length === 0) return "simple";
    return "composite";
  }, [compositeBookingEditingId, compositeBookingForm.lines]);

  const bookingLabPreview = useMemo(() => {
    const gross = parseAmountInput(bookingLabForm.grossAmount, bookingLabFxRate);
    const collected = bookingLabForm.collectedAmount
      ? parseAmountInput(bookingLabForm.collectedAmount, bookingLabFxRate)
      : gross;
    const eventExpenses = bookingLabForm.expenses.reduce((total, expense) => total + parseAmountInput(expense.amount, bookingLabFxRate), 0);
    const directCommissions = bookingLabForm.directCommissions.reduce((total, commission) => total + parseAmountInput(commission.amount, bookingLabFxRate), 0);
    const incorporatedCommissionsByArtist = bookingLabForm.directCommissions
      .filter((commission) => commission.commissionDestination === "artist_base" && commission.commissionTargetArtist)
      .reduce<Record<string, number>>((items, commission) => {
        const artist = String(commission.commissionTargetArtist || "").trim();
        if (!artist) return items;
        items[artist] = (items[artist] || 0) + parseAmountInput(commission.amount, bookingLabFxRate);
        return items;
      }, {});
    const incorporatedCommissions = Object.values(incorporatedCommissionsByArtist).reduce((total, amount) => total + amount, 0);
    const eventBase = collected - eventExpenses - directCommissions;
    const linePool = eventBase + incorporatedCommissions;
    const equalLines = bookingLabForm.lines.filter((line) => line.lineType === "artista_vpo" && line.allocationMode === "equal").length;
    const equalShare = equalLines > 0 ? eventBase / equalLines : 0;
    const vpoLineArtists = bookingLabForm.lines
      .filter((line) => line.lineType === "artista_vpo" && line.artist)
      .map((line) => line.artist);
    const singleVpoArtist = vpoLineArtists.length === 1 ? vpoLineArtists[0] : "";
    const movementAppliesToArtist = (movement: BookingCashMovementForm, artist: string) => {
      if (!artist) return false;
      const targetArtist = String(movement.targetArtist || "").trim();
      if (targetArtist) return targetArtist === artist;
      return Boolean(singleVpoArtist && singleVpoArtist === artist);
    };
    const cashSummary = bookingLabForm.cashMovements.reduce((totals, movement) => {
      const amount = parseAmountInput(movement.amount, bookingLabFxRate);
      if (movement.recipient === "producer") totals.producer += amount;
      if (movement.recipient === "artist") totals.artist += amount;
      if (!movement.targetArtist && vpoLineArtists.length > 1) totals.unassigned += amount;
      totals.total += amount;
      return totals;
    }, { producer: 0, artist: 0, total: 0, unassigned: 0 });

    const linePreviews = bookingLabForm.lines.reduce<Record<string, {
      lineBase: number;
      lineExpenses: number;
      preSplitThirdParties: number;
      afterSplitThirdParties: number;
      recoveryAmount: number;
      baseBeforeSplit: number;
      splitBase: number;
      artistSuggested: number;
      producerSuggested: number;
      artistCashReceived: number;
      producerCashReceived: number;
      artistPaid: number;
      producerReceived: number;
      artistBalance: number;
      producerBalance: number;
      commissionableBase: number;
      lineBalance: number;
    }>>((items, line) => {
      const adjustment = parseAmountInput(line.baseAdjustment, bookingLabFxRate) + (incorporatedCommissionsByArtist[line.artist] || 0);
      let lineBase = parseAmountInput(line.amount, bookingLabFxRate);
      if (line.lineType === "artista_vpo" && line.allocationMode === "equal") {
        lineBase = equalShare + adjustment;
      } else if (line.lineType === "artista_vpo" && line.allocationMode === "net_percent") {
        lineBase = eventBase * parseMoneyInput(line.allocationPercent) / 100 + adjustment;
      } else {
        lineBase += adjustment;
      }

      const lineExpenses = line.showExpenses.reduce((total, expense) => total + parseAmountInput(expense.amount, bookingLabFxRate), 0);
      const baseBeforeSplit = lineBase - lineExpenses;
      const preSplitThirdParties = line.thirdParties
        .filter((thirdParty) => thirdParty.basis === "before_split")
        .reduce((total, thirdParty) => {
          const manual = parseAmountInput(thirdParty.amount, bookingLabFxRate);
          return total + (manual > 0 ? manual : baseBeforeSplit * parseMoneyInput(thirdParty.percent) / 100);
        }, 0);
      const splitBaseBeforeRecovery = baseBeforeSplit - preSplitThirdParties;
      const recoveryAmount = line.recoveryEnabled ? parseAmountInput(line.recoveryAmount, bookingLabFxRate) : 0;
      const splitBase = line.recoveryMode === "pre_split"
        ? splitBaseBeforeRecovery - recoveryAmount
        : splitBaseBeforeRecovery;
      const afterSplitThirdParties = line.thirdParties
        .filter((thirdParty) => thirdParty.basis === "after_split")
        .reduce((total, thirdParty) => {
          const manual = parseAmountInput(thirdParty.amount, bookingLabFxRate);
          return total + (manual > 0 ? manual : splitBase * parseMoneyInput(thirdParty.percent) / 100);
        }, 0);
      const artistGross = splitBase * parseMoneyInput(line.artistPercent) / 100;
      const producerGross = splitBase * parseMoneyInput(line.producerPercent) / 100;
      const artistSuggested = line.recoveryMode === "artist_share" ? artistGross - recoveryAmount : artistGross;
      const producerSuggested = line.recoveryMode === "producer_share" ? producerGross - recoveryAmount : producerGross;
      const artistCashReceived = bookingLabForm.cashMovements
        .filter((movement) => movement.recipient === "artist" && movementAppliesToArtist(movement, line.artist))
        .reduce((total, movement) => total + parseAmountInput(movement.amount, bookingLabFxRate), 0);
      const producerCashReceived = bookingLabForm.cashMovements
        .filter((movement) => movement.recipient === "producer" && movementAppliesToArtist(movement, line.artist))
        .reduce((total, movement) => total + parseAmountInput(movement.amount, bookingLabFxRate), 0);
      const artistPaid = parseAmountInput(line.artistPaidAmount, bookingLabFxRate) + artistCashReceived;
      const producerReceived = parseAmountInput(line.producerReceivedAmount, bookingLabFxRate) + producerCashReceived;

      items[line.uid] = {
        lineBase,
        lineExpenses,
        preSplitThirdParties,
        afterSplitThirdParties,
        recoveryAmount,
        baseBeforeSplit,
        splitBase,
        artistSuggested,
        producerSuggested,
        artistCashReceived,
        producerCashReceived,
        artistPaid,
        producerReceived,
        artistBalance: artistSuggested - artistPaid,
        producerBalance: producerSuggested - producerReceived,
        commissionableBase: line.bookingCommissionExempt ? 0 : producerSuggested,
        lineBalance: splitBase - artistSuggested - producerSuggested - afterSplitThirdParties,
      };
      return items;
    }, {});

    const allocated = Object.values(linePreviews).reduce((total, item) => total + item.lineBase, 0);
    const indyanaExpected = Object.values(linePreviews).reduce((total, item) => total + item.producerSuggested, 0);
    const commissionableBase = Object.values(linePreviews).reduce((total, item) => total + item.commissionableBase, 0);
    const thirdPartyExpected = Object.values(linePreviews).reduce((total, item) => total + item.preSplitThirdParties + item.afterSplitThirdParties, 0);
    const recoveryApplied = Object.values(linePreviews).reduce((total, item) => total + item.recoveryAmount, 0);
    const artistExpected = Object.values(linePreviews).reduce((total, item) => total + item.artistSuggested, 0);
    const artistBalance = Object.values(linePreviews).reduce((total, item) => total + item.artistBalance, 0);
    const producerBalance = Object.values(linePreviews).reduce((total, item) => total + item.producerBalance, 0);
    const eventCashToSettle = collected - cashSummary.total;

    return {
      gross,
      collected,
      eventExpenses,
      directCommissions,
      incorporatedCommissions,
      incorporatedCommissionsByArtist,
      cashSummary,
      eventBase,
      linePool,
      equalShare,
      allocated,
      unallocated: linePool - allocated,
      indyanaExpected,
      artistExpected,
      commissionableBase,
      nonCommissionableBase: indyanaExpected - commissionableBase,
      thirdPartyExpected,
      recoveryApplied,
      artistBalance,
      producerBalance,
      eventCashToSettle,
      venueBalance: gross - collected,
      linePreviews,
    };
  }, [bookingLabForm, bookingLabFxRate]);

  const bookingLabMode = useMemo(() => {
    const artistLines = bookingLabForm.lines.filter((line) => line.lineType === "artista_vpo" || line.lineType === "artista_externo");
    const vpoLines = bookingLabForm.lines.filter((line) => line.lineType === "artista_vpo");
    const hasAdvancedRules = (
      bookingLabForm.directCommissions.length > 0 ||
      bookingLabForm.lines.some((line) => (
        line.thirdParties.length > 0 ||
        line.recoveryEnabled ||
        line.bookingCommissionExempt ||
        line.showExpenses.length > 0
      ))
    );

    if (artistLines.length <= 1 && vpoLines.length === 1) {
      return {
        kind: "simple",
        label: hasAdvancedRules ? "Show simple con reglas avanzadas" : "Show simple",
        detail: "Un solo artista VPO. Puede tener gastos, terceros, comisiones o recuperos sin convertirse en evento madre.",
      };
    }

    if (artistLines.length > 1) {
      return {
        kind: "mother",
        label: `Evento madre con ${artistLines.length} lineas`,
        detail: "Hay mas de un artista/linea artistica. El sistema deberia crear una madre y shows internos por artista VPO.",
      };
    }

    return {
      kind: "draft",
      label: "Borrador sin artista VPO",
      detail: "Agrega un artista VPO para que el sistema pueda clasificar la carga.",
    };
  }, [bookingLabForm.directCommissions.length, bookingLabForm.lines]);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setLoading(true);

    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo ingresar." }));
      setMessage({ type: "error", text: data.error || "No se pudo ingresar." });
      setLoading(false);
      return;
    }

    const data = await response.json();
    setAuthenticated(true);
    setCurrentUser(data.user || null);
    setUsername("");
    setPassword("");
    setLoading(false);
  }

  async function logout() {
    await fetch("/api/logout", { method: "POST" });
    setAuthenticated(false);
    setCurrentUser(null);
    setUsername("");
    setView("menu");
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");
  }

  function buildPayload(output: "excel" | "google_sheet") {
    return {
      keywords: keywords.split(/[;,]/).map((item) => item.trim()).filter(Boolean),
      start_month: startMonth || null,
      end_month: endMonth || null,
      period_basis: periodBasis,
      mode,
      raw_limit: Number(rawLimit) || 0,
      refresh_cache: false,
      output,
    };
  }

  function validatePeriod() {
    if (startMonth && endMonth && startMonth > endMonth) {
      setMessage({ type: "error", text: "El periodo desde no puede ser mayor que hasta." });
      return false;
    }
    return true;
  }

  async function generateExcel() {
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");

    if (!validatePeriod()) return;
    setLoading(true);

    const response = await fetch("/api/report-link", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload("excel")),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo generar el reporte." }));
      setMessage({ type: "error", text: data.error || "No se pudo generar el reporte." });
      setLoading(false);
      return;
    }

    const data = await response.json();
    if (data.url) {
      window.location.href = data.url;
    }
    setLastFile("Descarga directa iniciada");
    setMessage({ type: "ok", text: "Reporte solicitado. La descarga se abre directo desde Cloud Run." });
    setLoading(false);
  }

  async function createGoogleSheet(event?: MouseEvent<HTMLButtonElement>) {
    event?.preventDefault();
    event?.stopPropagation();
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");

    if (!validatePeriod()) return;
    setGoogleLoading(true);

    const response = await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload("google_sheet")),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo crear el Google Sheet." }));
      setMessage({ type: "error", text: data.error || "No se pudo crear el Google Sheet." });
      setGoogleLoading(false);
      return;
    }

    const data = await response.json();
    setLastSheetUrl(data.url);
    if (data.url) window.open(data.url, "_blank", "noopener,noreferrer");
    setMessage({ type: "ok", text: "Google Sheet creado correctamente." });
    setGoogleLoading(false);
  }

  async function generateStatementReport() {
    setMessage(null);
    setStatementLoading(true);

    const response = await fetch("/api/statement", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        refresh_cache: false,
        min_artist_total_usd: Number(statementMinTotal) || 0,
      }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo generar el reporte por statement." }));
      setMessage({ type: "error", text: data.error || "No se pudo generar el reporte por statement." });
      setStatementLoading(false);
      return;
    }

    const blob = await response.blob();
    const filename = filenameFromDisposition(response.headers.get("content-disposition"), "vpo_statement_report.xlsx");
    downloadBlob(blob, filename);
    setLastFile(filename);
    setMessage({ type: "ok", text: "Reporte por statement generado correctamente." });
    setStatementLoading(false);
  }

  function loadParticipationCache(): ParticipationCache | null {
    try {
      const raw = window.localStorage.getItem(PARTICIPATION_CACHE_KEY);
      if (!raw) return null;

      const cached = JSON.parse(raw) as ParticipationCache;
      if (!cached?.data?.items) return null;

      return cached;
    } catch {
      return null;
    }
  }

  function saveParticipationCache(data: ParticipationData) {
    try {
      window.localStorage.setItem(
        PARTICIPATION_CACHE_KEY,
        JSON.stringify({
          data,
          preset: participationPreset,
          startMonth: participationStartMonth,
          endMonth: participationEndMonth,
        }),
      );
    } catch {
      // Si el navegador bloquea localStorage, la torta sigue funcionando sin cache.
    }
  }

  async function loadParticipation(refresh: boolean) {
    setMessage(null);

    if (
      participationPreset === "custom"
      && participationStartMonth
      && participationEndMonth
      && participationStartMonth > participationEndMonth
    ) {
      setMessage({ type: "error", text: "El periodo desde no puede ser mayor que hasta." });
      return;
    }

    setParticipationLoading(true);

    const params = new URLSearchParams({
      refresh: refresh ? "1" : "0",
      preset: participationPreset,
    });

    if (participationPreset === "custom") {
      if (participationStartMonth) params.set("start_month", participationStartMonth);
      if (participationEndMonth) params.set("end_month", participationEndMonth);
    }

    const response = await fetch(`/api/participation?${params.toString()}`, { cache: "no-store" });
    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo cargar participacion." }));
      setMessage({ type: "error", text: data.error || "No se pudo cargar participacion." });
      setParticipationLoading(false);
      return;
    }

    const data = await response.json();
    setParticipation(data);
    saveParticipationCache(data);
    setParticipationLoading(false);
  }

  function updateBookingField<K extends keyof BookingForm>(key: K, value: BookingForm[K]) {
    setBookingForm((current) => ({ ...current, [key]: value }));
  }

  function addBookingExpense(category = "general") {
    setBookingForm((current) => ({
      ...current,
      showExpenses: [...current.showExpenses, newBookingExpense(category)],
    }));
  }

  function removeBookingExpense(uid: string) {
    setBookingForm((current) => ({
      ...current,
      showExpenses: current.showExpenses.filter((expense) => expense.uid !== uid),
    }));
  }

  function updateBookingExpenseField<K extends keyof BookingExpenseForm>(
    uid: string,
    key: K,
    value: BookingExpenseForm[K],
  ) {
    setBookingForm((current) => ({
      ...current,
      showExpenses: current.showExpenses.map((expense) => (
        expense.uid === uid ? { ...expense, [key]: value } : expense
      )),
    }));
  }

  function addBookingCashMovement(recipient: "producer" | "artist" = "producer") {
    setBookingForm((current) => ({
      ...current,
      cashMovements: [...current.cashMovements, newBookingCashMovement(recipient)],
    }));
  }

  function removeBookingCashMovement(uid: string) {
    setBookingForm((current) => ({
      ...current,
      cashMovements: current.cashMovements.filter((movement) => movement.uid !== uid),
    }));
  }

  function updateBookingCashMovementField<K extends keyof BookingCashMovementForm>(
    uid: string,
    key: K,
    value: BookingCashMovementForm[K],
  ) {
    setBookingForm((current) => ({
      ...current,
      cashMovements: current.cashMovements.map((movement) => (
        movement.uid === uid ? { ...movement, [key]: value } : movement
      )),
    }));
  }

  function addBookingAdjustment() {
    setBookingForm((current) => ({
      ...current,
      artistAdjustments: [...current.artistAdjustments, newBookingAdjustment()],
    }));
  }

  function removeBookingAdjustment(uid: string) {
    setBookingForm((current) => ({
      ...current,
      artistAdjustments: current.artistAdjustments.filter((adjustment) => adjustment.uid !== uid),
    }));
  }

  function addBookingPreSplitAdjustment(destination: "artist" | "producer" = "producer") {
    setBookingForm((current) => ({
      ...current,
      preSplitAdjustments: [...current.preSplitAdjustments, newBookingPreSplitAdjustment(destination)],
    }));
  }

  function removeBookingPreSplitAdjustment(uid: string) {
    setBookingForm((current) => ({
      ...current,
      preSplitAdjustments: current.preSplitAdjustments.filter((adjustment) => adjustment.uid !== uid),
    }));
  }

  function updateBookingPreSplitAdjustmentField<K extends keyof BookingPreSplitAdjustmentForm>(
    uid: string,
    key: K,
    value: BookingPreSplitAdjustmentForm[K],
  ) {
    setBookingForm((current) => ({
      ...current,
      preSplitAdjustments: current.preSplitAdjustments.map((adjustment) => (
        adjustment.uid === uid ? { ...adjustment, [key]: value } : adjustment
      )),
    }));
  }

  function addBookingExternalShare() {
    setBookingForm((current) => ({
      ...current,
      externalShares: [...current.externalShares, newBookingExternalShare()],
    }));
  }

  function removeBookingExternalShare(uid: string) {
    setBookingForm((current) => ({
      ...current,
      externalShares: current.externalShares.filter((share) => share.uid !== uid),
    }));
  }

  function updateBookingExternalShareField<K extends keyof BookingExternalShareForm>(
    uid: string,
    key: K,
    value: BookingExternalShareForm[K],
  ) {
    setBookingForm((current) => ({
      ...current,
      externalShares: current.externalShares.map((share) => (
        share.uid === uid ? { ...share, [key]: value } : share
      )),
    }));
  }

  function updateBookingAdjustmentField<K extends keyof BookingAdjustmentForm>(
    uid: string,
    key: K,
    value: BookingAdjustmentForm[K],
  ) {
    setBookingForm((current) => ({
      ...current,
      artistAdjustments: current.artistAdjustments.map((adjustment) => (
        adjustment.uid === uid ? { ...adjustment, [key]: value } : adjustment
      )),
    }));
  }

  function parseMoneyInput(value: string) {
    const raw = String(value || "")
      .replace(/\s/g, "")
      .replace(/\$/g, "")
      .trim();
    if (!raw) return 0;

    const lastComma = raw.lastIndexOf(",");
    const lastDot = raw.lastIndexOf(".");
    let normalized = raw;

    if (lastComma >= 0 && lastDot >= 0) {
      const decimalSeparator = lastComma > lastDot ? "," : ".";
      const thousandsSeparator = decimalSeparator === "," ? "." : ",";
      normalized = raw
        .replace(new RegExp(`\\${thousandsSeparator}`, "g"), "")
        .replace(decimalSeparator, ".");
    } else if (lastComma >= 0) {
      normalized = raw.replace(/\./g, "").replace(",", ".");
    } else if (lastDot >= 0) {
      const dotCount = (raw.match(/\./g) || []).length;
      const decimals = raw.length - lastDot - 1;
      normalized = dotCount === 1 && decimals > 0 && decimals <= 2
        ? raw
        : raw.replace(/\./g, "");
    }

    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function isUsdAmountInput(value: string) {
    return /^\s*(u\$|us\$|usd)\s*/i.test(String(value || ""));
  }

  function stripUsdPrefix(value: string) {
    return String(value || "").replace(/^\s*(u\$|us\$|usd)\s*/i, "");
  }

  function parseAmountInput(value: string, fxRate: number) {
    const amount = parseMoneyInput(stripUsdPrefix(value));
    if (!isUsdAmountInput(value)) return amount;
    return fxRate > 0 ? amount * fxRate : 0;
  }

  function collectBookingAmountInputs() {
    return [
      bookingForm.cachetAmount,
      bookingForm.venueCollectedAmount,
      bookingForm.artistPaidAmount,
      bookingForm.producerReceivedAmount,
      ...bookingForm.showExpenses.map((expense) => expense.amount),
      ...bookingForm.cashMovements.map((movement) => movement.amount),
      ...bookingForm.preSplitAdjustments.map((adjustment) => adjustment.amount),
      ...bookingForm.externalShares.map((share) => share.amount),
      ...bookingForm.artistAdjustments.flatMap((adjustment) => [adjustment.amount, adjustment.appliedAmount]),
    ];
  }

  function needsFxRate(values: string[]) {
    return values.some((value) => isUsdAmountInput(value));
  }

  async function loadBookingShows() {
    const response = await fetch("/api/booking", { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    setBookingItems(data.items || []);
    setBookingVisibleCount(5);
  }

  async function loadBookingSummary() {
    setBookingSummaryLoading(true);
    const response = await fetch("/api/booking/summary", { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      setBookingSummary(data);
    }
    setBookingSummaryLoading(false);
  }

  async function loadBookingArtistSummary() {
    setBookingArtistSummaryLoading(true);
    const params = new URLSearchParams();
    if (bookingArtistSummaryArtist) params.set("artist", bookingArtistSummaryArtist);
    const response = await fetch(`/api/booking/artist-summary${params.toString() ? `?${params.toString()}` : ""}`, { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      setBookingArtistSummary(data);
      if (!bookingArtistSummaryArtist && data.artists?.length === 1) {
        setBookingArtistSummaryArtist(data.artists[0]);
      }
    }
    setBookingArtistSummaryLoading(false);
  }

  async function loadBookingArtists() {
    const response = await fetch("/api/booking/artists", { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    setBookingArtists(data.items || []);
  }

  async function loadArtistRecords() {
    const response = await fetch("/api/booking/artist-records", { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    setArtistRecords(data.items || []);
  }

  async function loadCaserioEvents() {
    const response = await fetch("/api/caserio/events", { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    setCaserioEvents(data.items || []);
  }

  async function loadCompositeBookingEvents() {
    setCompositeBookingLoading(true);
    const response = await fetch("/api/booking/composite-events", { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      setCompositeBookingEvents(data.items || []);
    }
    setCompositeBookingLoading(false);
  }

  function updateCompositeBookingField<K extends keyof BookingCompositeForm>(key: K, value: BookingCompositeForm[K]) {
    setCompositeBookingForm((current) => ({ ...current, [key]: value }));
  }

  function addCompositeBookingExpense(category = "general") {
    setCompositeBookingForm((current) => ({
      ...current,
      expenses: [...current.expenses, newBookingExpense(category)],
    }));
  }

  function removeCompositeBookingExpense(uid: string) {
    setCompositeBookingForm((current) => ({
      ...current,
      expenses: current.expenses.filter((expense) => expense.uid !== uid),
    }));
  }

  function updateCompositeBookingExpenseField<K extends keyof BookingExpenseForm>(uid: string, key: K, value: BookingExpenseForm[K]) {
    setCompositeBookingForm((current) => ({
      ...current,
      expenses: current.expenses.map((expense) => (
        expense.uid === uid
          ? {
            ...expense,
            [key]: value,
            ...(key === "category" && String(value || "").startsWith("comision")
              ? { commissionDestination: expense.commissionDestination || "direct" }
              : {}),
            ...(key === "category" && !String(value || "").startsWith("comision")
              ? { commissionDestination: undefined, commissionTargetArtist: "" }
              : {}),
          }
          : expense
      )),
    }));
  }

  function addCompositeBookingLine(lineType: BookingCompositeLineForm["lineType"] = "artista_vpo") {
    setCompositeBookingForm((current) => ({
      ...current,
      lines: [...current.lines, newCompositeBookingLine(lineType)],
    }));
  }

  function removeCompositeBookingLine(uid: string) {
    setCompositeBookingForm((current) => ({
      ...current,
      lines: current.lines.filter((line) => line.uid !== uid),
    }));
  }

  function updateCompositeBookingLineField<K extends keyof BookingCompositeLineForm>(
    uid: string,
    key: K,
    value: BookingCompositeLineForm[K],
  ) {
    setCompositeBookingForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (line.uid === uid ? { ...line, [key]: value } : line)),
    }));
  }

  function addCompositeBookingLineExpense(uid: string) {
    setCompositeBookingForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === uid ? { ...line, showExpenses: [...line.showExpenses, newBookingExpense()] } : line
      )),
    }));
  }

  function removeCompositeBookingLineExpense(lineUid: string, expenseUid: string) {
    setCompositeBookingForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === lineUid
          ? { ...line, showExpenses: line.showExpenses.filter((expense) => expense.uid !== expenseUid) }
          : line
      )),
    }));
  }

  function updateCompositeBookingLineExpenseField<K extends keyof BookingExpenseForm>(
    lineUid: string,
    expenseUid: string,
    key: K,
    value: BookingExpenseForm[K],
  ) {
    setCompositeBookingForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === lineUid
          ? {
            ...line,
            showExpenses: line.showExpenses.map((expense) => (
              expense.uid === expenseUid ? { ...expense, [key]: value } : expense
            )),
          }
          : line
      )),
    }));
  }

  function addCompositeBookingLineExternalShare(uid: string) {
    setCompositeBookingForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === uid ? { ...line, externalShares: [...line.externalShares, newBookingExternalShare()] } : line
      )),
    }));
  }

  function removeCompositeBookingLineExternalShare(lineUid: string, shareUid: string) {
    setCompositeBookingForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === lineUid
          ? { ...line, externalShares: line.externalShares.filter((share) => share.uid !== shareUid) }
          : line
      )),
    }));
  }

  function updateCompositeBookingLineExternalShareField<K extends keyof BookingExternalShareForm>(
    lineUid: string,
    shareUid: string,
    key: K,
    value: BookingExternalShareForm[K],
  ) {
    setCompositeBookingForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === lineUid
          ? {
            ...line,
            externalShares: line.externalShares.map((share) => (
              share.uid === shareUid ? { ...share, [key]: value } : share
            )),
          }
          : line
      )),
    }));
  }

  function updateBookingLabField<K extends keyof BookingLabForm>(key: K, value: BookingLabForm[K]) {
    setBookingLabForm((current) => ({ ...current, [key]: value }));
  }

  function addBookingLabExpense(target: "expenses" | "directCommissions", category = "general") {
    setBookingLabForm((current) => ({
      ...current,
      [target]: [...current[target], newBookingExpense(category)],
    }));
  }

  function removeBookingLabExpense(target: "expenses" | "directCommissions", uid: string) {
    setBookingLabForm((current) => ({
      ...current,
      [target]: current[target].filter((expense) => expense.uid !== uid),
    }));
  }

  function updateBookingLabExpenseField<K extends keyof BookingExpenseForm>(
    target: "expenses" | "directCommissions",
    uid: string,
    key: K,
    value: BookingExpenseForm[K],
  ) {
    setBookingLabForm((current) => ({
      ...current,
      [target]: current[target].map((expense) => (expense.uid === uid ? { ...expense, [key]: value } : expense)),
    }));
  }

  function addBookingLabLine(lineType: BookingLabLineForm["lineType"] = "artista_vpo") {
    setBookingLabForm((current) => ({
      ...current,
      lines: [...current.lines, newBookingLabLine(lineType)],
    }));
  }

  function removeBookingLabLine(uid: string) {
    setBookingLabForm((current) => ({
      ...current,
      lines: current.lines.filter((line) => line.uid !== uid),
    }));
  }

  function updateBookingLabLineField<K extends keyof BookingLabLineForm>(uid: string, key: K, value: BookingLabLineForm[K]) {
    setBookingLabForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (line.uid === uid ? { ...line, [key]: value } : line)),
    }));
  }

  function addBookingLabLineExpense(lineUid: string, category = "general") {
    setBookingLabForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === lineUid ? { ...line, showExpenses: [...line.showExpenses, newBookingExpense(category)] } : line
      )),
    }));
  }

  function removeBookingLabLineExpense(lineUid: string, expenseUid: string) {
    setBookingLabForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === lineUid
          ? { ...line, showExpenses: line.showExpenses.filter((expense) => expense.uid !== expenseUid) }
          : line
      )),
    }));
  }

  function updateBookingLabLineExpenseField<K extends keyof BookingExpenseForm>(
    lineUid: string,
    expenseUid: string,
    key: K,
    value: BookingExpenseForm[K],
  ) {
    setBookingLabForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === lineUid
          ? {
            ...line,
            showExpenses: line.showExpenses.map((expense) => (
              expense.uid === expenseUid ? { ...expense, [key]: value } : expense
            )),
          }
          : line
      )),
    }));
  }

  function addBookingLabThirdParty(lineUid: string, basis: BookingLabThirdPartyForm["basis"] = "before_split") {
    setBookingLabForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === lineUid ? { ...line, thirdParties: [...line.thirdParties, newBookingLabThirdParty(basis)] } : line
      )),
    }));
  }

  function removeBookingLabThirdParty(lineUid: string, thirdPartyUid: string) {
    setBookingLabForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === lineUid
          ? { ...line, thirdParties: line.thirdParties.filter((thirdParty) => thirdParty.uid !== thirdPartyUid) }
          : line
      )),
    }));
  }

  function updateBookingLabThirdPartyField<K extends keyof BookingLabThirdPartyForm>(
    lineUid: string,
    thirdPartyUid: string,
    key: K,
    value: BookingLabThirdPartyForm[K],
  ) {
    setBookingLabForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === lineUid
          ? {
            ...line,
            thirdParties: line.thirdParties.map((thirdParty) => (
              thirdParty.uid === thirdPartyUid ? { ...thirdParty, [key]: value } : thirdParty
            )),
          }
          : line
      )),
    }));
  }

  function addBookingLabCashMovement(recipient: "producer" | "artist" = "producer") {
    setBookingLabForm((current) => ({
      ...current,
      cashMovements: [...current.cashMovements, newBookingCashMovement(recipient)],
    }));
  }

  function removeBookingLabCashMovement(uid: string) {
    setBookingLabForm((current) => ({
      ...current,
      cashMovements: current.cashMovements.filter((movement) => movement.uid !== uid),
    }));
  }

  function updateBookingLabCashMovementField<K extends keyof BookingCashMovementForm>(
    uid: string,
    key: K,
    value: BookingCashMovementForm[K],
  ) {
    setBookingLabForm((current) => ({
      ...current,
      cashMovements: current.cashMovements.map((movement) => (
        movement.uid === uid ? { ...movement, [key]: value } : movement
      )),
    }));
  }

  function resetBookingLabForm() {
    setBookingLabForm(initialBookingLabForm());
  }

  function resetCompositeBookingForm() {
    setCompositeBookingEditingId(null);
    setCompositeBookingForm({
      eventDate: new Date().toISOString().slice(0, 10),
      venue: "",
      city: "",
      responsible: "",
      grossAmount: "",
      currency: "ARS",
      fxRate: "",
      status: "borrador",
      receivedAmount: "",
      receiptRefs: "",
      notes: "",
      expenses: [],
      lines: [],
    });
  }

  async function submitCompositeBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCompositeBookingLoading(true);
    setMessage(null);

    const compositeAmountInputs = [
      compositeBookingForm.grossAmount,
      compositeBookingForm.receivedAmount,
      ...compositeBookingForm.expenses.map((expense) => expense.amount),
      ...compositeBookingForm.lines.flatMap((line) => [
        line.amount,
        line.baseAdjustment,
        line.artistPaidAmount,
        line.producerReceivedAmount,
        ...line.showExpenses.map((expense) => expense.amount),
        ...line.externalShares.map((share) => share.amount),
      ]),
    ];
    if (needsFxRate(compositeAmountInputs) && compositeBookingFxRate <= 0) {
      setMessage({ type: "error", text: "Para cargar importes en USD con u$, primero cargá el tipo de cambio de la liquidación." });
      setCompositeBookingLoading(false);
      return;
    }

    const vpoLines = compositeBookingForm.lines.filter((line) => line.lineType === "artista_vpo");
    const externalArtistLines = compositeBookingForm.lines.filter((line) => line.lineType === "artista_externo");
    const legacyCommissionLines = compositeBookingForm.lines.filter((line) => line.lineType === "comision_externa");
    const shouldSaveAsSimpleShow = !compositeBookingEditingId && vpoLines.length === 1 && externalArtistLines.length === 0;

    if (shouldSaveAsSimpleShow) {
      const line = vpoLines[0];
      if (!line.artist) {
        setMessage({ type: "error", text: "Para guardar como show simple desde beta, elegi el artista de la linea." });
        setCompositeBookingLoading(false);
        return;
      }
      const lineAmount = compositeBookingPreview.lineAmounts[line.uid] || 0;
      const eventExpensesNotes = compositeBookingForm.expenses
        .filter((expense) => parseAmountInput(expense.amount, compositeBookingFxRate) > 0)
        .map((expense) => {
          const amount = parseAmountInput(expense.amount, compositeBookingFxRate);
          const destination = isCommissionExpense(expense)
            ? ` | destino: ${expense.commissionDestination === "artist_base" ? `incorpora a ${expense.commissionTargetArtist || "linea"}` : "salida directa"}`
            : "";
          return `- ${expense.concept || "Gasto"}: ${amount}${destination}`;
        });
      const statusMap: Record<string, string> = {
        borrador: "realizado",
        rendido: "rendido",
        observado: "realizado",
        cerrado: "aprobado",
      };
      const lineNotes = [
        "Creado desde Carga de Shows beta como show simple, sin evento madre.",
        `Bruto/contexto informado: ${parseAmountInput(compositeBookingForm.grossAmount, compositeBookingFxRate)}`,
        legacyCommissionLines.length > 0
          ? `Lineas antiguas de comision directa tomadas como contexto:\n${legacyCommissionLines.map((commission) => `- ${commission.description || "Comision"}: ${parseAmountInput(commission.amount, compositeBookingFxRate)}`).join("\n")}`
          : "",
        eventExpensesNotes.length > 0 ? `Gastos/comisiones usados para calcular la base:\n${eventExpensesNotes.join("\n")}` : "",
        compositeBookingForm.notes || "",
        line.notes || "",
      ].filter(Boolean).join("\n\n");

      const response = await fetch("/api/booking", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          artist: line.artist,
          show_date: compositeBookingForm.eventDate,
          venue: compositeBookingForm.venue,
          city: compositeBookingForm.city || null,
          tour_manager: compositeBookingForm.responsible || null,
          status: statusMap[compositeBookingForm.status] || "realizado",
          currency: compositeBookingForm.currency,
          fx_rate: compositeBookingForm.fxRate ? compositeBookingFxRate : null,
          contracted_cachet_amount: lineAmount,
          venue_collected_amount: lineAmount,
          venue_payment_status: "cobrado",
          cachet_amount: lineAmount,
          show_expenses: line.showExpenses
            .filter((expense) => parseAmountInput(expense.amount, compositeBookingFxRate) > 0)
            .map((expense) => ({
              concept: expense.concept || "Gasto",
              category: expense.category || "general",
              amount: parseAmountInput(expense.amount, compositeBookingFxRate),
              notes: expense.notes || null,
            })),
          external_shares: line.externalShares
            .map((share) => ({
              name: share.name.trim(),
              role: share.role,
              percent: share.percent ? parseMoneyInput(share.percent) : null,
              amount: parseAmountInput(share.amount, compositeBookingFxRate),
              cash_handled_by_vpo: share.cashHandledByVpo,
              notes: share.notes || null,
            }))
            .filter((share) => share.name && (share.amount > 0 || (share.percent || 0) > 0)),
          artist_paid_amount: parseAmountInput(line.artistPaidAmount, compositeBookingFxRate),
          producer_received_amount: parseAmountInput(line.producerReceivedAmount, compositeBookingFxRate),
          artist_percent: parseMoneyInput(line.artistPercent),
          producer_percent: line.producerPercent ? parseMoneyInput(line.producerPercent) : null,
          booking_commission_exempt: line.bookingCommissionExempt,
          booking_commission_notes: line.bookingCommissionNotes || null,
          receipt_refs: compositeBookingForm.receiptRefs.split(/\r?\n/).map((value) => value.trim()).filter(Boolean),
          notes: lineNotes,
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({ error: "No se pudo guardar el show simple desde beta." }));
        setMessage({ type: "error", text: data.error || "No se pudo guardar el show simple desde beta." });
        setCompositeBookingLoading(false);
        return;
      }

      const data = await response.json();
      setBookingItems((current) => [data.item, ...current].slice(0, 30));
      resetCompositeBookingForm();
      loadBookingShows();
      setMessage({ type: "ok", text: "Show simple guardado desde beta. No se creo evento madre." });
      setCompositeBookingLoading(false);
      return;
    }

    const response = await fetch(
      compositeBookingEditingId ? `/api/booking/composite-events?id=${compositeBookingEditingId}` : "/api/booking/composite-events",
      {
      method: compositeBookingEditingId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_date: compositeBookingForm.eventDate,
        venue: compositeBookingForm.venue,
        city: compositeBookingForm.city || null,
        responsible: compositeBookingForm.responsible || null,
        gross_amount: parseAmountInput(compositeBookingForm.grossAmount, compositeBookingFxRate),
        currency: compositeBookingForm.currency,
        fx_rate: compositeBookingForm.fxRate ? compositeBookingFxRate : null,
        status: compositeBookingForm.status,
        received_amount: parseAmountInput(compositeBookingForm.receivedAmount, compositeBookingFxRate),
        receipt_refs: compositeBookingForm.receiptRefs.split(/\r?\n/).map((value) => value.trim()).filter(Boolean),
        notes: compositeBookingForm.notes || null,
        expenses: compositeBookingForm.expenses
          .filter((expense) => parseAmountInput(expense.amount, compositeBookingFxRate) > 0)
          .map((expense) => ({
            concept: expense.concept || "Gasto",
            category: expense.category || "general",
            amount: parseAmountInput(expense.amount, compositeBookingFxRate),
            notes: encodeCommissionNotes(expense),
          })),
        lines: compositeBookingForm.lines.map((line) => ({
          id: line.id || null,
          line_type: line.lineType,
          description: line.description,
          artist: line.artist || null,
          amount: compositeBookingPreview.lineAmounts[line.uid],
          artist_percent: parseMoneyInput(line.artistPercent),
          producer_percent: line.producerPercent ? parseMoneyInput(line.producerPercent) : null,
          artist_paid_amount: parseAmountInput(line.artistPaidAmount, compositeBookingFxRate),
          producer_received_amount: parseAmountInput(line.producerReceivedAmount, compositeBookingFxRate),
          show_expenses: line.showExpenses
            .filter((expense) => parseAmountInput(expense.amount, compositeBookingFxRate) > 0)
            .map((expense) => ({
              concept: expense.concept || "Gasto",
              category: expense.category || "general",
              amount: parseAmountInput(expense.amount, compositeBookingFxRate),
              notes: expense.notes || null,
            })),
          external_shares: line.externalShares
            .map((share) => ({
              name: share.name.trim(),
              role: share.role,
              percent: share.percent ? parseMoneyInput(share.percent) : null,
              amount: parseAmountInput(share.amount, compositeBookingFxRate),
              cash_handled_by_vpo: share.cashHandledByVpo,
              notes: share.notes || null,
            }))
            .filter((share) => share.name && (share.amount > 0 || (share.percent || 0) > 0)),
          booking_commission_exempt: line.bookingCommissionExempt,
          booking_commission_notes: line.bookingCommissionNotes || null,
          notes: line.notes || null,
        })),
      }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo guardar la liquidacion compuesta." }));
      setMessage({ type: "error", text: data.error || "No se pudo guardar la liquidacion compuesta." });
      setCompositeBookingLoading(false);
      return;
    }

    const data = await response.json();
    setCompositeBookingEvents((current) => (
      compositeBookingEditingId
        ? current.map((item) => (item.id === data.item.id ? data.item : item))
        : [data.item, ...current]
    ));
    resetCompositeBookingForm();
    loadBookingShows();
    setMessage({
      type: "ok",
      text: compositeBookingEditingId
        ? "Liquidacion compuesta actualizada. Los shows hijos existentes se preservaron."
        : "Liquidacion compuesta creada y shows internos generados cuando correspondia.",
    });
    setCompositeBookingLoading(false);
  }

  function editCompositeBookingEvent(event: BookingCompositeEvent) {
    const vpoLines = event.lines.filter((line) => line.line_type === "artista_vpo");
    const equalShare = vpoLines.length > 0 ? event.artist_base_amount / vpoLines.length : 0;
    setCompositeBookingEditingId(event.id);
    setCompositeBookingForm({
      eventDate: event.event_date,
      venue: event.venue,
      city: event.city || "",
      responsible: event.responsible || "",
      grossAmount: amountToInput(event.gross_amount),
      currency: event.currency,
      fxRate: "",
      status: event.status,
      receivedAmount: amountToInput(event.received_amount),
      receiptRefs: event.receipt_refs.join("\n"),
      notes: event.notes || "",
      expenses: event.expenses.map((expense) => ({
        ...(() => {
          const decoded = decodeCommissionNotes(expense.notes);
          return {
            uid: `composite-expense-${expense.id}-${Date.now()}`,
            concept: expense.concept || "",
            category: expense.category || "general",
            amount: amountToInput(expense.amount),
            commissionDestination: isCommissionExpense(expense) ? decoded.commissionDestination : undefined,
            commissionTargetArtist: isCommissionExpense(expense) ? decoded.commissionTargetArtist : "",
            notes: decoded.notes || "",
          };
        })(),
      })),
      lines: event.lines.map((line) => ({
        id: line.id,
        uid: `composite-line-${line.id}-${Date.now()}`,
        lineType: line.line_type as BookingCompositeLineForm["lineType"],
        description: line.description || "",
        artist: line.artist || "",
        allocationMode: line.line_type === "artista_vpo" && vpoLines.length > 1 ? "equal" : "manual",
        allocationPercent: "",
        baseAdjustment: line.line_type === "artista_vpo" && vpoLines.length > 1
          ? amountToInput(line.amount - equalShare)
          : "",
        amount: line.line_type === "artista_vpo" && vpoLines.length > 1 ? "" : amountToInput(line.amount),
        artistPercent: amountToInput(line.artist_percent),
        producerPercent: amountToInput(line.producer_percent),
        artistPaidAmount: amountToInput(line.artist_paid_amount),
        producerReceivedAmount: amountToInput(line.producer_received_amount),
        showExpenses: (line.show_expenses || []).map((expense) => ({
          uid: `composite-line-expense-${line.id}-${expense.id}-${Date.now()}`,
          category: expense.category || "general",
          concept: expense.concept || "",
          amount: amountToInput(expense.amount),
          notes: expense.notes || "",
        })),
        externalShares: (line.external_shares || []).map((share) => ({
          uid: `composite-line-share-${line.id}-${share.id}-${Date.now()}`,
          name: share.name || "",
          role: share.role as BookingExternalShareForm["role"],
          percent: share.percent === null || share.percent === undefined ? "" : amountToInput(share.percent),
          amount: amountToInput(share.amount),
          cashHandledByVpo: Boolean(share.cash_handled_by_vpo),
          notes: share.notes || "",
        })),
        bookingCommissionExempt: Boolean(line.booking_commission_exempt),
        bookingCommissionNotes: line.booking_commission_notes || "",
        notes: line.notes || "",
      })),
    });
    setMessage({
      type: "ok",
      text: `Editando liquidacion compuesta #${event.id}. Guardar actualiza la madre y preserva los shows hijos existentes.`,
    });
  }

  function updateCaserioField<K extends keyof CaserioForm>(key: K, value: CaserioForm[K]) {
    setCaserioForm((current) => ({ ...current, [key]: value }));
  }

  function addCaserioLine(lineType: CaserioLineForm["lineType"] = "gasto_general") {
    setCaserioForm((current) => ({
      ...current,
      lines: [...current.lines, newCaserioLine(lineType)],
    }));
  }

  function removeCaserioLine(uid: string) {
    setCaserioForm((current) => ({
      ...current,
      lines: current.lines.filter((line) => line.uid !== uid),
    }));
  }

  function updateCaserioLineField<K extends keyof CaserioLineForm>(uid: string, key: K, value: CaserioLineForm[K]) {
    setCaserioForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (line.uid === uid ? { ...line, [key]: value } : line)),
    }));
  }

  function addCaserioLineExpense(uid: string) {
    setCaserioForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === uid ? { ...line, showExpenses: [...line.showExpenses, newBookingExpense()] } : line
      )),
    }));
  }

  function removeCaserioLineExpense(lineUid: string, expenseUid: string) {
    setCaserioForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === lineUid
          ? { ...line, showExpenses: line.showExpenses.filter((expense) => expense.uid !== expenseUid) }
          : line
      )),
    }));
  }

  function updateCaserioLineExpenseField<K extends keyof BookingExpenseForm>(
    lineUid: string,
    expenseUid: string,
    key: K,
    value: BookingExpenseForm[K],
  ) {
    setCaserioForm((current) => ({
      ...current,
      lines: current.lines.map((line) => (
        line.uid === lineUid
          ? {
            ...line,
            showExpenses: line.showExpenses.map((expense) => (
              expense.uid === expenseUid ? { ...expense, [key]: value } : expense
            )),
          }
          : line
      )),
    }));
  }

  function resetCaserioForm() {
    setCaserioForm({
      eventDate: new Date().toISOString().slice(0, 10),
      venue: "",
      city: "",
      responsible: "",
      grossAmount: "",
      currency: "ARS",
      fxRate: "",
      status: "borrador",
      receivedAmount: "",
      receiptRefs: "",
      notes: "",
      lines: [],
    });
  }

  async function submitCaserio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCaserioLoading(true);
    setMessage(null);

    const caserioAmountInputs = [
      caserioForm.grossAmount,
      caserioForm.receivedAmount,
      ...caserioForm.lines.flatMap((line) => [
        line.amount,
        ...line.showExpenses.map((expense) => expense.amount),
      ]),
    ];
    if (needsFxRate(caserioAmountInputs) && caserioFxRate <= 0) {
      setMessage({ type: "error", text: "Para cargar importes en USD con u$, primero cargá el tipo de cambio del evento." });
      setCaserioLoading(false);
      return;
    }

    const response = await fetch("/api/caserio/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_date: caserioForm.eventDate,
        venue: caserioForm.venue,
        city: caserioForm.city || null,
        responsible: caserioForm.responsible || null,
        gross_amount: parseAmountInput(caserioForm.grossAmount, caserioFxRate),
        currency: caserioForm.currency,
        fx_rate: caserioForm.fxRate ? caserioFxRate : null,
        status: caserioForm.status,
        received_amount: parseAmountInput(caserioForm.receivedAmount, caserioFxRate),
        receipt_refs: caserioForm.receiptRefs.split(/\r?\n/).map((value) => value.trim()).filter(Boolean),
        notes: caserioForm.notes || null,
        lines: caserioForm.lines.map((line) => ({
          line_type: line.lineType,
          description: line.description,
          amount: parseAmountInput(line.amount, caserioFxRate),
          artist: line.artist || null,
          artist_percent: parseMoneyInput(line.artistPercent),
          producer_percent: line.producerPercent ? parseMoneyInput(line.producerPercent) : null,
          show_expenses: line.showExpenses
            .filter((expense) => parseAmountInput(expense.amount, caserioFxRate) > 0)
            .map((expense) => ({
              concept: expense.concept || null,
              category: expense.category,
              amount: parseAmountInput(expense.amount, caserioFxRate),
              notes: expense.notes || null,
            })),
          notes: line.notes || null,
        })),
      }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo guardar el evento Caserio." }));
      setMessage({ type: "error", text: data.error || "No se pudo guardar el evento Caserio." });
      setCaserioLoading(false);
      return;
    }

    const data = await response.json();
    setCaserioEvents((current) => [data.item, ...current]);
    resetCaserioForm();
    loadBookingShows();
    setMessage({ type: "ok", text: "Evento Caserio creado y shows VPO vinculados cuando correspondia." });
    setCaserioLoading(false);
  }

  function updateArtistRecordField<K extends keyof BookingArtistForm>(key: K, value: BookingArtistForm[K]) {
    setArtistRecordForm((current) => ({ ...current, [key]: value }));
  }

  function resetArtistRecordForm() {
    setArtistRecordEditingId(null);
    setArtistRecordForm({
      stageName: "",
      legalName: "",
      cuit: "",
      phone: "",
      email: "",
      address: "",
      notes: "",
      active: true,
    });
  }

  function editArtistRecord(item: BookingArtistRecord) {
    setArtistRecordEditingId(item.id);
    setArtistRecordForm({
      stageName: item.stage_name,
      legalName: item.legal_name || "",
      cuit: item.cuit || "",
      phone: item.phone || "",
      email: item.email || "",
      address: item.address || "",
      notes: item.notes || "",
      active: item.active,
    });
  }

  async function submitArtistRecord(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setArtistRecordLoading(true);
    setMessage(null);

    const response = await fetch(
      artistRecordEditingId ? `/api/booking/artist-records?id=${artistRecordEditingId}` : "/api/booking/artist-records",
      {
        method: artistRecordEditingId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stage_name: artistRecordForm.stageName,
          legal_name: artistRecordForm.legalName || null,
          cuit: artistRecordForm.cuit || null,
          phone: artistRecordForm.phone || null,
          email: artistRecordForm.email || null,
          address: artistRecordForm.address || null,
          notes: artistRecordForm.notes || null,
          active: artistRecordForm.active,
        }),
      },
    );

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo guardar el artista." }));
      setMessage({ type: "error", text: data.error || "No se pudo guardar el artista." });
      setArtistRecordLoading(false);
      return;
    }

    const data = await response.json();
    const item = data.item as BookingArtistRecord;
    setArtistRecords((current) => {
      if (artistRecordEditingId) {
        return current.map((record) => (record.id === item.id ? item : record));
      }
      return [item, ...current];
    });
    resetArtistRecordForm();
    loadBookingArtists();
    setMessage({ type: "ok", text: artistRecordEditingId ? "Artista actualizado correctamente." : "Artista creado correctamente." });
    setArtistRecordLoading(false);
  }

  async function deactivateArtistRecord(item: BookingArtistRecord) {
    setArtistRecordLoading(true);
    setMessage(null);
    const response = await fetch(`/api/booking/artist-records?id=${item.id}`, { method: "DELETE" });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo desactivar el artista." }));
      setMessage({ type: "error", text: data.error || "No se pudo desactivar el artista." });
      setArtistRecordLoading(false);
      return;
    }

    const data = await response.json();
    const updated = data.item as BookingArtistRecord;
    setArtistRecords((current) => current.map((record) => (record.id === updated.id ? updated : record)));
    if (artistRecordEditingId === updated.id) resetArtistRecordForm();
    loadBookingArtists();
    setMessage({ type: "ok", text: "Artista desactivado. Sigue guardado para historial." });
    setArtistRecordLoading(false);
  }

  function resetBookingForm() {
    setBookingEditingId(null);
    setBookingForm((current) => ({
      ...current,
      artist: "",
      showDate: new Date().toISOString().slice(0, 10),
      venue: "",
      city: "",
      tourManager: "",
      seller: "",
      status: "realizado",
      currency: "ARS",
      fxRate: "",
      cachetAmount: "",
      venuePaymentIssue: false,
      venueCollectedAmount: "",
      venuePaymentNotes: "",
      showExpenses: [],
      cashMovements: [],
      preSplitAdjustments: [],
      externalShares: [],
      artistPaidAmount: "",
      producerReceivedAmount: "",
      artistPercent: "70",
      producerPercent: "30",
      bookingCommissionExempt: false,
      bookingCommissionNotes: "",
      artistAdjustments: [],
      receiptRefs: "",
      notes: "",
    }));
  }

  function editBookingShow(item: BookingShow) {
    const hasVenueIssue = (item.venue_payment_status || "cobrado") !== "cobrado" || Math.abs(item.venue_balance_amount || 0) > 0.01;
    const cashMovementForms = (item.cash_movements || []).map((movement) => ({
      uid: `cash-${movement.id}-${Date.now()}`,
      recipient: movement.recipient || "producer",
      concept: movement.concept || "Seña",
      amount: amountToInput(movement.amount),
      paymentMethod: normalizeCashPaymentMethod(movement.payment_method),
      paidBy: movement.paid_by || "",
      notes: movement.notes || "",
    }));
    const cashArtistTotal = cashMovementForms.reduce((total, movement) => total + (movement.recipient === "artist" ? parseMoneyInput(movement.amount) : 0), 0);
    const cashProducerTotal = cashMovementForms.reduce((total, movement) => total + (movement.recipient === "producer" ? parseMoneyInput(movement.amount) : 0), 0);
    setBookingEditingId(item.id);
    setBookingForm({
      artist: item.artist,
      showDate: item.show_date,
      venue: item.venue,
      city: item.city || "",
      tourManager: item.tour_manager || "",
      seller: item.seller || "",
      status: item.status,
      currency: item.currency,
      fxRate: amountToInput(item.fx_rate),
      cachetAmount: amountToInput(item.contracted_cachet_amount || item.cachet_amount),
      venuePaymentIssue: hasVenueIssue,
      venueCollectedAmount: amountToInput(item.venue_collected_amount || item.cachet_amount),
      venuePaymentNotes: item.venue_payment_notes || "",
      showExpenses: item.show_expenses.map((expense) => ({
        uid: `expense-${expense.id}-${Date.now()}`,
        concept: expense.concept || "",
        category: expense.category || "general",
        amount: amountToInput(expense.amount),
        notes: expense.notes || "",
      })),
      cashMovements: cashMovementForms,
      preSplitAdjustments: item.pre_split_adjustments.map((adjustment) => ({
        uid: `pre-split-${adjustment.id}-${Date.now()}`,
        concept: adjustment.concept || "",
        destination: adjustment.destination,
        amount: amountToInput(adjustment.amount),
        notes: adjustment.notes || "",
      })),
      externalShares: (item.external_shares || []).map((share) => ({
        uid: `external-share-${share.id}-${Date.now()}`,
        name: share.name || "",
        role: share.role || "tercero",
        percent: amountToInput(share.percent),
        amount: amountToInput(share.amount),
        cashHandledByVpo: share.cash_handled_by_vpo,
        notes: share.notes || "",
      })),
      artistPaidAmount: amountToInput(Math.max(0, item.artist_paid_amount - cashArtistTotal)),
      producerReceivedAmount: amountToInput(Math.max(0, item.producer_received_amount - cashProducerTotal)),
      artistPercent: String(item.artist_percent),
      producerPercent: String(item.producer_percent),
      bookingCommissionExempt: Boolean(item.booking_commission_exempt),
      bookingCommissionNotes: item.booking_commission_notes || "",
      artistAdjustments: item.artist_adjustments.map((adjustment) => ({
        uid: `adjustment-${adjustment.id}-${Date.now()}`,
        concept: adjustment.concept || "",
        amount: amountToInput(adjustment.amount),
        appliedAmount: amountToInput(adjustment.applied_amount),
        adjustmentType: adjustment.adjustment_type,
        area: adjustment.area,
        impact: adjustment.impact,
        recoverable: adjustment.recoverable,
        artistPercent: String(adjustment.artist_percent),
        producerPercent: String(adjustment.producer_percent),
        notes: adjustment.notes || "",
      })),
      receiptRefs: item.receipt_refs.join("\n"),
      notes: item.notes || "",
    });
    setMessage({ type: "ok", text: `Editando show #${item.id}. Guardar actualiza la carga existente.` });
  }

  async function submitBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setBookingLoading(true);

    if (needsFxRate(collectBookingAmountInputs()) && bookingFxRate <= 0) {
      setMessage({ type: "error", text: "Para cargar importes en USD con u$, primero cargá el tipo de cambio del show." });
      setBookingLoading(false);
      return;
    }

    const receiptRefs = bookingForm.receiptRefs
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
    const contractedCachet = parseAmountInput(bookingForm.cachetAmount, bookingFxRate);
    const venueCollected = bookingForm.venuePaymentIssue
      ? parseAmountInput(bookingForm.venueCollectedAmount, bookingFxRate)
      : contractedCachet;
    const venuePaymentStatus = bookingForm.venuePaymentIssue
      ? (venueCollected <= 0.01 ? "no_cobrado" : "parcial")
      : "cobrado";
    const hasCashMovements = bookingForm.cashMovements.some((movement) => parseAmountInput(movement.amount, bookingFxRate) > 0);
    const cashArtist = bookingCashSummary.artist;
    const cashProducer = bookingCashSummary.producer;

    const response = await fetch(bookingEditingId ? `/api/booking?id=${bookingEditingId}` : "/api/booking", {
      method: bookingEditingId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        artist: bookingForm.artist,
        show_date: bookingForm.showDate,
        venue: bookingForm.venue,
        city: bookingForm.city || null,
        tour_manager: bookingForm.tourManager || null,
        seller: bookingForm.seller || null,
        status: bookingForm.status,
        currency: bookingForm.currency,
        fx_rate: bookingForm.fxRate ? bookingFxRate : null,
        contracted_cachet_amount: contractedCachet,
        venue_collected_amount: venueCollected,
        venue_payment_status: venuePaymentStatus,
        venue_payment_notes: bookingForm.venuePaymentIssue ? bookingForm.venuePaymentNotes || null : null,
        cachet_amount: venueCollected,
        cash_movements: bookingForm.cashMovements
          .map((movement) => ({
            recipient: movement.recipient,
            concept: movement.concept.trim() || "Movimiento de caja",
            amount: parseAmountInput(movement.amount, bookingFxRate),
            payment_method: movement.paymentMethod,
            paid_by: movement.paidBy.trim() || null,
            notes: movement.notes || null,
          }))
          .filter((movement) => movement.amount > 0),
        show_expenses: bookingForm.showExpenses
          .map((expense) => ({
            category: expense.category.trim() || "general",
            concept: expense.concept.trim() || expense.category.trim() || "general",
            amount: parseAmountInput(expense.amount, bookingFxRate),
            notes: expense.notes || null,
          }))
          .filter((expense) => expense.amount > 0),
        pre_split_adjustments: bookingForm.preSplitAdjustments
          .map((adjustment) => ({
            concept: adjustment.concept.trim(),
            destination: adjustment.destination,
            amount: parseAmountInput(adjustment.amount, bookingFxRate),
            notes: adjustment.notes || null,
          }))
          .filter((adjustment) => adjustment.concept && adjustment.amount > 0),
        external_shares: bookingForm.externalShares
          .map((share) => ({
            name: share.name.trim(),
            role: share.role,
            percent: share.percent ? parseMoneyInput(share.percent) : null,
            amount: parseAmountInput(share.amount, bookingFxRate),
            cash_handled_by_vpo: share.cashHandledByVpo,
            notes: share.notes || null,
          }))
          .filter((share) => share.name && ((share.percent ?? 0) > 0 || share.amount > 0)),
        artist_paid_amount: parseAmountInput(bookingForm.artistPaidAmount, bookingFxRate),
        producer_received_amount: parseAmountInput(bookingForm.producerReceivedAmount, bookingFxRate),
        artist_percent: parseMoneyInput(bookingForm.artistPercent),
        producer_percent: bookingForm.producerPercent ? parseMoneyInput(bookingForm.producerPercent) : null,
        booking_commission_exempt: bookingForm.bookingCommissionExempt,
        booking_commission_notes: bookingForm.bookingCommissionExempt ? bookingForm.bookingCommissionNotes || null : null,
        artist_adjustments: bookingForm.artistAdjustments
          .map((adjustment) => ({
            concept: adjustment.concept.trim(),
            amount: parseAmountInput(adjustment.amount, bookingFxRate),
            applied_amount: parseAmountInput(adjustment.appliedAmount, bookingFxRate),
            adjustment_type: adjustment.adjustmentType,
            area: adjustment.area,
            impact: adjustment.impact,
            recoverable: adjustment.recoverable,
            artist_percent: parseMoneyInput(adjustment.artistPercent),
            producer_percent: adjustment.producerPercent ? parseMoneyInput(adjustment.producerPercent) : null,
            notes: adjustment.notes || null,
          }))
          .filter((adjustment) => adjustment.concept && adjustment.amount > 0),
        receipt_refs: receiptRefs,
        notes: bookingForm.notes || null,
      }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo guardar el show." }));
      setMessage({ type: "error", text: data.error || "No se pudo guardar el show." });
      setBookingLoading(false);
      return;
    }

    const data = await response.json();
    setBookingItems((current) => {
      if (bookingEditingId) {
        return current.map((item) => (item.id === data.item.id ? data.item : item));
      }
      return [data.item, ...current].slice(0, 30);
    });
    setBookingVisibleCount(5);
    resetBookingForm();
    setMessage({ type: "ok", text: bookingEditingId ? "Show actualizado correctamente." : "Show cargado correctamente." });
    setBookingLoading(false);
  }

  function submitRoyalties(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    generateExcel();
  }

  function openView(nextView: View) {
    setView(nextView);
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");
  }

  if (checkingSession) {
    return (
      <div className="login">
        <section className="panel">
          <div className="login-brand">
            <span className="brand-vpo">VPO</span>
            <span className="brand-corp">Corp</span>
          </div>
          <p>Validando sesion...</p>
        </section>
      </div>
    );
  }

  if (!authenticated) {
    return (
      <div className="login">
        <form className="panel" onSubmit={login}>
          <div className="login-brand">
            <span className="brand-vpo">VPO</span>
            <span className="brand-corp">Corp</span>
          </div>
          <p className="login-copy">Sistema privado de reportes de regalias digitales.</p>
          {message && <div className={`message ${message.type === "error" ? "error" : ""}`}>{message.text}</div>}
          <label htmlFor="username">Usuario</label>
          <input id="username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
          <label htmlFor="password">Contrasena</label>
          <input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
          <button type="submit" disabled={loading}>{loading ? "Ingresando..." : "Ingresar"}</button>
        </form>
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand" aria-label="VPO Corp">
          <span className="brand-vpo">VPO</span>
          <span className="brand-corp">Corp</span>
        </div>
        <div className="top-actions">
          {currentUser && (
            <span className="session-pill">{currentUser.username} · {currentUser.role}</span>
          )}
          {view !== "menu" && <button type="button" onClick={() => openView("menu")}>Menu</button>}
          <button type="button" onClick={logout}>Salir</button>
        </div>
      </header>

      <main>
        {message && <div className={`message ${message.type === "error" ? "error" : ""}`}>{message.text}</div>}

        {view === "menu" && (
          <>
            <section className="home-hero">
              <div>
                <div className="hero-brand">
                  <span className="brand-vpo">VPO</span>
                  <span className="brand-corp">Corp</span>
                </div>
                <p>Royalty intelligence para reportes, statements y participacion digital.</p>
              </div>
              <div className="hero-stats">
                <span>Marts publicados</span>
                <strong>Live</strong>
              </div>
            </section>

            <div className="menu-grid">
              {!demoMenuOnly && (
                <>
                  <button type="button" className="menu-card" onClick={() => openView("statement")}>
                    <span className="card-index">01</span>
                    <strong>Reporte por statement</strong>
                    <span>Totales por artista, statement y distribuidora.</span>
                  </button>
                  <button type="button" className="menu-card" onClick={() => openView("royalties")}>
                    <span className="card-index">02</span>
                    <strong>Reporte de regalias</strong>
                    <span>Busqueda por palabra clave, periodo, Excel o Google Sheets.</span>
                  </button>
                  <button type="button" className="menu-card" onClick={() => openView("participation")}>
                    <span className="card-index">03</span>
                    <strong>Participacion en distribuidoras</strong>
                    <span>Torta simple por fuente, guardada desde marts publicados.</span>
                  </button>
                  <button type="button" className="menu-card" onClick={() => openView("booking")}>
                    <span className="card-index">04</span>
                    <strong>Booking Indyana</strong>
                    <span>Shows propios: cachet, gastos, split, pagos y comprobantes.</span>
                  </button>
                  <button type="button" className="menu-card" onClick={() => openView("booking-summary")}>
                    <span className="card-index">05</span>
                    <strong>Resumen booking</strong>
                    <span>Indyana por artista y mes, separando base comisionable y excepciones.</span>
                  </button>
                </>
              )}
              <button type="button" className="menu-card" onClick={() => openView("booking-artist-summary")}>
                <span className="card-index">{demoMenuOnly ? "01" : "06"}</span>
                <strong>Detalle Booking</strong>
                <span>Shows por fecha y venue, con cachet, ingreso artista e Indyana.</span>
              </button>
              {!demoMenuOnly && (
                <>
                  <button type="button" className="menu-card" onClick={() => openView("artists")}>
                    <span className="card-index">07</span>
                    <strong>ABM de artistas</strong>
                    <span>Ficha legal, contacto y datos base para booking.</span>
                  </button>
                  <button type="button" className="menu-card" onClick={() => openView("caserio")}>
                    <span className="card-index">08</span>
                    <strong>El Caserio</strong>
                    <span>Eventos sociedad, artistas externos y shows VPO vinculados.</span>
                  </button>
                  <button type="button" className="menu-card" onClick={() => openView("booking-lab")}>
                    <span className="card-index">09</span>
                    <strong>Carga de Shows laboratorio</strong>
                    <span>Flujo dinamico sin guardar: simple, reglas especiales y eventos con varios artistas.</span>
                  </button>
                  <button type="button" className="menu-card" onClick={() => openView("composite-booking")}>
                    <span className="card-index">10</span>
                    <strong>Liquidaciones compuestas</strong>
                    <span>Pantalla actual con guardado de madres/hijas. Usar solo para cargas ya validadas.</span>
                  </button>
                </>
              )}
            </div>
          </>
        )}

        {view === "statement" && (
          <section className="panel">
            <h1>Reporte por statement</h1>
            <p>Genera el reporte historico por statement usando los marts nuevos publicados.</p>
            <label htmlFor="statement_min_total">No mostrar artistas menores a USD</label>
            <input
              id="statement_min_total"
              type="number"
              min="0"
              step="1"
              value={statementMinTotal}
              onChange={(event) => setStatementMinTotal(event.target.value)}
            />
            <p className="field-help">Se aplica por artista dentro de cada distribuidora/cuenta.</p>
            <button type="button" disabled={statementLoading} onClick={generateStatementReport}>
              {statementLoading ? "Generando..." : "Descargar reporte por statement"}
            </button>
            {lastFile && <p className="filename">{lastFile}</p>}
          </section>
        )}

        {view === "royalties" && (
          <div className="grid">
            <form className="panel" onSubmit={submitRoyalties}>
              <h1>Reporte de regalias</h1>
              <label htmlFor="keywords">Palabras clave</label>
              <input id="keywords" value={keywords} onChange={(event) => setKeywords(event.target.value)} placeholder="gusty dj, juli savioli" required />

              <div className="row">
                <div>
                  <label htmlFor="start_month">Desde</label>
                  <MonthSelect id="start_month" value={startMonth} onChange={setStartMonth} />
                </div>
                <div>
                  <label htmlFor="end_month">Hasta</label>
                  <MonthSelect id="end_month" value={endMonth} onChange={setEndMonth} />
                </div>
              </div>

              <label htmlFor="period_basis">Criterio de periodo</label>
              <select id="period_basis" value={periodBasis} onChange={(event) => setPeriodBasis(event.target.value)}>
                <option value="transaction_month">Performance / mes de consumo</option>
                <option value="statement_period">Liquidacion / mes de statement</option>
              </select>

              <label htmlFor="mode">Coincidencia</label>
              <select id="mode" value={mode} onChange={(event) => setMode(event.target.value)}>
                <option value="any">Cualquier palabra</option>
                <option value="all">Todas las palabras</option>
              </select>

              <label htmlFor="raw_limit">Filas raw maximas</label>
              <input id="raw_limit" type="number" min="0" max="50000" value={rawLimit} onChange={(event) => setRawLimit(event.target.value)} />

              <button type="submit" disabled={loading || googleLoading}>{loading ? "Generando..." : "Descargar Excel"}</button>
            </form>

            <div>
              <section className="panel">
                <h2>Google Sheets</h2>
                <p>Crea el mismo reporte como spreadsheet editable en Google Drive.</p>
                <button type="button" disabled={loading || googleLoading} onClick={createGoogleSheet}>
                  {googleLoading ? "Creando..." : "Crear Google Sheet"}
                </button>
              </section>

              {lastFile && (
                <section className="panel" style={{ marginTop: 24 }}>
                  <h2>Ultimo reporte</h2>
                  <p className="filename">{lastFile}</p>
                </section>
              )}

              {lastSheetUrl && (
                <section className="panel" style={{ marginTop: 24 }}>
                  <h2>Google Sheet</h2>
                  <p><a className="button" href={lastSheetUrl} target="_blank" rel="noreferrer">Abrir Google Sheet</a></p>
                </section>
              )}
            </div>
          </div>
        )}

        {view === "participation" && (
          <section className="panel">
            <div className="section-heading">
              <div>
                <h1>Participacion en distribuidoras</h1>
                <p>
                  Ultima actualizacion: {participation?.updated_at || "sin cargar"}
                  {participation?.start_month && participation?.end_month ? ` - ${participation.start_month} a ${participation.end_month}` : ""}
                </p>
              </div>
              <button type="button" onClick={() => loadParticipation(true)} disabled={participationLoading}>
                {participationLoading ? "Actualizando..." : "Actualizar"}
              </button>
            </div>

            <div className="period-controls">
              <div>
                <label htmlFor="participation_preset">Periodo</label>
                <select
                  id="participation_preset"
                  value={participationPreset}
                  onChange={(event) => setParticipationPreset(event.target.value)}
                >
                  <option value="last_month">Ultimo mes</option>
                  <option value="last_3_months">Ultimos tres meses</option>
                  <option value="last_year">Ultimo a?o</option>
                  <option value="all_history">Historico</option>
                  <option value="custom">Rango</option>
                </select>
              </div>

              {participationPreset === "custom" && (
                <>
                  <div>
                    <label htmlFor="participation_start">Desde</label>
                    <MonthSelect
                      id="participation_start"
                      value={participationStartMonth}
                      min={participation?.available_start_month || undefined}
                      onChange={setParticipationStartMonth}
                    />
                  </div>
                  <div>
                    <label htmlFor="participation_end">Hasta</label>
                    <MonthSelect
                      id="participation_end"
                      value={participationEndMonth}
                      min={participation?.available_start_month || undefined}
                      onChange={setParticipationEndMonth}
                    />
                  </div>
                </>
              )}

              <button type="button" onClick={() => loadParticipation(false)} disabled={participationLoading}>
                {participationLoading ? "Cargando..." : "Aplicar"}
              </button>
            </div>

            {participation?.start_date && participation?.end_date && (
              <div className="period-meta">
                <strong>Rango aplicado</strong>
                <span>{participation.start_date} a {participation.end_date}</span>
                <strong>Total</strong>
                <span>{money(participation.total_amount_usd)}</span>
              </div>
            )}

            <div className="pie-layout">
              <div className="pie" style={pieStyle} aria-label="Participacion por distribuidora" />
              <div className="legend">
                {participation?.items.map((item, idx) => (
                  <div className="legend-row" key={item.source}>
                    <span className="swatch" style={{ background: PIE_COLORS[idx % PIE_COLORS.length] }} />
                    <strong>{item.source}</strong>
                    <span>{pct(item.percentage)}</span>
                    <span>{money(item.amount_usd)}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {view === "booking-summary" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Resumen booking</h1>
                <p>Ingreso Indyana por artista y mes. La base comisionable excluye shows con regla especial.</p>
              </div>
              <button type="button" onClick={loadBookingSummary} disabled={bookingSummaryLoading}>
                {bookingSummaryLoading ? "Actualizando..." : "Actualizar"}
              </button>
            </div>

            <div className="control-dashboard">
              <div>
                <span>Shows</span>
                <strong>{bookingSummary?.totals.shows || 0}</strong>
              </div>
              <div>
                <span>Indyana total</span>
                <strong>{ars(bookingSummary?.totals.indyana_total || 0)}</strong>
              </div>
              <div>
                <span>Base comisionable</span>
                <strong>{ars(bookingSummary?.totals.commissionable_total || 0)}</strong>
              </div>
              <div className={(bookingSummary?.totals.non_commissionable_total || 0) > 0 ? "warn" : ""}>
                <span>No comisionable</span>
                <strong>{ars(bookingSummary?.totals.non_commissionable_total || 0)}</strong>
              </div>
            </div>

            <p className="field-help">
              Si un show tiene comision directa o una regla especial, Indyana conserva el ingreso, pero ese monto no entra en la comision general del responsable de booking.
            </p>

            <div className="summary-table-wrap">
              <table className="summary-table">
                <thead>
                  <tr>
                    <th>Artista</th>
                    <th>Shows</th>
                    <th>Indyana</th>
                    <th>Base comisionable</th>
                    <th>No comisionable</th>
                    {bookingSummary?.months.map((month) => (
                      <th key={month}>{month}</th>
                    ))}
                    <th>Explicacion</th>
                  </tr>
                </thead>
                <tbody>
                  {!bookingSummary && (
                    <tr>
                      <td colSpan={6}>Cargando resumen...</td>
                    </tr>
                  )}
                  {bookingSummary?.items.map((item) => (
                    <tr key={item.artist}>
                      <td><strong>{item.artist}</strong></td>
                      <td>{item.shows}</td>
                      <td>{ars(item.indyana_total)}</td>
                      <td>{ars(item.commissionable_total)}</td>
                      <td className={item.non_commissionable_total > 0 ? "amount-warn" : ""}>
                        {ars(item.non_commissionable_total)}
                      </td>
                      {bookingSummary.months.map((month) => {
                        const monthItem = item.months[month];
                        return (
                          <td key={`${item.artist}-${month}`}>
                            {monthItem ? (
                              <>
                                <strong>{ars(monthItem.indyana_total)}</strong>
                                {monthItem.non_commissionable_total > 0 && (
                                  <span className="cell-note">No com. {ars(monthItem.non_commissionable_total)}</span>
                                )}
                              </>
                            ) : "-"}
                          </td>
                        );
                      })}
                      <td>{item.notes.length ? item.notes.join(" / ") : "Comisiona normal"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {view === "booking-artist-summary" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Detalle Booking</h1>
                <p>Control show por show con fecha, venue, cachet total, ingreso artista e ingreso Indyana.</p>
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setBookingArtistSummaryLatestOnly((current) => !current)}
                  disabled={!bookingArtistSummary}
                >
                  {bookingArtistSummaryLatestOnly ? "Mostrar todos" : "Mostrar ultimos 5"}
                </button>
                <button type="button" onClick={loadBookingArtistSummary} disabled={bookingArtistSummaryLoading}>
                  {bookingArtistSummaryLoading ? "Actualizando..." : "Actualizar"}
                </button>
              </div>
            </div>

            <div className="row">
              <div>
                <label htmlFor="booking_artist_summary_artist">Artista</label>
                <select
                  id="booking_artist_summary_artist"
                  value={bookingArtistSummaryArtist}
                  onChange={(event) => setBookingArtistSummaryArtist(event.target.value)}
                >
                  <option value="">Todos</option>
                  {bookingArtistSummary?.artists.map((artist) => (
                    <option key={artist} value={artist}>{artist}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="control-dashboard">
              <div>
                <span>Shows</span>
                <strong>{bookingArtistSummary?.totals.shows || 0}</strong>
              </div>
              <div>
                <span>Cachet total</span>
                <strong>{ars(bookingArtistSummary?.totals.cachet_total || 0)}</strong>
              </div>
              <div>
                <span>Ingreso artista</span>
                <strong>{ars(bookingArtistSummary?.totals.artist_income || 0)}</strong>
              </div>
              <div>
                <span>Ingreso Indyana</span>
                <strong>{ars(bookingArtistSummary?.totals.indyana_income || 0)}</strong>
              </div>
              <div>
                <span>Comisionable</span>
                <strong>{ars(bookingArtistSummary?.totals.commissionable_income || 0)}</strong>
              </div>
              <div className={(bookingArtistSummary?.totals.non_commissionable_income || 0) > 0 ? "warn" : ""}>
                <span>No comisionable</span>
                <strong>{ars(bookingArtistSummary?.totals.non_commissionable_income || 0)}</strong>
              </div>
            </div>

            <h2>Totales por mes</h2>
            <div className="summary-table-wrap compact-table">
              <table className="summary-table">
                <thead>
                  <tr>
                    <th>Mes</th>
                    <th>Shows</th>
                    <th>Cachet total</th>
                    <th>Ingreso artista</th>
                    <th>Ingreso Indyana</th>
                    <th>Comisionable</th>
                    <th>No comisionable</th>
                  </tr>
                </thead>
                <tbody>
                  {!bookingArtistSummary && (
                    <tr>
                      <td colSpan={7}>Cargando detalle...</td>
                    </tr>
                  )}
                  {bookingArtistSummary?.months.map((month) => (
                    <tr key={month.month}>
                      <td><strong>{month.month}</strong></td>
                      <td>{month.shows}</td>
                      <td>{ars(month.cachet_total)}</td>
                      <td>{ars(month.artist_income)}</td>
                      <td>{ars(month.indyana_income)}</td>
                      <td>{ars(month.commissionable_income)}</td>
                      <td className={month.non_commissionable_income > 0 ? "amount-warn" : ""}>{ars(month.non_commissionable_income)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h2>Shows</h2>
            {bookingArtistSummary && (
              <p className="field-help">
                Mostrando {visibleBookingArtistSummaryItems.length} de {bookingArtistSummary.items.length} show(s).
              </p>
            )}
            <div className="summary-table-wrap">
              <table className="summary-table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Venue</th>
                    <th>Artista</th>
                    <th>Cachet total</th>
                    <th>Ingreso artista</th>
                    <th>Ingreso Indyana</th>
                    <th>Comision</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {bookingArtistSummary?.items.length === 0 && (
                    <tr>
                      <td colSpan={8}>Sin shows para este filtro.</td>
                    </tr>
                  )}
                  {visibleBookingArtistSummaryItems.map((item) => (
                    <tr key={item.id}>
                      <td>{item.show_date}</td>
                      <td>
                        <strong>{item.venue}</strong>
                        {item.city && <span className="cell-note">{item.city}</span>}
                      </td>
                      <td>{item.artist}</td>
                      <td>{ars(item.cachet_total)}</td>
                      <td>{ars(item.artist_income)}</td>
                      <td>{ars(item.indyana_income)}</td>
                      <td>
                        <strong>{item.is_commissionable ? "Comisionable" : "No comisionable"}</strong>
                        <span className="cell-note">
                          {item.is_commissionable ? ars(item.commissionable_income) : ars(item.non_commissionable_income)}
                        </span>
                        {!item.is_commissionable && item.commission_notes && (
                          <span className="cell-note">{item.commission_notes}</span>
                        )}
                      </td>
                      <td>
                        <span>{item.settlement_status}</span>
                        {item.origin_type === "booking_composite" && item.origin_id && (
                          <span className="cell-note">Madre #{item.origin_id}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {view === "booking-lab" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Carga de Shows laboratorio</h1>
                <p>Modo seguro: calcula y valida el flujo dinamico, sin guardar en la base viva.</p>
              </div>
              <div className="button-row">
                <button type="button" onClick={resetBookingLabForm}>Limpiar</button>
                <button type="button" className="secondary" disabled>Guardar desactivado</button>
              </div>
            </div>

            <form className="panel nested-panel" onSubmit={(event) => event.preventDefault()}>
              <div className="row">
                <div>
                  <label htmlFor="booking_lab_date">Fecha</label>
                  <input id="booking_lab_date" type="date" value={bookingLabForm.eventDate} onChange={(event) => updateBookingLabField("eventDate", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="booking_lab_venue">Venue / evento</label>
                  <input id="booking_lab_venue" value={bookingLabForm.venue} onChange={(event) => updateBookingLabField("venue", event.target.value)} />
                </div>
              </div>

              <div className="row three">
                <div>
                  <label htmlFor="booking_lab_city">Ciudad</label>
                  <input id="booking_lab_city" value={bookingLabForm.city} onChange={(event) => updateBookingLabField("city", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="booking_lab_responsible">Responsable</label>
                  <input id="booking_lab_responsible" value={bookingLabForm.responsible} onChange={(event) => updateBookingLabField("responsible", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="booking_lab_status">Estado</label>
                  <select id="booking_lab_status" value={bookingLabForm.status} onChange={(event) => updateBookingLabField("status", event.target.value as BookingLabForm["status"])}>
                    <option value="borrador">Borrador</option>
                    <option value="observado">Observado</option>
                    <option value="cerrado">Cerrado</option>
                    <option value="cerrado_cc">Cerrado con cuenta corriente</option>
                  </select>
                </div>
              </div>

              <div className="row four">
                <div>
                  <label htmlFor="booking_lab_gross">Cachet pactado</label>
                  <input id="booking_lab_gross" inputMode="decimal" value={bookingLabForm.grossAmount} onChange={(event) => updateBookingLabField("grossAmount", event.target.value)} placeholder="1500000 o u$ 300" />
                </div>
                <div>
                  <label htmlFor="booking_lab_collected">Cobrado real</label>
                  <input id="booking_lab_collected" inputMode="decimal" value={bookingLabForm.collectedAmount} onChange={(event) => updateBookingLabField("collectedAmount", event.target.value)} placeholder="vacio = cachet" />
                </div>
                <div>
                  <label htmlFor="booking_lab_currency">Moneda base</label>
                  <select id="booking_lab_currency" value={bookingLabForm.currency} onChange={(event) => updateBookingLabField("currency", event.target.value as BookingLabForm["currency"])}>
                    <option value="ARS">ARS</option>
                    <option value="USD">USD</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="booking_lab_fx">Tipo de cambio</label>
                  <input id="booking_lab_fx" inputMode="decimal" value={bookingLabForm.fxRate} onChange={(event) => updateBookingLabField("fxRate", event.target.value)} placeholder="1390" />
                </div>
              </div>

              <div className="booking-suggestion">
                <div className={bookingLabMode.kind === "mother" ? "warn" : ""}>
                  <span>Modo actual</span>
                  <strong>{bookingLabMode.label}</strong>
                </div>
                <div>
                  <span>Cachet pactado</span>
                  <strong>{suggestedAmount(bookingLabPreview.gross, bookingLabForm.currency)}</strong>
                </div>
                <div className={Math.abs(bookingLabPreview.venueBalance) > 0.001 ? "warn" : ""}>
                  <span>Deuda boliche</span>
                  <strong>{suggestedAmount(bookingLabPreview.venueBalance, bookingLabForm.currency)}</strong>
                </div>
                <div>
                  <span>Gastos generales</span>
                  <strong>{suggestedAmount(bookingLabPreview.eventExpenses, bookingLabForm.currency)}</strong>
                </div>
                <div>
                  <span>Comisión directa</span>
                  <strong>{suggestedAmount(bookingLabPreview.directCommissions, bookingLabForm.currency)}</strong>
                </div>
                <div>
                  <span>Incorporado a artistas</span>
                  <strong>{suggestedAmount(bookingLabPreview.incorporatedCommissions, bookingLabForm.currency)}</strong>
                </div>
                <div>
                  <span>Base neta evento</span>
                  <strong>{suggestedAmount(bookingLabPreview.eventBase, bookingLabForm.currency)}</strong>
                </div>
                <div className={Math.abs(bookingLabPreview.unallocated) > 0.001 ? "warn" : ""}>
                  <span>Diferencia asignada</span>
                  <strong>{suggestedAmount(bookingLabPreview.unallocated, bookingLabForm.currency)}</strong>
                </div>
                <div>
                  <span>Indyana esperada</span>
                  <strong>{suggestedAmount(bookingLabPreview.indyanaExpected, bookingLabForm.currency)}</strong>
                </div>
                <div>
                  <span>Base comisionable</span>
                  <strong>{suggestedAmount(bookingLabPreview.commissionableBase, bookingLabForm.currency)}</strong>
                </div>
                <div>
                  <span>Terceros</span>
                  <strong>{suggestedAmount(bookingLabPreview.thirdPartyExpected, bookingLabForm.currency)}</strong>
                </div>
                <div>
                  <span>Recuperos aplicados</span>
                  <strong>{suggestedAmount(bookingLabPreview.recoveryApplied, bookingLabForm.currency)}</strong>
                </div>
                <div>
                  <span>Señas previas</span>
                  <strong>{suggestedAmount(bookingLabPreview.cashSummary.total, bookingLabForm.currency)}</strong>
                </div>
                <div>
                  <span>A cerrar en evento</span>
                  <strong>{suggestedAmount(bookingLabPreview.eventCashToSettle, bookingLabForm.currency)}</strong>
                </div>
                {bookingLabPreview.cashSummary.unassigned > 0 && (
                  <div className="warn">
                    <span>Seña sin asignar</span>
                    <strong>{suggestedAmount(bookingLabPreview.cashSummary.unassigned, bookingLabForm.currency)}</strong>
                  </div>
                )}
              </div>
              <p className="field-help">{bookingLabMode.detail}</p>
              <div className="booking-payment-box">
                <strong>Resumen de guardado</strong>
                <p className="field-help">
                  {bookingLabMode.kind === "simple"
                    ? "Se guardaria como un show simple en Booking Indyana, con reglas avanzadas dentro del mismo show."
                    : bookingLabMode.kind === "mother"
                      ? "Se guardaria como evento madre y generaria shows internos para cada artista VPO."
                      : "Todavia no hay artista VPO suficiente para guardar."}
                </p>
                {bookingLabForm.lines.filter((line) => line.lineType === "artista_vpo").map((line) => {
                  const preview = bookingLabPreview.linePreviews[line.uid];
                  if (!preview) return null;
                  return (
                    <div className="adjustment-summary" key={`save-summary-${line.uid}`}>
                      <span>{line.artist || "Artista sin elegir"}</span>
                      <span>Base {suggestedAmount(preview.lineBase, bookingLabForm.currency)}</span>
                      <span>Gastos {suggestedAmount(preview.lineExpenses, bookingLabForm.currency)}</span>
                      <span>Split {suggestedAmount(preview.splitBase, bookingLabForm.currency)}</span>
                      <span>Artista {suggestedAmount(preview.artistSuggested, bookingLabForm.currency)}</span>
                      <span>Indyana {suggestedAmount(preview.producerSuggested, bookingLabForm.currency)}</span>
                      <span>Terceros {suggestedAmount(preview.preSplitThirdParties + preview.afterSplitThirdParties, bookingLabForm.currency)}</span>
                      <span>Pagado artista {suggestedAmount(preview.artistPaid, bookingLabForm.currency)}</span>
                      <span>Rendido Indyana {suggestedAmount(preview.producerReceived, bookingLabForm.currency)}</span>
                      <span>Saldo artista {suggestedAmount(preview.artistBalance, bookingLabForm.currency)}</span>
                      <span>Saldo Indyana {suggestedAmount(preview.producerBalance, bookingLabForm.currency)}</span>
                    </div>
                  );
                })}
                <div className="adjustment-summary">
                  <span>Artistas esperado {suggestedAmount(bookingLabPreview.artistExpected, bookingLabForm.currency)}</span>
                  <span>Indyana esperado {suggestedAmount(bookingLabPreview.indyanaExpected, bookingLabForm.currency)}</span>
                  <span>Señas artista {suggestedAmount(bookingLabPreview.cashSummary.artist, bookingLabForm.currency)}</span>
                  <span>Señas Indyana {suggestedAmount(bookingLabPreview.cashSummary.producer, bookingLabForm.currency)}</span>
                  <span className={Math.abs(bookingLabPreview.artistBalance) > 0.01 ? "amount-warn" : ""}>Saldo artistas {suggestedAmount(bookingLabPreview.artistBalance, bookingLabForm.currency)}</span>
                  <span className={Math.abs(bookingLabPreview.producerBalance) > 0.01 ? "amount-warn" : ""}>Saldo Indyana {suggestedAmount(bookingLabPreview.producerBalance, bookingLabForm.currency)}</span>
                </div>
                {(bookingLabPreview.artistBalance < -0.01 || bookingLabPreview.producerBalance < -0.01) && (
                  <p className="field-help danger-text">
                    Hay cobros por encima de lo esperado. Esto deberia generar cuenta corriente por artista/productora antes de cerrar.
                  </p>
                )}
              </div>

              <div className="show-expenses">
                <div className="section-heading compact">
                  <div>
                    <h2>Señas previas</h2>
                    <p>Anticipos recibidos antes o fuera del cierre del show. No cambian el split; reducen saldos y pueden generar cuenta corriente.</p>
                  </div>
                  <button type="button" onClick={() => addBookingLabCashMovement("producer")}>Agregar seña</button>
                </div>

                {bookingLabForm.cashMovements.length === 0 && (
                  <p className="field-help">Sin señas previas. Agregalas solo si artista o productora recibieron plata antes del cierre del show.</p>
                )}

                {bookingLabForm.cashMovements.length > 0 && (
                  <div className="adjustment-summary">
                    <span>Seña Indyana {suggestedAmount(bookingLabPreview.cashSummary.producer, bookingLabForm.currency)}</span>
                    <span>Seña artista {suggestedAmount(bookingLabPreview.cashSummary.artist, bookingLabForm.currency)}</span>
                    <span>Total señas {suggestedAmount(bookingLabPreview.cashSummary.total, bookingLabForm.currency)}</span>
                    {bookingLabPreview.cashSummary.unassigned > 0 && <span>Sin asignar {suggestedAmount(bookingLabPreview.cashSummary.unassigned, bookingLabForm.currency)}</span>}
                  </div>
                )}

                {bookingLabForm.cashMovements.map((movement, index) => (
                  <div className="adjustment-card" key={movement.uid}>
                    <div className="adjustment-card-title">
                      <strong>Seña {index + 1}</strong>
                      <button type="button" onClick={() => removeBookingLabCashMovement(movement.uid)}>Quitar</button>
                    </div>
                    <div className="row four">
                      <div>
                        <label>Importe</label>
                        <input inputMode="decimal" value={movement.amount} onChange={(event) => updateBookingLabCashMovementField(movement.uid, "amount", event.target.value)} />
                      </div>
                      <div>
                        <label>Metodo</label>
                        <select value={movement.paymentMethod} onChange={(event) => updateBookingLabCashMovementField(movement.uid, "paymentMethod", event.target.value as BookingCashMovementForm["paymentMethod"])}>
                          <option value="transferencia">Transferencia</option>
                          <option value="efectivo">Efectivo</option>
                          <option value="otro">Otro</option>
                        </select>
                      </div>
                      <div>
                        <label>Recibio</label>
                        <select value={movement.recipient} onChange={(event) => updateBookingLabCashMovementField(movement.uid, "recipient", event.target.value as BookingCashMovementForm["recipient"])}>
                          <option value="producer">Indyana</option>
                          <option value="artist">Artista</option>
                        </select>
                      </div>
                      <div>
                        <label>Aplicar a</label>
                        <select value={movement.targetArtist || ""} onChange={(event) => updateBookingLabCashMovementField(movement.uid, "targetArtist", event.target.value)}>
                          <option value="">General / automatico</option>
                          {bookingLabForm.lines.filter((line) => line.lineType === "artista_vpo" && line.artist).map((line) => (
                            <option key={`${movement.uid}-${line.uid}`} value={line.artist}>{line.artist}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div className="row">
                      <div>
                        <label>Pagado por / origen</label>
                        <input value={movement.paidBy} onChange={(event) => updateBookingLabCashMovementField(movement.uid, "paidBy", event.target.value)} placeholder="Boliche, PM, artista" />
                      </div>
                    </div>
                    <label>Nota / comprobante</label>
                    <textarea value={movement.notes} onChange={(event) => updateBookingLabCashMovementField(movement.uid, "notes", event.target.value)} />
                    {!movement.targetArtist && bookingLabForm.lines.filter((line) => line.lineType === "artista_vpo" && line.artist).length > 1 && (
                      <p className="field-help danger-text">En eventos con varios artistas, asigna la seña a una linea para que el saldo sea confiable.</p>
                    )}
                  </div>
                ))}
              </div>

              <div className="show-expenses">
                <div className="section-heading compact">
                  <div>
                    <h2>Gastos generales del evento</h2>
                  </div>
                  <button type="button" onClick={() => addBookingLabExpense("expenses")}>Agregar gasto</button>
                </div>
                {bookingLabForm.expenses.map((expense) => (
                  <div className="row four" key={expense.uid}>
                    <select value={expense.category} onChange={(event) => updateBookingLabExpenseField("expenses", expense.uid, "category", event.target.value)}>
                      {BOOKING_EXPENSE_CATEGORIES.map((category) => (
                        <option key={category.value} value={category.value}>{category.label}</option>
                      ))}
                    </select>
                    <input value={expense.concept} onChange={(event) => updateBookingLabExpenseField("expenses", expense.uid, "concept", event.target.value)} placeholder="concepto" />
                    <input inputMode="decimal" value={expense.amount} onChange={(event) => updateBookingLabExpenseField("expenses", expense.uid, "amount", event.target.value)} placeholder="importe" />
                    <button type="button" onClick={() => removeBookingLabExpense("expenses", expense.uid)}>Quitar</button>
                  </div>
                ))}
              </div>

              <div className="show-expenses">
                <div className="section-heading compact">
                  <div>
                    <h2>Comisión directa del evento</h2>
                  </div>
                  <button type="button" onClick={() => addBookingLabExpense("directCommissions", "comision_externa")}>Agregar comisión</button>
                </div>
                {bookingLabForm.directCommissions.map((commission) => (
                  <div className="adjustment-card" key={commission.uid}>
                    <div className="adjustment-card-title">
                      <strong>{commission.concept || "Comision directa"}</strong>
                      <button type="button" onClick={() => removeBookingLabExpense("directCommissions", commission.uid)}>Quitar</button>
                    </div>
                    <div className="row four">
                      <div>
                        <label>Categoria</label>
                        <select value={commission.category} onChange={(event) => updateBookingLabExpenseField("directCommissions", commission.uid, "category", event.target.value)}>
                          {BOOKING_EXPENSE_CATEGORIES.map((category) => (
                            <option key={category.value} value={category.value}>{category.label}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label>Concepto</label>
                        <input value={commission.concept} onChange={(event) => updateBookingLabExpenseField("directCommissions", commission.uid, "concept", event.target.value)} placeholder="Marce directo, booking, vendedor" />
                      </div>
                      <div>
                        <label>Importe</label>
                        <input inputMode="decimal" value={commission.amount} onChange={(event) => updateBookingLabExpenseField("directCommissions", commission.uid, "amount", event.target.value)} placeholder="importe" />
                      </div>
                      <div>
                        <label>Tratamiento</label>
                        <select
                          value={commission.commissionDestination || "direct"}
                          onChange={(event) => updateBookingLabExpenseField("directCommissions", commission.uid, "commissionDestination", event.target.value as BookingExpenseForm["commissionDestination"])}
                        >
                          <option value="direct">Sale del calculo</option>
                          <option value="artist_base">Asignar a artista</option>
                        </select>
                      </div>
                    </div>
                    {commission.commissionDestination === "artist_base" && (
                      <div className="row">
                        <div>
                          <label>Artista destino</label>
                          <select
                            value={commission.commissionTargetArtist || ""}
                            onChange={(event) => updateBookingLabExpenseField("directCommissions", commission.uid, "commissionTargetArtist", event.target.value)}
                          >
                            <option value="">Elegir artista</option>
                            {bookingArtists.map((artist) => (
                              <option key={artist} value={artist}>{artist}</option>
                            ))}
                          </select>
                          <p className="field-help">El importe sale del neto general y vuelve como base de esta linea.</p>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="show-expenses">
                <div className="section-heading compact">
                  <div>
                    <h2>Líneas del evento</h2>
                  </div>
                  <div className="button-row">
                    <button type="button" onClick={() => addBookingLabLine("artista_vpo")}>Artista VPO</button>
                    <button type="button" onClick={() => addBookingLabLine("artista_externo")}>Artista externo</button>
                  </div>
                </div>

                {bookingLabForm.lines.map((line, index) => {
                  const preview = bookingLabPreview.linePreviews[line.uid];
                  return (
                    <div className="line-card" key={line.uid}>
                      <div className="adjustment-card-title">
                        <strong>Línea {index + 1}</strong>
                        <button type="button" onClick={() => removeBookingLabLine(line.uid)}>Quitar</button>
                      </div>

                      <div className="row three">
                        <div>
                          <label>Tipo</label>
                          <select value={line.lineType} onChange={(event) => updateBookingLabLineField(line.uid, "lineType", event.target.value as BookingLabLineForm["lineType"])}>
                            <option value="artista_vpo">Artista VPO</option>
                            <option value="artista_externo">Artista externo</option>
                          </select>
                        </div>
                        <div>
                          <label>Descripción</label>
                          <input value={line.description} onChange={(event) => updateBookingLabLineField(line.uid, "description", event.target.value)} placeholder="Candu, G Sony, Franux" />
                        </div>
                        <div>
                          <label>Artista</label>
                          <select value={line.artist} onChange={(event) => updateBookingLabLineField(line.uid, "artist", event.target.value)}>
                            <option value="">Elegir artista</option>
                            {bookingArtists.map((artist) => (
                              <option key={artist} value={artist}>{artist}</option>
                            ))}
                          </select>
                        </div>
                      </div>

                      <div className="row four">
                        <div>
                          <label>Cálculo de base</label>
                          <select value={line.allocationMode} onChange={(event) => updateBookingLabLineField(line.uid, "allocationMode", event.target.value as BookingLabLineForm["allocationMode"])}>
                            <option value="equal">Partes iguales</option>
                            <option value="net_percent">% del neto evento</option>
                            <option value="manual">Manual</option>
                          </select>
                        </div>
                        <div>
                          <label>% neto</label>
                          <input inputMode="decimal" value={line.allocationPercent} disabled={line.allocationMode !== "net_percent"} onChange={(event) => updateBookingLabLineField(line.uid, "allocationPercent", event.target.value)} />
                        </div>
                        <div>
                          <label>Importe manual</label>
                          <input inputMode="decimal" value={line.amount} disabled={line.allocationMode !== "manual"} onChange={(event) => updateBookingLabLineField(line.uid, "amount", event.target.value)} />
                        </div>
                        <div>
                          <label>Ajuste base</label>
                          <input inputMode="decimal" value={line.baseAdjustment} onChange={(event) => updateBookingLabLineField(line.uid, "baseAdjustment", event.target.value)} placeholder="+200000" />
                        </div>
                      </div>

                      {preview && (
                        <div className="adjustment-summary">
                          <span>Base línea {suggestedAmount(preview.lineBase, bookingLabForm.currency)}</span>
                          <span>Gastos línea {suggestedAmount(preview.lineExpenses, bookingLabForm.currency)}</span>
                          <span>Terceros antes {suggestedAmount(preview.preSplitThirdParties, bookingLabForm.currency)}</span>
                          <span>Base split {suggestedAmount(preview.splitBase, bookingLabForm.currency)}</span>
                          <span>Artista {suggestedAmount(preview.artistSuggested, bookingLabForm.currency)}</span>
                          <span>Indyana {suggestedAmount(preview.producerSuggested, bookingLabForm.currency)}</span>
                          <span>Terceros después {suggestedAmount(preview.afterSplitThirdParties, bookingLabForm.currency)}</span>
                          <span>Control {suggestedAmount(preview.lineBalance, bookingLabForm.currency)}</span>
                        </div>
                      )}

                      <div className="row three">
                        <div>
                          <label>% artista</label>
                          <input inputMode="decimal" value={line.artistPercent} onChange={(event) => updateBookingLabLineField(line.uid, "artistPercent", event.target.value)} />
                        </div>
                        <div>
                          <label>% Indyana</label>
                          <input inputMode="decimal" value={line.producerPercent} onChange={(event) => updateBookingLabLineField(line.uid, "producerPercent", event.target.value)} />
                        </div>
                        <label className="checkbox-field">
                          <input type="checkbox" checked={line.bookingCommissionExempt} onChange={(event) => updateBookingLabLineField(line.uid, "bookingCommissionExempt", event.target.checked)} />
                          No entra en comisión general
                        </label>
                      </div>
                      {line.bookingCommissionExempt && (
                        <textarea value={line.bookingCommissionNotes} onChange={(event) => updateBookingLabLineField(line.uid, "bookingCommissionNotes", event.target.value)} placeholder="Motivo" />
                      )}

                      <div className="section-heading compact">
                        <div>
                          <h2>Gastos propios de la línea</h2>
                        </div>
                        <button type="button" onClick={() => addBookingLabLineExpense(line.uid)}>Agregar gasto</button>
                      </div>
                      {line.showExpenses.map((expense) => (
                        <div className="row four" key={expense.uid}>
                          <select value={expense.category} onChange={(event) => updateBookingLabLineExpenseField(line.uid, expense.uid, "category", event.target.value)}>
                            {BOOKING_EXPENSE_CATEGORIES.map((category) => (
                              <option key={category.value} value={category.value}>{category.label}</option>
                            ))}
                          </select>
                          <input value={expense.concept} onChange={(event) => updateBookingLabLineExpenseField(line.uid, expense.uid, "concept", event.target.value)} placeholder="tour manager, músico" />
                          <input inputMode="decimal" value={expense.amount} onChange={(event) => updateBookingLabLineExpenseField(line.uid, expense.uid, "amount", event.target.value)} placeholder="importe" />
                          <button type="button" onClick={() => removeBookingLabLineExpense(line.uid, expense.uid)}>Quitar</button>
                        </div>
                      ))}

                      <div className="section-heading compact">
                        <div>
                          <h2>Manager / socio externo</h2>
                          <p>Para casos como Fede en G Sony: participa del split, no es gasto del show.</p>
                        </div>
                        <button type="button" onClick={() => addBookingLabThirdParty(line.uid, "after_split")}>Agregar manager/socio externo</button>
                      </div>
                      {line.thirdParties.map((thirdParty) => (
                        <div className="adjustment-card" key={thirdParty.uid}>
                          {(() => {
                            const amount = parseAmountInput(thirdParty.amount, bookingLabFxRate);
                            const base = thirdParty.basis === "before_split" ? preview?.baseBeforeSplit || 0 : preview?.splitBase || 0;
                            const calculated = amount > 0 ? amount : base * parseMoneyInput(thirdParty.percent) / 100;

                            return (
                              <div className="adjustment-card-title">
                                <strong>{thirdParty.name || "Manager / socio externo"}</strong>
                                <span>{suggestedAmount(calculated, bookingLabForm.currency)}</span>
                              </div>
                            );
                          })()}
                          <div className="row four">
                            <div>
                              <label>Nombre</label>
                              <input value={thirdParty.name} onChange={(event) => updateBookingLabThirdPartyField(line.uid, thirdParty.uid, "name", event.target.value)} placeholder="Fede" />
                            </div>
                            <div>
                              <label>Rol</label>
                              <select value={thirdParty.role} onChange={(event) => updateBookingLabThirdPartyField(line.uid, thirdParty.uid, "role", event.target.value as BookingLabThirdPartyForm["role"])}>
                                <option value="manager_externo">Manager externo</option>
                                <option value="socio_externo">Socio externo</option>
                                <option value="tercero">Tercero</option>
                                <option value="otro">Otro</option>
                              </select>
                            </div>
                            <div>
                              <label>Participa</label>
                              <select value={thirdParty.basis} onChange={(event) => updateBookingLabThirdPartyField(line.uid, thirdParty.uid, "basis", event.target.value as BookingLabThirdPartyForm["basis"])}>
                                <option value="after_split">Del split</option>
                                <option value="before_split">Antes del split</option>
                              </select>
                            </div>
                            <button type="button" onClick={() => removeBookingLabThirdParty(line.uid, thirdParty.uid)}>Quitar</button>
                          </div>
                          <div className="row three">
                            <div>
                              <label>% del split</label>
                              <input inputMode="decimal" value={thirdParty.percent} onChange={(event) => updateBookingLabThirdPartyField(line.uid, thirdParty.uid, "percent", event.target.value)} placeholder="25" />
                            </div>
                            <div>
                              <label>Importe manual</label>
                              <input inputMode="decimal" value={thirdParty.amount} onChange={(event) => updateBookingLabThirdPartyField(line.uid, thirdParty.uid, "amount", event.target.value)} placeholder="opcional" />
                            </div>
                            <label className="checkbox-field">
                              <input type="checkbox" checked={thirdParty.cashHandledByVpo} onChange={(event) => updateBookingLabThirdPartyField(line.uid, thirdParty.uid, "cashHandledByVpo", event.target.checked)} />
                              Caja manejada por VPO
                            </label>
                          </div>
                        </div>
                      ))}

                      {preview && (
                        <div className="show-expenses">
                          <div className="section-heading compact">
                            <div>
                              <h2>Pagos y rendicion</h2>
                              <p>Registra lo que paso en caja. Los sugeridos vienen de la liquidacion calculada.</p>
                            </div>
                          </div>
                          <div className="row">
                            <div>
                              <label>Pagado al artista</label>
                              <input
                                inputMode="decimal"
                                value={line.artistPaidAmount}
                                onChange={(event) => updateBookingLabLineField(line.uid, "artistPaidAmount", event.target.value)}
                                placeholder="importe real pagado"
                              />
                              <button
                                type="button"
                                className="inline-action"
                                onClick={() => updateBookingLabLineField(line.uid, "artistPaidAmount", String(Math.round(Math.max(0, preview.artistSuggested - preview.artistCashReceived) * 100) / 100))}
                              >
                                Usar sugerido ({suggestedAmount(Math.max(0, preview.artistSuggested - preview.artistCashReceived), bookingLabForm.currency)})
                              </button>
                              <p className={Math.abs(preview.artistBalance) > 0.01 ? "field-help danger-text" : "field-help"}>
                                Saldo artista: {suggestedAmount(preview.artistBalance, bookingLabForm.currency)}
                              </p>
                            </div>
                            <div>
                              <label>Rendido a Indyana</label>
                              <input
                                inputMode="decimal"
                                value={line.producerReceivedAmount}
                                onChange={(event) => updateBookingLabLineField(line.uid, "producerReceivedAmount", event.target.value)}
                                placeholder="importe real recibido"
                              />
                              <button
                                type="button"
                                className="inline-action"
                                onClick={() => updateBookingLabLineField(line.uid, "producerReceivedAmount", String(Math.round(Math.max(0, preview.producerSuggested - preview.producerCashReceived) * 100) / 100))}
                              >
                                Usar sugerido ({suggestedAmount(Math.max(0, preview.producerSuggested - preview.producerCashReceived), bookingLabForm.currency)})
                              </button>
                              <p className={Math.abs(preview.producerBalance) > 0.01 ? "field-help danger-text" : "field-help"}>
                                Saldo Indyana: {suggestedAmount(preview.producerBalance, bookingLabForm.currency)}
                              </p>
                            </div>
                          </div>
                        </div>
                      )}

                      <div className="show-expenses">
                        <label className="checkbox-field">
                          <input type="checkbox" checked={line.recoveryEnabled} onChange={(event) => updateBookingLabLineField(line.uid, "recoveryEnabled", event.target.checked)} />
                          Aplicar recupero
                        </label>
                        {line.recoveryEnabled && (
                          <div className="row four">
                            <select value={line.recoveryMode} onChange={(event) => updateBookingLabLineField(line.uid, "recoveryMode", event.target.value as BookingLabLineForm["recoveryMode"])}>
                              <option value="artist_share">Contra parte artista</option>
                              <option value="pre_split">Antes del split</option>
                              <option value="producer_share">Contra parte Indyana</option>
                              <option value="manual">Manual</option>
                            </select>
                            <input value={line.recoverySource} onChange={(event) => updateBookingLabLineField(line.uid, "recoverySource", event.target.value)} placeholder="DJ set, adelanto, gasto" />
                            <input inputMode="decimal" value={line.recoveryAmount} onChange={(event) => updateBookingLabLineField(line.uid, "recoveryAmount", event.target.value)} placeholder="importe aplicado" />
                            <input value={line.notes} onChange={(event) => updateBookingLabLineField(line.uid, "notes", event.target.value)} placeholder="nota" />
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              <label htmlFor="booking_lab_notes">Notas</label>
              <textarea id="booking_lab_notes" value={bookingLabForm.notes} onChange={(event) => updateBookingLabField("notes", event.target.value)} />
            </form>
          </section>
        )}

        {view === "composite-booking" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Carga de Shows beta</h1>
                <p>Pantalla de prueba para validar el flujo unificado antes de reemplazar la carga estable.</p>
              </div>
              <button type="button" onClick={loadCompositeBookingEvents} disabled={compositeBookingLoading}>
                {compositeBookingLoading ? "Actualizando..." : "Actualizar"}
              </button>
            </div>

            <form className="panel nested-panel" onSubmit={submitCompositeBooking}>
              <div className="section-heading compact">
                <div>
                  <h2>Nueva liquidacion</h2>
                  <p>Para eventos madre con gastos compartidos y shows internos de artistas VPO.</p>
                </div>
              </div>

              <div className="row">
                <div>
                  <label htmlFor="composite_date">Fecha</label>
                  <input id="composite_date" type="date" value={compositeBookingForm.eventDate} onChange={(event) => updateCompositeBookingField("eventDate", event.target.value)} required />
                </div>
                <div>
                  <label htmlFor="composite_venue">Venue / evento</label>
                  <input id="composite_venue" value={compositeBookingForm.venue} onChange={(event) => updateCompositeBookingField("venue", event.target.value)} required />
                </div>
              </div>

              <div className="row">
                <div>
                  <label htmlFor="composite_city">Ciudad</label>
                  <input id="composite_city" value={compositeBookingForm.city} onChange={(event) => updateCompositeBookingField("city", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="composite_responsible">Responsable</label>
                  <input id="composite_responsible" value={compositeBookingForm.responsible} onChange={(event) => updateCompositeBookingField("responsible", event.target.value)} />
                </div>
              </div>

              <div className="row three">
                <div>
                  <label htmlFor="composite_gross">Cachet / bruto madre</label>
                  <input id="composite_gross" inputMode="decimal" value={compositeBookingForm.grossAmount} onChange={(event) => updateCompositeBookingField("grossAmount", event.target.value)} required />
                </div>
                <div>
                  <label htmlFor="composite_received">Rendido a Indyana</label>
                  <input id="composite_received" inputMode="decimal" value={compositeBookingForm.receivedAmount} onChange={(event) => updateCompositeBookingField("receivedAmount", event.target.value)} />
                  <button
                    type="button"
                    className="inline-action"
                    onClick={() => updateCompositeBookingField("receivedAmount", String(Math.round(compositeBookingPreview.producerExpected * 100) / 100))}
                  >
                    Usar sugerido ({suggestedAmount(compositeBookingPreview.producerExpected, compositeBookingForm.currency)})
                  </button>
                </div>
                <div>
                  <label htmlFor="composite_status">Estado</label>
                  <select id="composite_status" value={compositeBookingForm.status} onChange={(event) => updateCompositeBookingField("status", event.target.value)}>
                    <option value="borrador">Borrador</option>
                    <option value="rendido">Rendido</option>
                    <option value="observado">Observado</option>
                    <option value="cerrado">Cerrado</option>
                  </select>
                </div>
              </div>

              <div className="booking-suggestion">
                <div>
                  <span>Bruto madre</span>
                  <strong>{localAmount(compositeBookingPreview.gross, compositeBookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Gastos operativos</span>
                  <strong>{localAmount(compositeBookingPreview.operationalExpenses, compositeBookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Comision directa</span>
                  <strong>{localAmount(compositeBookingPreview.directCommissions, compositeBookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Base artistica neta</span>
                  <strong>{localAmount(compositeBookingPreview.artistBase, compositeBookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Incorporado a artistas</span>
                  <strong>{localAmount(compositeBookingPreview.incorporatedCommissions, compositeBookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Base disponible lineas</span>
                  <strong>{localAmount(compositeBookingPreview.linePool, compositeBookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Base por partes iguales</span>
                  <strong>{localAmount(compositeBookingPreview.equalShare, compositeBookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Asignado a lineas</span>
                  <strong>{localAmount(compositeBookingPreview.allocated, compositeBookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Diferencia vs base</span>
                  <strong>{localAmount(compositeBookingPreview.unallocated, compositeBookingForm.currency)}</strong>
                </div>
                <div className={compositeBookingPreview.producerExpected > 0 ? "" : "muted"}>
                  <span>Indyana esperada</span>
                  <strong>{compositeBookingPreview.producerExpected > 0 ? localAmount(compositeBookingPreview.producerExpected, compositeBookingForm.currency) : "Sin calcular"}</strong>
                </div>
                <div className={compositeBookingPreview.producerExpected > 0 || compositeBookingPreview.received > 0 ? "" : "muted"}>
                  <span>Diferencia caja</span>
                  <strong>{compositeBookingPreview.producerExpected > 0 || compositeBookingPreview.received > 0 ? localAmount(compositeBookingPreview.balance, compositeBookingForm.currency) : "Sin caja"}</strong>
                </div>
                <div>
                  <span>Modo de guardado</span>
                  <strong>{compositeBookingSaveMode === "simple" ? "Show simple" : "Evento madre"}</strong>
                </div>
              </div>

              <div className="show-expenses">
                <div className="section-heading compact">
                  <div>
                    <h2>Gastos operativos</h2>
                    <p>Costos reales del show antes de repartir: sonido, musicos, staff, movilidad, viaticos.</p>
                  </div>
                  <button type="button" onClick={() => addCompositeBookingExpense("general")}>Agregar gasto</button>
                </div>

                {compositeBookingForm.expenses.filter((expense) => !isCommissionExpense(expense)).length === 0 && <p className="field-help">Sin gastos operativos cargados.</p>}
                {compositeBookingForm.expenses.filter((expense) => !isCommissionExpense(expense)).map((expense) => (
                  <div className="row three" key={expense.uid}>
                    <div>
                      <label htmlFor={`composite_expense_category_${expense.uid}`}>Categoria</label>
                      <select id={`composite_expense_category_${expense.uid}`} value={expense.category} onChange={(event) => updateCompositeBookingExpenseField(expense.uid, "category", event.target.value)}>
                        {BOOKING_EXPENSE_CATEGORIES.map((category) => (
                          <option key={category.value} value={category.value}>{category.label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label htmlFor={`composite_expense_concept_${expense.uid}`}>Concepto</label>
                      <input id={`composite_expense_concept_${expense.uid}`} value={expense.concept} onChange={(event) => updateCompositeBookingExpenseField(expense.uid, "concept", event.target.value)} placeholder="Sonido, Facha 15%, guitarra" />
                    </div>
                    <div className="inline-remove">
                      <div>
                        <label htmlFor={`composite_expense_amount_${expense.uid}`}>Importe</label>
                        <input id={`composite_expense_amount_${expense.uid}`} inputMode="decimal" value={expense.amount} onChange={(event) => updateCompositeBookingExpenseField(expense.uid, "amount", event.target.value)} placeholder="importe" />
                      </div>
                      <button type="button" onClick={() => removeCompositeBookingExpense(expense.uid)}>Quitar</button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="show-expenses">
                <div className="section-heading compact">
                  <div>
                    <h2>Comision directa / booking fee</h2>
                    <p>Partes del booking fee que salen directo o se incorporan a la base de un artista.</p>
                  </div>
                  <button type="button" onClick={() => addCompositeBookingExpense("comision_externa")}>Agregar comision</button>
                </div>

                {compositeBookingForm.expenses.filter((expense) => isCommissionExpense(expense)).length === 0 && (
                  <p className="field-help">Sin comision directa. Para un show simple podes dejar esta seccion vacia.</p>
                )}
                {compositeBookingForm.expenses.filter((expense) => isCommissionExpense(expense)).map((expense) => (
                  <div className="adjustment-card" key={expense.uid}>
                    <div className="adjustment-card-title">
                      <strong>{expense.concept || "Comision directa"}</strong>
                      <button type="button" onClick={() => removeCompositeBookingExpense(expense.uid)}>Quitar</button>
                    </div>
                    <div className="row three">
                      <div>
                        <label htmlFor={`composite_commission_concept_${expense.uid}`}>Beneficiario / concepto</label>
                        <input
                          id={`composite_commission_concept_${expense.uid}`}
                          value={expense.concept}
                          onChange={(event) => updateCompositeBookingExpenseField(expense.uid, "concept", event.target.value)}
                          placeholder="Marce, Gaston, booking fee"
                        />
                      </div>
                      <div>
                        <label htmlFor={`composite_commission_amount_${expense.uid}`}>Importe</label>
                        <input
                          id={`composite_commission_amount_${expense.uid}`}
                          inputMode="decimal"
                          value={expense.amount}
                          onChange={(event) => updateCompositeBookingExpenseField(expense.uid, "amount", event.target.value)}
                          placeholder="150000"
                        />
                      </div>
                      <div>
                        <label htmlFor={`composite_commission_destination_${expense.uid}`}>Destino</label>
                        <select
                          id={`composite_commission_destination_${expense.uid}`}
                          value={expense.commissionDestination || "direct"}
                          onChange={(event) => updateCompositeBookingExpenseField(expense.uid, "commissionDestination", event.target.value as BookingExpenseForm["commissionDestination"])}
                        >
                          <option value="direct">Salida directa / fuera de caja</option>
                          <option value="artist_base">Incorporar a base de artista</option>
                        </select>
                      </div>
                    </div>
                    {expense.commissionDestination === "artist_base" && (
                      <div className="row">
                        <div>
                          <label htmlFor={`composite_commission_target_${expense.uid}`}>Artista que recibe base</label>
                          <select
                            id={`composite_commission_target_${expense.uid}`}
                            value={expense.commissionTargetArtist || ""}
                            onChange={(event) => updateCompositeBookingExpenseField(expense.uid, "commissionTargetArtist", event.target.value)}
                          >
                            <option value="">Elegir artista</option>
                            {bookingArtists.map((artist) => (
                              <option key={artist} value={artist}>{artist}</option>
                            ))}
                          </select>
                          <p className="field-help">El importe se suma automaticamente a la base de la linea de ese artista.</p>
                        </div>
                        <div>
                          <div>
                            <label htmlFor={`composite_commission_notes_${expense.uid}`}>Nota</label>
                            <input
                              id={`composite_commission_notes_${expense.uid}`}
                              value={expense.notes}
                              onChange={(event) => updateCompositeBookingExpenseField(expense.uid, "notes", event.target.value)}
                              placeholder="Ej: parte Gaston se incorpora a G Sony"
                            />
                          </div>
                        </div>
                      </div>
                    )}
                    {expense.commissionDestination !== "artist_base" && (
                      <div className="row">
                        <div>
                          <label htmlFor={`composite_commission_notes_${expense.uid}`}>Nota</label>
                          <input
                            id={`composite_commission_notes_${expense.uid}`}
                            value={expense.notes}
                            onChange={(event) => updateCompositeBookingExpenseField(expense.uid, "notes", event.target.value)}
                            placeholder="Ej: Marce cobra directo, no entra en caja VPO"
                          />
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="show-expenses">
                <div className="section-heading compact">
                  <div>
                    <h2>Lineas internas</h2>
                    <p>Las lineas Artista VPO crean shows hijos en Booking Indyana.</p>
                  </div>
                  <div className="button-row">
                    <button type="button" onClick={() => addCompositeBookingLine("artista_vpo")}>Artista VPO</button>
                    <button type="button" onClick={() => addCompositeBookingLine("artista_externo")}>Artista externo</button>
                  </div>
                </div>

                {compositeBookingForm.lines.length === 0 && <p className="field-help">Agrega al menos una linea para cargar la liquidacion.</p>}
                {compositeBookingForm.lines.map((line, index) => (
                  <div className="line-card" key={line.uid}>
                    {(() => {
                      const lineBase = compositeBookingPreview.lineAmounts[line.uid] || 0;
                      const incorporatedForLine = line.artist ? compositeBookingPreview.incorporatedCommissionsByArtist[line.artist] || 0 : 0;
                      const lineExpenses = line.showExpenses.reduce((sum, expense) => sum + parseAmountInput(expense.amount, compositeBookingFxRate), 0);
                      const splitBase = Math.max(0, lineBase - lineExpenses);
                      const artistPercent = parseMoneyInput(line.artistPercent);
                      const producerPercent = line.producerPercent ? parseMoneyInput(line.producerPercent) : Math.max(0, 100 - artistPercent);
                      const artistSuggested = splitBase * artistPercent / 100;
                      const producerSuggested = splitBase * producerPercent / 100;
                      const activeExternalShares = line.externalShares.filter((share) => (
                        share.name.trim() || share.percent.trim() || share.amount.trim()
                      ));
                      const externalSuggested = activeExternalShares.reduce((total, share) => {
                        const manualAmount = parseAmountInput(share.amount, compositeBookingFxRate);
                        return total + (manualAmount > 0 ? manualAmount : splitBase * parseMoneyInput(share.percent) / 100);
                      }, 0);
                      const assignedPercent = artistPercent + producerPercent + activeExternalShares.reduce((total, share) => total + parseMoneyInput(share.percent), 0);

                      return (
                        <>
                    <div className="adjustment-card-title">
                      <strong>Linea {index + 1}</strong>
                      <button type="button" onClick={() => removeCompositeBookingLine(line.uid)}>Quitar</button>
                    </div>
                    <div className="row three">
                      <div>
                        <label htmlFor={`composite_line_type_${line.uid}`}>Tipo</label>
                        <select id={`composite_line_type_${line.uid}`} value={line.lineType} onChange={(event) => updateCompositeBookingLineField(line.uid, "lineType", event.target.value as BookingCompositeLineForm["lineType"])}>
                          <option value="artista_vpo">Artista VPO</option>
                          <option value="artista_externo">Artista externo</option>
                          <option value="comision_externa">Comision directa</option>
                        </select>
                      </div>
                      <div>
                        <label htmlFor={`composite_line_desc_${line.uid}`}>Descripcion</label>
                        <input id={`composite_line_desc_${line.uid}`} value={line.description} onChange={(event) => updateCompositeBookingLineField(line.uid, "description", event.target.value)} required />
                      </div>
                      <div>
                        <label htmlFor={`composite_line_amount_${line.uid}`}>Importe base</label>
                        <input id={`composite_line_amount_${line.uid}`} inputMode="decimal" value={line.amount} disabled={line.lineType === "artista_vpo" && line.allocationMode !== "manual"} onChange={(event) => updateCompositeBookingLineField(line.uid, "amount", event.target.value)} />
                      </div>
                    </div>

                    {line.lineType === "artista_vpo" && (
                      <>
                        <div className="row three">
                          <div>
                            <label htmlFor={`composite_allocation_mode_${line.uid}`}>Como calcular la base</label>
                            <select id={`composite_allocation_mode_${line.uid}`} value={line.allocationMode} onChange={(event) => updateCompositeBookingLineField(line.uid, "allocationMode", event.target.value as BookingCompositeLineForm["allocationMode"])}>
                              <option value="equal">Partes iguales del neto madre</option>
                              <option value="net_percent">Porcentaje del neto madre</option>
                              <option value="manual">Importe manual</option>
                            </select>
                            <p className="field-help">Neto madre = bruto menos gastos madre y comisiones directas.</p>
                          </div>
                          <div>
                            <label htmlFor={`composite_allocation_pct_${line.uid}`}>% del neto madre</label>
                            <input id={`composite_allocation_pct_${line.uid}`} inputMode="decimal" value={line.allocationPercent} disabled={line.allocationMode !== "net_percent"} onChange={(event) => updateCompositeBookingLineField(line.uid, "allocationPercent", event.target.value)} placeholder="50" />
                          </div>
                          <div>
                            <label htmlFor={`composite_base_adjustment_${line.uid}`}>Ajuste de base</label>
                            <input id={`composite_base_adjustment_${line.uid}`} inputMode="decimal" value={line.baseAdjustment} onChange={(event) => updateCompositeBookingLineField(line.uid, "baseAdjustment", event.target.value)} placeholder="opcional" />
                            <p className="field-help">Ej: +420000 si una comision directa se incorpora a esta liquidacion.</p>
                          </div>
                        </div>

                        <div className="adjustment-summary">
                          <span>Base calculada {localAmount(lineBase, compositeBookingForm.currency)}</span>
                          {incorporatedForLine > 0 && <span>Comision incorporada {suggestedAmount(incorporatedForLine, compositeBookingForm.currency)}</span>}
                          <span>Gastos artista {localAmount(lineExpenses, compositeBookingForm.currency)}</span>
                          <span>Base split {localAmount(splitBase, compositeBookingForm.currency)}</span>
                          <span>Artista sugerido {suggestedAmount(artistSuggested, compositeBookingForm.currency)}</span>
                          <span>Indyana sugerido {suggestedAmount(producerSuggested, compositeBookingForm.currency)}</span>
                          {externalSuggested > 0 && <span>Externos sugeridos {suggestedAmount(externalSuggested, compositeBookingForm.currency)}</span>}
                          <span>% asignado {assignedPercent.toFixed(2)}%</span>
                        </div>
                        {assignedPercent > 100.001 && (
                          <p className="field-help danger-text">El split de esta linea supera el 100%. Revisa artista, Indyana y terceros.</p>
                        )}

                        <div className="row three">
                          <div>
                            <label htmlFor={`composite_artist_${line.uid}`}>Artista</label>
                            <select id={`composite_artist_${line.uid}`} value={line.artist} onChange={(event) => updateCompositeBookingLineField(line.uid, "artist", event.target.value)} required>
                              <option value="">Elegir artista</option>
                              {bookingArtists.map((artist) => (
                                <option key={artist} value={artist}>{artist}</option>
                              ))}
                            </select>
                          </div>
                          <div>
                            <label htmlFor={`composite_artist_pct_${line.uid}`}>% artista</label>
                            <input id={`composite_artist_pct_${line.uid}`} inputMode="decimal" value={line.artistPercent} onChange={(event) => updateCompositeBookingLineField(line.uid, "artistPercent", event.target.value)} />
                          </div>
                          <div>
                            <label htmlFor={`composite_producer_pct_${line.uid}`}>% Indyana</label>
                            <input id={`composite_producer_pct_${line.uid}`} inputMode="decimal" value={line.producerPercent} onChange={(event) => updateCompositeBookingLineField(line.uid, "producerPercent", event.target.value)} />
                          </div>
                        </div>

                        <div className="show-expenses">
                          <div className="section-heading compact">
                            <div>
                              <h2>Gastos propios del artista</h2>
                            </div>
                            <button type="button" onClick={() => addCompositeBookingLineExpense(line.uid)}>Agregar gasto artista</button>
                          </div>
                          {line.showExpenses.length === 0 && <p className="field-help">Sin gastos propios para esta linea.</p>}
                          {line.showExpenses.map((expense) => (
                            <div className="row three" key={expense.uid}>
                              <select value={expense.category} onChange={(event) => updateCompositeBookingLineExpenseField(line.uid, expense.uid, "category", event.target.value)}>
                                {BOOKING_EXPENSE_CATEGORIES.map((category) => (
                                  <option key={category.value} value={category.value}>{category.label}</option>
                                ))}
                              </select>
                              <input value={expense.concept} onChange={(event) => updateCompositeBookingLineExpenseField(line.uid, expense.uid, "concept", event.target.value)} placeholder="concepto" />
                              <div className="inline-remove">
                                <input inputMode="decimal" value={expense.amount} onChange={(event) => updateCompositeBookingLineExpenseField(line.uid, expense.uid, "amount", event.target.value)} placeholder="importe" />
                                <button type="button" onClick={() => removeCompositeBookingLineExpense(line.uid, expense.uid)}>Quitar</button>
                              </div>
                            </div>
                          ))}
                        </div>

                        <div className="show-expenses">
                          <div className="section-heading compact">
                            <div>
                              <h2>Terceros externos</h2>
                              <p>Participaciones sobre la base split del show hijo, como Fede en G Sony.</p>
                            </div>
                            <button type="button" onClick={() => addCompositeBookingLineExternalShare(line.uid)}>Agregar tercero</button>
                          </div>
                          {line.externalShares.length === 0 && <p className="field-help">Sin terceros externos para esta linea.</p>}
                          {line.externalShares.map((share, shareIndex) => {
                            const shareAmount = parseAmountInput(share.amount, compositeBookingFxRate) || splitBase * parseMoneyInput(share.percent) / 100;
                            const hasShareBasis = parseMoneyInput(share.percent) > 0 || parseAmountInput(share.amount, compositeBookingFxRate) > 0;

                            return (
                              <div className="adjustment-card" key={share.uid}>
                                <div className="adjustment-card-title">
                                  <strong>
                                    Tercero {shareIndex + 1}
                                    {hasShareBasis ? ` - ${suggestedAmount(shareAmount, compositeBookingForm.currency)}` : ""}
                                  </strong>
                                  <button type="button" onClick={() => removeCompositeBookingLineExternalShare(line.uid, share.uid)}>Quitar</button>
                                </div>
                                <div className="row three">
                                  <input value={share.name} onChange={(event) => updateCompositeBookingLineExternalShareField(line.uid, share.uid, "name", event.target.value)} placeholder="Fede" />
                                  <select value={share.role} onChange={(event) => updateCompositeBookingLineExternalShareField(line.uid, share.uid, "role", event.target.value as BookingExternalShareForm["role"])}>
                                    <option value="manager_externo">Manager externo</option>
                                    <option value="socio_externo">Socio externo</option>
                                    <option value="tercero">Tercero</option>
                                    <option value="otro">Otro</option>
                                  </select>
                                  <input inputMode="decimal" value={share.percent} onChange={(event) => updateCompositeBookingLineExternalShareField(line.uid, share.uid, "percent", event.target.value)} placeholder="% sobre base split" />
                                </div>
                                <div className="row">
                                  <div>
                                    <label htmlFor={`composite_external_amount_${share.uid}`}>Importe manual</label>
                                    <input id={`composite_external_amount_${share.uid}`} inputMode="decimal" value={share.amount} onChange={(event) => updateCompositeBookingLineExternalShareField(line.uid, share.uid, "amount", event.target.value)} placeholder="opcional" />
                                    {hasShareBasis && (
                                      <button
                                        type="button"
                                        className="inline-action"
                                        onClick={() => updateCompositeBookingLineExternalShareField(line.uid, share.uid, "amount", String(Math.round(shareAmount * 100) / 100))}
                                      >
                                        Usar sugerido ({suggestedAmount(shareAmount, compositeBookingForm.currency)})
                                      </button>
                                    )}
                                  </div>
                                  <label className="checkbox-field">
                                    <input type="checkbox" checked={share.cashHandledByVpo} onChange={(event) => updateCompositeBookingLineExternalShareField(line.uid, share.uid, "cashHandledByVpo", event.target.checked)} />
                                    Caja manejada por VPO
                                  </label>
                                </div>
                                <textarea value={share.notes} onChange={(event) => updateCompositeBookingLineExternalShareField(line.uid, share.uid, "notes", event.target.value)} placeholder="Nota del tercero" />
                              </div>
                            );
                          })}
                        </div>

                        <label className="checkbox-field">
                          <input type="checkbox" checked={line.bookingCommissionExempt} onChange={(event) => updateCompositeBookingLineField(line.uid, "bookingCommissionExempt", event.target.checked)} />
                          Excluir de comision general de booking
                        </label>
                        {line.bookingCommissionExempt && (
                          <textarea value={line.bookingCommissionNotes} onChange={(event) => updateCompositeBookingLineField(line.uid, "bookingCommissionNotes", event.target.value)} placeholder="Motivo: comision directa, regla especial, sociedad, etc." />
                        )}

                        <div className="row">
                          <div>
                            <label htmlFor={`composite_artist_paid_${line.uid}`}>Pagado artista</label>
                            <input id={`composite_artist_paid_${line.uid}`} inputMode="decimal" value={line.artistPaidAmount} onChange={(event) => updateCompositeBookingLineField(line.uid, "artistPaidAmount", event.target.value)} />
                            <button
                              type="button"
                              className="inline-action"
                              onClick={() => updateCompositeBookingLineField(line.uid, "artistPaidAmount", String(Math.round(artistSuggested * 100) / 100))}
                            >
                              Usar sugerido ({suggestedAmount(artistSuggested, compositeBookingForm.currency)})
                            </button>
                          </div>
                          <div>
                            <label htmlFor={`composite_producer_received_${line.uid}`}>Recibido Indyana</label>
                            <input id={`composite_producer_received_${line.uid}`} inputMode="decimal" value={line.producerReceivedAmount} onChange={(event) => updateCompositeBookingLineField(line.uid, "producerReceivedAmount", event.target.value)} />
                            <button
                              type="button"
                              className="inline-action"
                              onClick={() => updateCompositeBookingLineField(line.uid, "producerReceivedAmount", String(Math.round(producerSuggested * 100) / 100))}
                            >
                              Usar sugerido ({suggestedAmount(producerSuggested, compositeBookingForm.currency)})
                            </button>
                          </div>
                        </div>
                      </>
                    )}

                    {line.lineType !== "artista_vpo" && (
                      <div className="row">
                        <div>
                          <label htmlFor={`composite_external_notes_${line.uid}`}>Notas</label>
                          <textarea id={`composite_external_notes_${line.uid}`} value={line.notes} onChange={(event) => updateCompositeBookingLineField(line.uid, "notes", event.target.value)} />
                        </div>
                      </div>
                    )}
                        </>
                      );
                    })()}
                  </div>
                ))}
              </div>

              <label htmlFor="composite_receipts">Comprobantes / links</label>
              <textarea id="composite_receipts" value={compositeBookingForm.receiptRefs} onChange={(event) => updateCompositeBookingField("receiptRefs", event.target.value)} placeholder="Uno por linea" />

              <label htmlFor="composite_notes">Notas generales</label>
              <textarea id="composite_notes" value={compositeBookingForm.notes} onChange={(event) => updateCompositeBookingField("notes", event.target.value)} />

              <button type="submit" disabled={compositeBookingLoading}>
                {compositeBookingLoading
                  ? "Guardando..."
                  : compositeBookingEditingId
                    ? "Actualizar liquidacion compuesta"
                    : compositeBookingSaveMode === "simple"
                      ? "Guardar show simple"
                      : "Guardar evento madre"}
              </button>
              {compositeBookingEditingId && (
                <button type="button" className="secondary" onClick={resetCompositeBookingForm}>
                  Cancelar edicion
                </button>
              )}
            </form>

            {compositeBookingEvents.length === 0 && (
              <p className="field-help">Todavia no hay liquidaciones compuestas cargadas.</p>
            )}

            <div className="event-list">
              {compositeBookingEvents.map((event) => (
                <article className="event-card" key={event.id}>
                  <div className="event-card-header">
                    <div>
                      <strong>{event.venue}</strong>
                      <span>{event.event_date} - #{event.id} - {event.status}</span>
                    </div>
                    <div className="button-row">
                      <button type="button" onClick={() => editCompositeBookingEvent(event)}>Editar</button>
                      <span className={event.balance_amount === 0 ? "status-pill ok" : "status-pill warning"}>
                        {event.balance_amount === 0 ? "Cerrado" : "Pendiente"}
                      </span>
                    </div>
                  </div>

                  <div className="control-dashboard">
                    <div>
                      <span>Bruto</span>
                      <strong>{localAmount(event.gross_amount, event.currency)}</strong>
                    </div>
                    <div>
                      <span>Gastos operativos</span>
                      <strong>{localAmount(event.operational_expenses_amount, event.currency)}</strong>
                    </div>
                    <div>
                      <span>Comisiones directas</span>
                      <strong>{localAmount(event.direct_commissions_amount, event.currency)}</strong>
                    </div>
                    <div>
                      <span>Base artistica neta</span>
                      <strong>{localAmount(event.artist_base_amount, event.currency)}</strong>
                    </div>
                    <div>
                      <span>Indyana esperada</span>
                      <strong>{localAmount(event.producer_expected_amount, event.currency)}</strong>
                    </div>
                    <div className={event.balance_amount === 0 ? "" : "warn"}>
                      <span>Saldo</span>
                      <strong>{localAmount(event.balance_amount, event.currency)}</strong>
                    </div>
                  </div>

                  {event.notes && <p className="field-help">{event.notes}</p>}

                  <div className="summary-table-wrap">
                    <table className="summary-table">
                      <thead>
                        <tr>
                          <th>Tipo</th>
                          <th>Descripcion</th>
                          <th>Artista</th>
                          <th>Base</th>
                          <th>Artista</th>
                          <th>Indyana</th>
                          <th>Show hijo</th>
                        </tr>
                      </thead>
                      <tbody>
                        {event.lines.map((line) => (
                          <tr key={line.id}>
                            <td>{line.line_type}</td>
                            <td>{line.description}</td>
                            <td>{line.artist || "-"}</td>
                            <td>{localAmount(line.amount, event.currency)}</td>
                            <td>{localAmount(line.artist_paid_amount, event.currency)}</td>
                            <td>{localAmount(line.producer_received_amount, event.currency)}</td>
                            <td>{line.booking_show_id ? `#${line.booking_show_id}` : "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}

        {view === "caserio" && (
          <div className="grid booking-grid">
            <form className="panel" onSubmit={submitCaserio}>
              <div className="section-heading compact">
                <div>
                  <h1>El Caserio</h1>
                  <p>Evento sociedad separado del booking VPO. Las lineas de artista VPO crean show vinculado.</p>
                </div>
              </div>

              <div className="row">
                <div>
                  <label htmlFor="caserio_date">Fecha</label>
                  <input id="caserio_date" type="date" value={caserioForm.eventDate} onChange={(event) => updateCaserioField("eventDate", event.target.value)} required />
                </div>
                <div>
                  <label htmlFor="caserio_venue">Venue / evento</label>
                  <input id="caserio_venue" value={caserioForm.venue} onChange={(event) => updateCaserioField("venue", event.target.value)} required />
                </div>
              </div>

              <div className="row">
                <div>
                  <label htmlFor="caserio_city">Ciudad</label>
                  <input id="caserio_city" value={caserioForm.city} onChange={(event) => updateCaserioField("city", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="caserio_responsible">Responsable</label>
                  <input id="caserio_responsible" value={caserioForm.responsible} onChange={(event) => updateCaserioField("responsible", event.target.value)} />
                </div>
              </div>

              <div className="row three">
                <div>
                  <label htmlFor="caserio_gross">Ingreso bruto evento</label>
                  <input id="caserio_gross" inputMode="decimal" value={caserioForm.grossAmount} onChange={(event) => updateCaserioField("grossAmount", event.target.value)} required />
                </div>
                <div>
                  <label htmlFor="caserio_received">Rendido a VPO</label>
                  <input id="caserio_received" inputMode="decimal" value={caserioForm.receivedAmount} onChange={(event) => updateCaserioField("receivedAmount", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="caserio_status">Estado</label>
                  <select id="caserio_status" value={caserioForm.status} onChange={(event) => updateCaserioField("status", event.target.value)}>
                    <option value="borrador">Borrador</option>
                    <option value="rendido">Rendido</option>
                    <option value="observado">Observado</option>
                    <option value="cerrado">Cerrado</option>
                  </select>
                </div>
              </div>

              <div className="booking-suggestion">
                <div>
                  <span>A rendir Caserio</span>
                  <strong>{localAmount(caserioPreview.caserioExpected, caserioForm.currency)}</strong>
                </div>
                <div>
                  <span>A rendir Indyana</span>
                  <strong>{localAmount(caserioPreview.producerExpected, caserioForm.currency)}</strong>
                </div>
                <div>
                  <span>Total caja esperada</span>
                  <strong>{localAmount(caserioPreview.totalExpected, caserioForm.currency)}</strong>
                </div>
                <div>
                  <span>Diferencia</span>
                  <strong>{localAmount(caserioPreview.balance, caserioForm.currency)}</strong>
                </div>
              </div>

              <div className="show-expenses">
                <div className="section-heading compact">
                  <div>
                    <h2>Lineas del evento</h2>
                    <p>Gastos generales, artistas externos o artistas VPO que crean show interno.</p>
                  </div>
                  <div className="button-row">
                    <button type="button" onClick={() => addCaserioLine("gasto_general")}>Gasto</button>
                    <button type="button" onClick={() => addCaserioLine("artista_externo")}>Externo</button>
                    <button type="button" onClick={() => addCaserioLine("artista_vpo")}>Artista VPO</button>
                  </div>
                </div>

                {caserioForm.lines.length === 0 && <p className="field-help">Agrega al menos una linea si hubo gastos o artistas dentro del evento.</p>}

                {caserioForm.lines.map((line, index) => (
                  <div className="expense-card" key={line.uid}>
                    <div className="adjustment-card-title">
                      <strong>Linea {index + 1}</strong>
                      <button type="button" onClick={() => removeCaserioLine(line.uid)}>Quitar</button>
                    </div>

                    <div className="row three">
                      <div>
                        <label htmlFor={`caserio_line_type_${line.uid}`}>Tipo</label>
                        <select id={`caserio_line_type_${line.uid}`} value={line.lineType} onChange={(event) => updateCaserioLineField(line.uid, "lineType", event.target.value as CaserioLineForm["lineType"])}>
                          <option value="gasto_general">Gasto general</option>
                          <option value="artista_externo">Artista externo</option>
                          <option value="artista_vpo">Artista VPO</option>
                        </select>
                      </div>
                      <div>
                        <label htmlFor={`caserio_line_description_${line.uid}`}>Descripcion</label>
                        <input id={`caserio_line_description_${line.uid}`} value={line.description} onChange={(event) => updateCaserioLineField(line.uid, "description", event.target.value)} required />
                      </div>
                      <div>
                        <label htmlFor={`caserio_line_amount_${line.uid}`}>Importe</label>
                        <input id={`caserio_line_amount_${line.uid}`} inputMode="decimal" value={line.amount} onChange={(event) => updateCaserioLineField(line.uid, "amount", event.target.value)} />
                      </div>
                    </div>

                    {line.lineType === "artista_vpo" && (
                      <>
                        <div className="row three">
                          <div>
                            <label htmlFor={`caserio_line_artist_${line.uid}`}>Artista VPO</label>
                            <select id={`caserio_line_artist_${line.uid}`} value={line.artist} onChange={(event) => updateCaserioLineField(line.uid, "artist", event.target.value)} required>
                              <option value="">Elegir artista</option>
                              {bookingArtists.map((artist) => (
                                <option key={artist} value={artist}>{artist}</option>
                              ))}
                            </select>
                          </div>
                          <div>
                            <label htmlFor={`caserio_line_artist_pct_${line.uid}`}>% artista</label>
                            <input id={`caserio_line_artist_pct_${line.uid}`} inputMode="decimal" value={line.artistPercent} onChange={(event) => updateCaserioLineField(line.uid, "artistPercent", event.target.value)} />
                          </div>
                          <div>
                            <label htmlFor={`caserio_line_producer_pct_${line.uid}`}>% Indyana</label>
                            <input id={`caserio_line_producer_pct_${line.uid}`} inputMode="decimal" value={line.producerPercent} onChange={(event) => updateCaserioLineField(line.uid, "producerPercent", event.target.value)} />
                          </div>
                        </div>

                        <div className="section-heading compact">
                          <div>
                            <h2>Gastos propios del artista</h2>
                          </div>
                          <button type="button" onClick={() => addCaserioLineExpense(line.uid)}>Agregar gasto artista</button>
                        </div>
                        {line.showExpenses.map((expense) => (
                          <div className="row three" key={expense.uid}>
                            <input value={expense.category} onChange={(event) => updateCaserioLineExpenseField(line.uid, expense.uid, "category", event.target.value)} placeholder="categoria" />
                            <input value={expense.concept} onChange={(event) => updateCaserioLineExpenseField(line.uid, expense.uid, "concept", event.target.value)} placeholder="concepto" />
                            <div className="inline-remove">
                              <input value={expense.amount} onChange={(event) => updateCaserioLineExpenseField(line.uid, expense.uid, "amount", event.target.value)} placeholder="importe" />
                              <button type="button" onClick={() => removeCaserioLineExpense(line.uid, expense.uid)}>Quitar</button>
                            </div>
                          </div>
                        ))}
                      </>
                    )}

                    <label htmlFor={`caserio_line_notes_${line.uid}`}>Notas</label>
                    <textarea id={`caserio_line_notes_${line.uid}`} value={line.notes} onChange={(event) => updateCaserioLineField(line.uid, "notes", event.target.value)} />
                  </div>
                ))}
              </div>

              <label htmlFor="caserio_receipts">Comprobantes / links</label>
              <textarea id="caserio_receipts" value={caserioForm.receiptRefs} onChange={(event) => updateCaserioField("receiptRefs", event.target.value)} />

              <label htmlFor="caserio_notes">Notas</label>
              <textarea id="caserio_notes" value={caserioForm.notes} onChange={(event) => updateCaserioField("notes", event.target.value)} />

              <button type="submit" disabled={caserioLoading}>{caserioLoading ? "Guardando..." : "Guardar evento Caserio"}</button>
            </form>

            <section className="panel">
              <div className="section-heading">
                <div>
                  <h2>Eventos Caserio</h2>
                  <p>Resumen de caja sociedad y shows VPO creados automaticamente.</p>
                </div>
                <button type="button" onClick={loadCaserioEvents}>Actualizar</button>
              </div>

              <div className="booking-list">
                {caserioEvents.length === 0 && <p className="field-help">Todavia no hay eventos Caserio cargados.</p>}
                {caserioEvents.map((item) => (
                  <article className="booking-item" key={item.id}>
                    <div>
                      <strong>{item.venue}</strong>
                      <span>{item.event_date}{item.city ? ` - ${item.city}` : ""}{item.responsible ? ` - ${item.responsible}` : ""}</span>
                    </div>
                    <div className="booking-metrics">
                      <span>Bruto {localAmount(item.gross_amount, item.currency)}</span>
                      <span>Caserio {localAmount(item.caserio_expected_amount, item.currency)}</span>
                      <span>Indyana {localAmount(item.producer_expected_amount, item.currency)}</span>
                      <span>Total caja {localAmount(item.total_expected_amount, item.currency)}</span>
                      <span>Rendido {localAmount(item.received_amount, item.currency)}</span>
                      <span>Balance {localAmount(item.balance_amount, item.currency)}</span>
                    </div>
                    <div className="booking-status">
                      <span>{item.status}</span>
                      <span>{item.lines.length} linea(s)</span>
                      {item.lines.filter((line) => line.booking_show_id).length > 0 && (
                        <span>{item.lines.filter((line) => line.booking_show_id).length} show(s) VPO</span>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </div>
        )}

        {view === "artists" && (
          <div className="grid artist-grid">
            <form className="panel" onSubmit={submitArtistRecord}>
              <div className="section-heading compact">
                <div>
                  <h1>{artistRecordEditingId ? `Editando artista #${artistRecordEditingId}` : "ABM de artistas"}</h1>
                  <p>Ficha base para booking: nombre artistico, datos legales y contacto.</p>
                </div>
                {artistRecordEditingId && (
                  <button type="button" onClick={resetArtistRecordForm}>Cancelar</button>
                )}
              </div>

              <label htmlFor="artist_stage_name">Nombre artistico</label>
              <input
                id="artist_stage_name"
                value={artistRecordForm.stageName}
                onChange={(event) => updateArtistRecordField("stageName", event.target.value)}
                required
              />

              <label htmlFor="artist_legal_name">Nombre real / razon social</label>
              <input
                id="artist_legal_name"
                value={artistRecordForm.legalName}
                onChange={(event) => updateArtistRecordField("legalName", event.target.value)}
              />

              <div className="row">
                <div>
                  <label htmlFor="artist_cuit">CUIT / CUIL</label>
                  <input
                    id="artist_cuit"
                    value={artistRecordForm.cuit}
                    onChange={(event) => updateArtistRecordField("cuit", event.target.value)}
                  />
                </div>
                <div>
                  <label htmlFor="artist_phone">Telefono</label>
                  <input
                    id="artist_phone"
                    value={artistRecordForm.phone}
                    onChange={(event) => updateArtistRecordField("phone", event.target.value)}
                  />
                </div>
              </div>

              <label htmlFor="artist_email">Email</label>
              <input
                id="artist_email"
                type="email"
                value={artistRecordForm.email}
                onChange={(event) => updateArtistRecordField("email", event.target.value)}
              />

              <label htmlFor="artist_address">Domicilio</label>
              <input
                id="artist_address"
                value={artistRecordForm.address}
                onChange={(event) => updateArtistRecordField("address", event.target.value)}
              />

              <label htmlFor="artist_notes">Notas</label>
              <textarea
                id="artist_notes"
                value={artistRecordForm.notes}
                onChange={(event) => updateArtistRecordField("notes", event.target.value)}
              />

              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={artistRecordForm.active}
                  onChange={(event) => updateArtistRecordField("active", event.target.checked)}
                />
                Activo en selector de booking
              </label>

              <button type="submit" disabled={artistRecordLoading}>
                {artistRecordLoading ? "Guardando..." : artistRecordEditingId ? "Guardar cambios" : "Crear artista"}
              </button>
            </form>

            <section className="panel">
              <div className="section-heading compact">
                <div>
                  <h1>Artistas</h1>
                  <p>Los inactivos quedan guardados, pero no aparecen para cargar nuevos shows.</p>
                </div>
                <button type="button" onClick={loadArtistRecords}>Actualizar</button>
              </div>

              <label htmlFor="artist_record_search">Buscar artista</label>
              <input
                id="artist_record_search"
                value={artistRecordSearch}
                onChange={(event) => setArtistRecordSearch(event.target.value)}
                placeholder="Nombre artistico, real, CUIT, telefono, email"
              />
              <p className="field-help">
                Mostrando {filteredArtistRecords.length} de {artistRecords.length} ficha(s).
              </p>

              <div className="artist-record-list">
                {artistRecords.length === 0 && (
                  <p className="field-help">Todavia no hay fichas manuales cargadas.</p>
                )}
                {artistRecords.length > 0 && filteredArtistRecords.length === 0 && (
                  <p className="field-help">No hay artistas que coincidan con la busqueda.</p>
                )}

                {filteredArtistRecords.map((item) => (
                  <div className={`artist-record-item ${item.active ? "" : "inactive"}`} key={item.id}>
                    <div>
                      <strong>{item.stage_name}</strong>
                      <span>{item.legal_name || "Sin nombre real cargado"}</span>
                    </div>
                    <div className="artist-record-meta">
                      <span>{item.cuit || "Sin CUIT"}</span>
                      <span>{item.phone || "Sin telefono"}</span>
                      <span>{item.email || "Sin email"}</span>
                      <span>{item.active ? "Activo" : "Inactivo"}</span>
                    </div>
                    {item.address && <p>{item.address}</p>}
                    {item.notes && <p>{item.notes}</p>}
                    <div className="booking-actions">
                      <button type="button" onClick={() => editArtistRecord(item)}>Editar</button>
                      {item.active && (
                        <button type="button" className="secondary-danger" onClick={() => deactivateArtistRecord(item)}>
                          Desactivar
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {view === "booking" && (
          <div className="grid booking-grid">
            <form className="panel" onSubmit={submitBooking}>
              <div className="section-heading compact">
                <div>
                  <h1>{bookingEditingId ? `Editando show #${bookingEditingId}` : "Booking Indyana"}</h1>
                  <p>{bookingEditingId ? "Guardar reemplaza los datos de esta carga." : "Alta directa de show propio, gastos, split y rendicion inicial."}</p>
                </div>
                {bookingEditingId && (
                  <button type="button" onClick={resetBookingForm}>Cancelar edicion</button>
                )}
              </div>

              <div className="row">
                <div>
                  <label htmlFor="booking_artist">Artista</label>
                  <select id="booking_artist" value={bookingForm.artist} onChange={(event) => updateBookingField("artist", event.target.value)} required>
                    <option value="">Elegir artista</option>
                    {bookingArtists.map((artist) => (
                      <option key={artist} value={artist}>{artist}</option>
                    ))}
                  </select>
                  {bookingArtists.length === 0 && <p className="field-help">No hay artistas disponibles para cargar.</p>}
                </div>
                <div>
                  <label htmlFor="booking_date">Fecha</label>
                  <input id="booking_date" type="date" value={bookingForm.showDate} onChange={(event) => updateBookingField("showDate", event.target.value)} required />
                </div>
              </div>

              <div className="row">
                <div>
                  <label htmlFor="booking_venue">Venue / evento</label>
                  <input id="booking_venue" value={bookingForm.venue} onChange={(event) => updateBookingField("venue", event.target.value)} required />
                </div>
                <div>
                  <label htmlFor="booking_city">Ciudad</label>
                  <input id="booking_city" value={bookingForm.city} onChange={(event) => updateBookingField("city", event.target.value)} />
                </div>
              </div>

              <div className="row">
                <div>
                  <label htmlFor="booking_tm">Tour manager</label>
                  <input id="booking_tm" value={bookingForm.tourManager} onChange={(event) => updateBookingField("tourManager", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="booking_status">Estado</label>
                  <select id="booking_status" value={bookingForm.status} onChange={(event) => updateBookingField("status", event.target.value)}>
                    <option value="realizado">Realizado</option>
                    <option value="pendiente">Pendiente</option>
                    <option value="rendido">Rendido</option>
                    <option value="aprobado">Aprobado</option>
                    <option value="no_cobrado">No cobrado</option>
                    <option value="cancelado">Cancelado</option>
                  </select>
                </div>
              </div>

              <div className="row three">
                <div>
                  <label htmlFor="booking_currency">Moneda</label>
                  <select id="booking_currency" value={bookingForm.currency} onChange={(event) => updateBookingField("currency", event.target.value as "ARS" | "USD")}>
                    <option value="ARS">ARS</option>
                    <option value="USD">USD</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="booking_fx">Tipo de cambio</label>
                  <input id="booking_fx" inputMode="decimal" value={bookingForm.fxRate} onChange={(event) => updateBookingField("fxRate", event.target.value)} placeholder="opcional" />
                </div>
                <div>
                  <label htmlFor="booking_cachet">Cachet pactado</label>
                  <input id="booking_cachet" inputMode="decimal" value={bookingForm.cachetAmount} onChange={(event) => updateBookingField("cachetAmount", event.target.value)} placeholder="1000000" />
                </div>
              </div>

              <div className="booking-payment-box">
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={bookingForm.venuePaymentIssue}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setBookingForm((current) => ({
                        ...current,
                        venuePaymentIssue: checked,
                        venueCollectedAmount: checked && !current.venueCollectedAmount ? current.cachetAmount : current.venueCollectedAmount,
                        venuePaymentNotes: checked ? current.venuePaymentNotes : "",
                      }));
                    }}
                  />
                  <span>El boliche pago menos o quedo deuda de cachet</span>
                </label>

                {bookingForm.venuePaymentIssue && (
                  <>
                    <div className="row">
                      <div>
                        <label htmlFor="booking_venue_collected">Cobrado real</label>
                        <input id="booking_venue_collected" inputMode="decimal" value={bookingForm.venueCollectedAmount} onChange={(event) => updateBookingField("venueCollectedAmount", event.target.value)} placeholder="0" />
                      </div>
                      <div>
                        <label>Deuda boliche</label>
                        <div className={bookingVenueBalance > 0 ? "readonly-metric danger-text" : "readonly-metric"}>
                          {localAmount(bookingVenueBalance, bookingForm.currency)}
                        </div>
                      </div>
                    </div>
                    <label htmlFor="booking_venue_payment_notes">Nota deuda boliche</label>
                    <textarea id="booking_venue_payment_notes" value={bookingForm.venuePaymentNotes} onChange={(event) => updateBookingField("venuePaymentNotes", event.target.value)} placeholder="Ej: cachet pactado 1.500.000, el venue pago 1.000.000 y queda deuda." />
                    <p className="field-help">Los calculos del show usan el cobrado real. La diferencia queda como alerta separada de la rendicion del PM.</p>
                  </>
                )}
              </div>

              <div className="show-expenses">
                <div className="section-heading compact">
                  <div>
                    <h2>Gastos del show</h2>
                    <p>Carga por concepto para caja y analisis futuro.</p>
                  </div>
                  <button type="button" onClick={() => addBookingExpense()}>Agregar gasto</button>
                </div>

                {bookingForm.showExpenses.length === 0 && (
                  <p className="field-help">Sin gastos cargados. Si preferis un gasto unico, agregalo como categoria general.</p>
                )}

                {bookingForm.showExpenses.length > 0 && (
                  <div className="adjustment-summary">
                    <span>Total gastos {localAmount(bookingExpenseTotal, bookingForm.currency)}</span>
                  </div>
                )}

                {bookingForm.showExpenses.map((expense, index) => (
                  <div className="expense-card" key={expense.uid}>
                    <div className="adjustment-card-title">
                      <strong>Gasto {index + 1}</strong>
                      <button type="button" onClick={() => removeBookingExpense(expense.uid)}>Quitar</button>
                    </div>

                    <div className="row three">
                      <div>
                        <label htmlFor={`expense_category_${expense.uid}`}>Categoria</label>
                        <select id={`expense_category_${expense.uid}`} value={expense.category} onChange={(event) => updateBookingExpenseField(expense.uid, "category", event.target.value)}>
                          {BOOKING_EXPENSE_CATEGORIES.map((category) => (
                            <option key={category.value} value={category.value}>{category.label}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label htmlFor={`expense_concept_${expense.uid}`}>Concepto</label>
                        <input id={`expense_concept_${expense.uid}`} value={expense.concept} onChange={(event) => updateBookingExpenseField(expense.uid, "concept", event.target.value)} placeholder="Sonido, Facha 15%, guitarra, nafta" />
                        <p className="field-help">Opcional: si lo dejas vacio se guarda con la categoria.</p>
                      </div>
                      <div>
                        <label htmlFor={`expense_amount_${expense.uid}`}>Importe</label>
                        <input id={`expense_amount_${expense.uid}`} inputMode="decimal" value={expense.amount} onChange={(event) => updateBookingExpenseField(expense.uid, "amount", event.target.value)} />
                      </div>
                    </div>

                    <label htmlFor={`expense_notes_${expense.uid}`}>Nota del gasto</label>
                    <textarea id={`expense_notes_${expense.uid}`} value={expense.notes} onChange={(event) => updateBookingExpenseField(expense.uid, "notes", event.target.value)} />
                  </div>
                ))}
              </div>

              <div className="artist-adjustments">
                <div className="section-heading compact">
                  <div>
                    <h2>Ajustes antes del split</h2>
                    <p>Importes que salen del neto antes de calcular el 70/30 u otro acuerdo.</p>
                  </div>
                  <div className="button-row">
                    <button type="button" onClick={() => addBookingPreSplitAdjustment("producer")}>A Indyana</button>
                    <button type="button" onClick={() => addBookingPreSplitAdjustment("artist")}>Al artista</button>
                  </div>
                </div>

                {bookingForm.preSplitAdjustments.length === 0 && (
                  <p className="field-help">Sin ajustes antes del split. Usalo para recuperos o deudas pagadas desde la caja del show.</p>
                )}

                {bookingForm.preSplitAdjustments.length > 0 && (
                  <div className="adjustment-summary">
                    <span>Total ajustes {localAmount(bookingPreSplitSummary.total, bookingForm.currency)}</span>
                    <span>A Indyana {localAmount(bookingPreSplitSummary.producer, bookingForm.currency)}</span>
                    <span>Al artista {localAmount(bookingPreSplitSummary.artist, bookingForm.currency)}</span>
                    <span>Base split {localAmount(bookingSuggestion.splitBase, bookingForm.currency)}</span>
                  </div>
                )}

                {bookingForm.preSplitAdjustments.map((adjustment, index) => (
                  <div className="adjustment-card" key={adjustment.uid}>
                    <div className="adjustment-card-title">
                      <strong>Ajuste antes del split {index + 1}</strong>
                      <button type="button" onClick={() => removeBookingPreSplitAdjustment(adjustment.uid)}>Quitar</button>
                    </div>

                    <div className="row three">
                      <div>
                        <label htmlFor={`pre_split_concept_${adjustment.uid}`}>Concepto</label>
                        <input id={`pre_split_concept_${adjustment.uid}`} value={adjustment.concept} onChange={(event) => updateBookingPreSplitAdjustmentField(adjustment.uid, "concept", event.target.value)} placeholder="Recupero DJ set, Uber adeudado" />
                      </div>
                      <div>
                        <label htmlFor={`pre_split_destination_${adjustment.uid}`}>Destino</label>
                        <select id={`pre_split_destination_${adjustment.uid}`} value={adjustment.destination} onChange={(event) => updateBookingPreSplitAdjustmentField(adjustment.uid, "destination", event.target.value as "artist" | "producer")}>
                          <option value="producer">Indyana</option>
                          <option value="artist">Artista</option>
                        </select>
                      </div>
                      <div>
                        <label htmlFor={`pre_split_amount_${adjustment.uid}`}>Importe</label>
                        <input id={`pre_split_amount_${adjustment.uid}`} inputMode="decimal" value={adjustment.amount} onChange={(event) => updateBookingPreSplitAdjustmentField(adjustment.uid, "amount", event.target.value)} />
                      </div>
                    </div>

                    <label htmlFor={`pre_split_notes_${adjustment.uid}`}>Nota</label>
                    <textarea id={`pre_split_notes_${adjustment.uid}`} value={adjustment.notes} onChange={(event) => updateBookingPreSplitAdjustmentField(adjustment.uid, "notes", event.target.value)} />
                  </div>
                ))}
              </div>

              <div className="artist-adjustments">
                <div className="section-heading compact">
                  <div>
                    <h2>Caja / señas del show</h2>
                    <p>Movimientos reales de plata. El sistema los compara contra la liquidacion sugerida.</p>
                  </div>
                  <div className="button-row">
                    <button type="button" onClick={() => addBookingCashMovement("producer")}>Ingreso Indyana</button>
                    <button type="button" onClick={() => addBookingCashMovement("artist")}>Ingreso artista</button>
                  </div>
                </div>

                {bookingForm.cashMovements.length === 0 && (
                  <p className="field-help">Sin caja detallada. PodÃ©s usar los campos pagado/rendido de abajo como antes.</p>
                )}

                {bookingForm.cashMovements.length > 0 && (
                  <div className="adjustment-summary">
                    <span>Recibio Indyana {localAmount(bookingCashSummary.producer, bookingForm.currency)}</span>
                    <span>Recibio artista {localAmount(bookingCashSummary.artist, bookingForm.currency)}</span>
                    <span>Total caja show {localAmount(bookingCashSummary.total, bookingForm.currency)}</span>
                  </div>
                )}

                {bookingForm.cashMovements.map((movement, index) => (
                  <div className="adjustment-card" key={movement.uid}>
                    <div className="adjustment-card-title">
                      <strong>Movimiento caja {index + 1}</strong>
                      <button type="button" onClick={() => removeBookingCashMovement(movement.uid)}>Quitar</button>
                    </div>

                    <div className="row three">
                      <div>
                        <label htmlFor={`cash_recipient_${movement.uid}`}>Recibio</label>
                        <select id={`cash_recipient_${movement.uid}`} value={movement.recipient} onChange={(event) => updateBookingCashMovementField(movement.uid, "recipient", event.target.value as BookingCashMovementForm["recipient"])}>
                          <option value="producer">Indyana</option>
                          <option value="artist">Artista</option>
                        </select>
                      </div>
                      <div>
                        <label htmlFor={`cash_method_${movement.uid}`}>Tipo</label>
                        <select id={`cash_method_${movement.uid}`} value={movement.paymentMethod} onChange={(event) => updateBookingCashMovementField(movement.uid, "paymentMethod", event.target.value as BookingCashMovementForm["paymentMethod"])}>
                          <option value="seña">Seña</option>
                          <option value="transferencia">Transferencia</option>
                          <option value="efectivo">Efectivo</option>
                          <option value="otro">Otro</option>
                        </select>
                      </div>
                      <div>
                        <label htmlFor={`cash_amount_${movement.uid}`}>Importe</label>
                        <input id={`cash_amount_${movement.uid}`} inputMode="decimal" value={movement.amount} onChange={(event) => updateBookingCashMovementField(movement.uid, "amount", event.target.value)} />
                      </div>
                    </div>

                    <div className="row">
                      <div>
                        <label htmlFor={`cash_concept_${movement.uid}`}>Concepto</label>
                        <input id={`cash_concept_${movement.uid}`} value={movement.concept} onChange={(event) => updateBookingCashMovementField(movement.uid, "concept", event.target.value)} placeholder="Seña, pago show, diferencia, transferencia final" />
                      </div>
                      <div>
                        <label htmlFor={`cash_paid_by_${movement.uid}`}>Pagado por / origen</label>
                        <input id={`cash_paid_by_${movement.uid}`} value={movement.paidBy} onChange={(event) => updateBookingCashMovementField(movement.uid, "paidBy", event.target.value)} placeholder="Boliche, PM, Carolina, artista" />
                      </div>
                    </div>

                    <label htmlFor={`cash_notes_${movement.uid}`}>Nota / comprobante</label>
                    <textarea id={`cash_notes_${movement.uid}`} value={movement.notes} onChange={(event) => updateBookingCashMovementField(movement.uid, "notes", event.target.value)} />
                  </div>
                ))}
              </div>

              <div className="row">
                <div>
                  <label htmlFor="booking_artist_paid">Pagado al artista</label>
                  <input
                    id="booking_artist_paid"
                    inputMode="decimal"
                    value={bookingForm.artistPaidAmount}

                    onChange={(event) => updateBookingField("artistPaidAmount", event.target.value)}
                  />
                  <button
                    type="button"
                    className="inline-action"

                    onClick={() => updateBookingField("artistPaidAmount", String(Math.round(Math.max(0, bookingFinalSuggestion.artistPayable - bookingCashSummary.artist) * 100) / 100))}
                  >
                    Usar sugerido ({localAmount(Math.max(0, bookingFinalSuggestion.artistPayable - bookingCashSummary.artist), bookingForm.currency)})
                  </button>
                  <p className="field-help">
                    Diferencia artista: {localAmount(bookingFinalSuggestion.artistPayable - bookingCashSummary.artist - parseAmountInput(bookingForm.artistPaidAmount, bookingFxRate), bookingForm.currency)}
                  </p>
                </div>
                <div>
                  <label>Total gastos del show</label>
                  <div className="readonly-metric">{localAmount(bookingExpenseTotal, bookingForm.currency)}</div>
                </div>
              </div>

              <div className="row three">
                <div>
                  <label htmlFor="booking_artist_pct">% artista</label>
                  <input id="booking_artist_pct" inputMode="decimal" value={bookingForm.artistPercent} onChange={(event) => updateBookingField("artistPercent", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="booking_producer_pct">% productora</label>
                  <input id="booking_producer_pct" inputMode="decimal" value={bookingForm.producerPercent} onChange={(event) => updateBookingField("producerPercent", event.target.value)} />
                  {bookingForm.externalShares.length > 0 && (
                    <button
                      type="button"
                      className="inline-action"
                      onClick={() => updateBookingField("producerPercent", String(bookingSplitPercentSummary.remainingPercent))}
                    >
                      Usar restante ({bookingSplitPercentSummary.remainingPercent.toFixed(2)}%)
                    </button>
                  )}
                </div>
                <div>
                  <label htmlFor="booking_producer_received">Rendido a productora</label>
                  <input
                    id="booking_producer_received"
                    inputMode="decimal"
                    value={bookingForm.producerReceivedAmount}

                    onChange={(event) => updateBookingField("producerReceivedAmount", event.target.value)}
                  />
                  <button
                    type="button"
                    className="inline-action"

                    onClick={() => updateBookingField("producerReceivedAmount", String(Math.round(Math.max(0, bookingFinalSuggestion.producerCash - bookingCashSummary.producer) * 100) / 100))}
                  >
                    Usar sugerido ({localAmount(Math.max(0, bookingFinalSuggestion.producerCash - bookingCashSummary.producer), bookingForm.currency)})
                  </button>
                  <p className="field-help">
                    Diferencia Indyana: {localAmount(bookingFinalSuggestion.producerCash - bookingCashSummary.producer - parseAmountInput(bookingForm.producerReceivedAmount, bookingFxRate), bookingForm.currency)}
                  </p>
                </div>
              </div>

              <div className="artist-adjustments">
                <div className="section-heading compact">
                  <div>
                    <h2>Participaciones externas</h2>
                    <p>Terceros que cobran parte del neto, sin formar parte del ingreso de Indyana.</p>
                  </div>
                  <button type="button" onClick={addBookingExternalShare}>Agregar tercero</button>
                </div>

                {bookingForm.externalShares.length === 0 && (
                  <p className="field-help">Sin terceros externos. Para un show normal no hace falta cargar nada aca.</p>
                )}

                {bookingForm.externalShares.length > 0 && (
                  <div className="adjustment-summary">
                    <span>Total externos {localAmount(bookingExternalShareSummary.amount, bookingForm.currency)}</span>
                    <span>% externo {bookingExternalShareSummary.percent.toFixed(2)}%</span>
                    <span>% asignado total {bookingSplitPercentSummary.assignedPercent.toFixed(2)}%</span>
                    <span>Caja manejada por VPO {localAmount(bookingExternalShareSummary.cashHandled, bookingForm.currency)}</span>
                  </div>
                )}
                {bookingSplitPercentSummary.overAssignedPercent > 0.001 && (
                  <p className="field-help danger-text">
                    El split supera 100% por {bookingSplitPercentSummary.overAssignedPercent.toFixed(2)}%. Ajusta % productora o usa el porcentaje restante.
                  </p>
                )}

                {bookingForm.externalShares.map((share, index) => {
                  const percent = parseMoneyInput(share.percent);
                  const manualAmount = parseAmountInput(share.amount, bookingFxRate);
                  const calculatedAmount = manualAmount > 0 ? manualAmount : bookingSuggestion.splitBase * percent / 100;

                  return (
                    <div className="adjustment-card" key={share.uid}>
                      <div className="adjustment-card-title">
                        <strong>Participacion externa {index + 1}</strong>
                        <button type="button" onClick={() => removeBookingExternalShare(share.uid)}>Quitar</button>
                      </div>

                      <div className="row three">
                        <div>
                          <label htmlFor={`external_name_${share.uid}`}>Nombre</label>
                          <input id={`external_name_${share.uid}`} value={share.name} onChange={(event) => updateBookingExternalShareField(share.uid, "name", event.target.value)} placeholder="Fede, manager externo" />
                        </div>
                        <div>
                          <label htmlFor={`external_role_${share.uid}`}>Rol</label>
                          <select id={`external_role_${share.uid}`} value={share.role} onChange={(event) => updateBookingExternalShareField(share.uid, "role", event.target.value as BookingExternalShareForm["role"])}>
                            <option value="manager_externo">Manager externo</option>
                            <option value="socio_externo">Socio externo</option>
                            <option value="tercero">Tercero</option>
                            <option value="otro">Otro</option>
                          </select>
                        </div>
                        <div>
                          <label>Importe calculado</label>
                          <div className="readonly-metric">{localAmount(calculatedAmount, bookingForm.currency)}</div>
                        </div>
                      </div>

                      <div className="row three">
                        <div>
                          <label htmlFor={`external_percent_${share.uid}`}>% sobre base split</label>
                          <input id={`external_percent_${share.uid}`} inputMode="decimal" value={share.percent} onChange={(event) => updateBookingExternalShareField(share.uid, "percent", event.target.value)} placeholder="25" />
                        </div>
                        <div>
                          <label htmlFor={`external_amount_${share.uid}`}>Importe manual</label>
                          <input id={`external_amount_${share.uid}`} inputMode="decimal" value={share.amount} onChange={(event) => updateBookingExternalShareField(share.uid, "amount", event.target.value)} placeholder="opcional" />
                          <p className="field-help">Si cargas importe manual, pisa el calculo por porcentaje.</p>
                        </div>
                        <label className="checkbox-field">
                          <input type="checkbox" checked={share.cashHandledByVpo} onChange={(event) => updateBookingExternalShareField(share.uid, "cashHandledByVpo", event.target.checked)} />
                          Caja manejada por VPO
                        </label>
                      </div>

                      <label htmlFor={`external_notes_${share.uid}`}>Nota</label>
                      <textarea id={`external_notes_${share.uid}`} value={share.notes} onChange={(event) => updateBookingExternalShareField(share.uid, "notes", event.target.value)} placeholder="Ej: Fede cobra 25% de la parte Juanma/Fede. No ingresa a Indyana." />
                    </div>
                  );
                })}
              </div>

              <div className="booking-suggestion">
                <div>
                  <span>Neto despues de gastos</span>
                  <strong>{localAmount(bookingSuggestion.net, bookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Base para split</span>
                  <strong>{localAmount(bookingSuggestion.splitBase, bookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Pago sugerido artista</span>
                  <strong>{localAmount(bookingSuggestion.artistShare, bookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Ingreso sugerido productora</span>
                  <strong>{localAmount(bookingSuggestion.producerShare, bookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Participaciones externas</span>
                  <strong>{localAmount(bookingFinalSuggestion.externalShares, bookingForm.currency)}</strong>
                </div>
                <div>
                  <span>% asignado del split</span>
                  <strong>{bookingSplitPercentSummary.assignedPercent.toFixed(2)}%</strong>
                </div>
                <div>
                  <span>Pago final sugerido artista</span>
                  <strong>{localAmount(bookingFinalSuggestion.artistPayable, bookingForm.currency)}</strong>
                </div>
                <div>
                  <span>Caja sugerida Indyana</span>
                  <strong>{localAmount(bookingFinalSuggestion.producerCash, bookingForm.currency)}</strong>
                </div>
                <p>Primero se descuentan gastos y ajustes antes del split. Despues se calcula el acuerdo y, si hay recuperos posteriores, se aplican sobre el pago final.</p>
              </div>
              <p className="field-help">
                Los sugeridos son la liquidacion correcta segun los datos cargados. Los campos pagado/rendido registran lo que paso en caja; si difieren, el show queda con saldo para control o cuenta corriente.
              </p>
              {bookingForm.cashMovements.length > 0 && (
                <p className="field-help">
                  Como cargaste caja detallada, el sistema usa esos movimientos para completar lo recibido por artista e Indyana. Los campos manuales quedan como referencia visual.
                </p>
              )}

              <div className="booking-payment-box">
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={bookingForm.bookingCommissionExempt}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setBookingForm((current) => ({
                        ...current,
                        bookingCommissionExempt: checked,
                        bookingCommissionNotes: checked ? current.bookingCommissionNotes : "",
                      }));
                    }}
                  />
                  <span>Excluir de comision general de booking</span>
                </label>
                {bookingForm.bookingCommissionExempt && (
                  <>
                    <label htmlFor="booking_commission_notes">Motivo / regla especial</label>
                    <textarea
                      id="booking_commission_notes"
                      value={bookingForm.bookingCommissionNotes}
                      onChange={(event) => updateBookingField("bookingCommissionNotes", event.target.value)}
                      placeholder="Ej: Show Candu + G Sony con booking directo 10%; no comisiona responsable general."
                    />
                    <p className="field-help">El ingreso de Indyana se mantiene, pero no suma a la base comisionable del responsable de booking.</p>
                  </>
                )}
              </div>

              <div className="artist-adjustments">
                <div className="section-heading compact">
                  <div>
                    <h2>Ajustes del artista</h2>
                    <p>Recuperos, inversiones o descuentos vinculados al artista.</p>
                  </div>
                  <button type="button" onClick={addBookingAdjustment}>Agregar ajuste</button>
                </div>

                {bookingForm.artistAdjustments.length > 0 && (
                  <div className="adjustment-summary">
                    <span>Total ajustes {localAmount(bookingAdjustmentSuggestion.amount, bookingForm.currency)}</span>
                    <span>Recupero aplicado {localAmount(bookingAdjustmentSuggestion.appliedAmount, bookingForm.currency)}</span>
                    <span>Artista {localAmount(bookingAdjustmentSuggestion.artistAmount, bookingForm.currency)}</span>
                    <span>Indyana {localAmount(bookingAdjustmentSuggestion.producerAmount, bookingForm.currency)}</span>
                  </div>
                )}

                {bookingForm.artistAdjustments.length === 0 && (
                  <p className="field-help">Sin ajustes cargados para este show.</p>
                )}

                {bookingForm.artistAdjustments.map((adjustment, index) => {
                  const adjustmentAmount = parseAmountInput(adjustment.amount, bookingFxRate);
                  const adjustmentAppliedAmount = parseAmountInput(adjustment.appliedAmount, bookingFxRate);
                  const adjustmentArtistPercent = parseMoneyInput(adjustment.artistPercent);
                  const adjustmentProducerPercent = adjustment.producerPercent
                    ? parseMoneyInput(adjustment.producerPercent)
                    : Math.max(0, 100 - adjustmentArtistPercent);
                  const adjustmentArtistAmount = adjustmentAmount * adjustmentArtistPercent / 100;
                  const adjustmentProducerAmount = adjustmentAmount * adjustmentProducerPercent / 100;

                  return (
                    <div className="adjustment-card" key={adjustment.uid}>
                      <div className="adjustment-card-title">
                        <strong>Ajuste {index + 1}</strong>
                        <button type="button" onClick={() => removeBookingAdjustment(adjustment.uid)}>Quitar</button>
                      </div>

                      <div className="row">
                        <div>
                          <label htmlFor={`adjustment_concept_${adjustment.uid}`}>Concepto</label>
                          <input id={`adjustment_concept_${adjustment.uid}`} value={adjustment.concept} onChange={(event) => updateBookingAdjustmentField(adjustment.uid, "concept", event.target.value)} placeholder="DJ set, adelanto, produccion" />
                        </div>
                        <div>
                          <label htmlFor={`adjustment_amount_${adjustment.uid}`}>Importe</label>
                          <input id={`adjustment_amount_${adjustment.uid}`} inputMode="decimal" value={adjustment.amount} onChange={(event) => updateBookingAdjustmentField(adjustment.uid, "amount", event.target.value)} />
                        </div>
                      </div>

                      <div className="row">
                        <div>
                          <label htmlFor={`adjustment_applied_${adjustment.uid}`}>Recupero aplicado en este show</label>
                          <input id={`adjustment_applied_${adjustment.uid}`} inputMode="decimal" value={adjustment.appliedAmount} onChange={(event) => updateBookingAdjustmentField(adjustment.uid, "appliedAmount", event.target.value)} placeholder="100000" />
                          <p className="field-help">Se descuenta despues del split: baja el pago al artista y sube la caja rendida a Indyana.</p>
                        </div>
                        <div>
                          <label>Saldo recuperable estimado</label>
                          <div className="readonly-metric">{localAmount(Math.max(0, adjustmentArtistAmount - adjustmentAppliedAmount), bookingForm.currency)}</div>
                        </div>
                      </div>

                      <div className="row three">
                        <div>
                          <label htmlFor={`adjustment_type_${adjustment.uid}`}>Tipo</label>
                          <select id={`adjustment_type_${adjustment.uid}`} value={adjustment.adjustmentType} onChange={(event) => updateBookingAdjustmentField(adjustment.uid, "adjustmentType", event.target.value)}>
                            <option value="recupero">Recupero</option>
                            <option value="adelanto">Adelanto</option>
                            <option value="inversion">Inversion</option>
                            <option value="descuento_especial">Descuento especial</option>
                            <option value="otro">Otro</option>
                          </select>
                        </div>
                        <div>
                          <label htmlFor={`adjustment_area_${adjustment.uid}`}>Area</label>
                          <select id={`adjustment_area_${adjustment.uid}`} value={adjustment.area} onChange={(event) => updateBookingAdjustmentField(adjustment.uid, "area", event.target.value)}>
                            <option value="booking">Booking</option>
                            <option value="label">Label</option>
                            <option value="general">General</option>
                          </select>
                        </div>
                        <div>
                          <label htmlFor={`adjustment_impact_${adjustment.uid}`}>Impacta en</label>
                          <select id={`adjustment_impact_${adjustment.uid}`} value={adjustment.impact} onChange={(event) => updateBookingAdjustmentField(adjustment.uid, "impact", event.target.value)}>
                            <option value="pago_artista">Pago artista</option>
                            <option value="ingreso_productora">Ingreso productora</option>
                            <option value="solo_cuenta_corriente">Solo cuenta corriente</option>
                          </select>
                        </div>
                      </div>

                      <div className="row three">
                        <div>
                          <label htmlFor={`adjustment_artist_pct_${adjustment.uid}`}>% artista</label>
                          <input id={`adjustment_artist_pct_${adjustment.uid}`} inputMode="decimal" value={adjustment.artistPercent} onChange={(event) => updateBookingAdjustmentField(adjustment.uid, "artistPercent", event.target.value)} />
                        </div>
                        <div>
                          <label htmlFor={`adjustment_producer_pct_${adjustment.uid}`}>% Indyana</label>
                          <input id={`adjustment_producer_pct_${adjustment.uid}`} inputMode="decimal" value={adjustment.producerPercent} onChange={(event) => updateBookingAdjustmentField(adjustment.uid, "producerPercent", event.target.value)} />
                        </div>
                        <label className="checkbox-field">
                          <input type="checkbox" checked={adjustment.recoverable} onChange={(event) => updateBookingAdjustmentField(adjustment.uid, "recoverable", event.target.checked)} />
                          Recuperable
                        </label>
                      </div>

                      <div className="adjustment-summary">
                        <span>Costo artista {localAmount(adjustmentArtistAmount, bookingForm.currency)}</span>
                        <span>Costo Indyana {localAmount(adjustmentProducerAmount, bookingForm.currency)}</span>
                        <span>Aplicado ahora {localAmount(adjustmentAppliedAmount, bookingForm.currency)}</span>
                      </div>

                      <label htmlFor={`adjustment_notes_${adjustment.uid}`}>Nota del ajuste</label>
                      <textarea id={`adjustment_notes_${adjustment.uid}`} value={adjustment.notes} onChange={(event) => updateBookingAdjustmentField(adjustment.uid, "notes", event.target.value)} />
                    </div>
                  );
                })}
              </div>

              <label htmlFor="booking_receipts">Comprobantes / links / rutas</label>
              <textarea id="booking_receipts" value={bookingForm.receiptRefs} onChange={(event) => updateBookingField("receiptRefs", event.target.value)} placeholder="Uno por linea: C:\\comprobantes\\show.pdf o link de Drive/WhatsApp" />

              <label htmlFor="booking_notes">Notas</label>
              <textarea id="booking_notes" value={bookingForm.notes} onChange={(event) => updateBookingField("notes", event.target.value)} />

              <button type="submit" disabled={bookingLoading || bookingArtists.length === 0}>
                {bookingLoading ? "Guardando..." : bookingEditingId ? "Actualizar show" : "Guardar show"}
              </button>
            </form>

            <section className="panel">
              <div className="section-heading">
                <div>
                  <h2>Tablero de control</h2>
                  <p>Estado de cierre de caja sobre las ultimas cargas disponibles.</p>
                </div>
                <button type="button" onClick={loadBookingShows} disabled={bookingLoading}>Actualizar</button>
              </div>

              <div className="control-dashboard">
                <div>
                  <span>Shows visibles</span>
                  <strong>{bookingControl.totalShows}</strong>
                </div>
                <div>
                  <span>Cerrados</span>
                  <strong>{bookingControl.closedShows}</strong>
                </div>
                <div>
                  <span>Historicos</span>
                  <strong>{bookingControl.historicalShows}</strong>
                </div>
                <div className={bookingControl.pendingShows > 0 ? "warn" : ""}>
                  <span>Pendientes</span>
                  <strong>{bookingControl.pendingShows}</strong>
                </div>
                <div className={bookingControl.pendingAmount > 0 ? "danger" : ""}>
                  <span>Saldo pendiente</span>
                  <strong>{ars(bookingControl.pendingAmount)}</strong>
                </div>
                <div className={bookingControl.venueDebtAmount > 0 ? "danger" : ""}>
                  <span>Deuda boliche</span>
                  <strong>{ars(bookingControl.venueDebtAmount)}</strong>
                </div>
              </div>

              {bookingControl.pending.length > 0 && (
                <div className="control-alerts">
                  <h3>Alertas pendientes</h3>
                  {bookingControl.pending.map((item) => (
                    <div className="control-alert" key={`pending-${item.id}`}>
                      <strong>{item.artist} - {item.venue}</strong>
                      <span>{item.show_date}</span>
                      <span>{item.venue_payment_status !== "cobrado" ? `Boliche ${item.venue_payment_status}` : item.settlement_status || "pendiente"}</span>
                      <span>{ars(Math.max(0, item.balance_producer_amount || 0) + Math.max(0, item.venue_balance_amount || 0))}</span>
                    </div>
                  ))}
                </div>
              )}

              <label htmlFor="booking_search">Buscar show para editar</label>
              <input
                id="booking_search"
                value={bookingSearch}
                onChange={(event) => setBookingSearch(event.target.value)}
                placeholder="Artista, venue, fecha, estado, grupo, nota o ID"
              />
              <p className="field-help">
                Mostrando {Math.min(bookingVisibleCount, filteredBookingItems.length)} de {filteredBookingItems.length} resultado(s), sobre {bookingItems.length} show(s). Toca Editar en el resultado.
              </p>

              <h2 className="list-title">Ultimas cargas</h2>
              <div className="booking-list">
                {bookingItems.length === 0 && <p className="field-help">Todavia no hay shows cargados en esta base local.</p>}
                {bookingItems.length > 0 && filteredBookingItems.length === 0 && (
                  <p className="field-help">No hay shows que coincidan con la busqueda.</p>
                )}
                {visibleBookingItems.map((item) => (
                  <article className="booking-item" key={item.id}>
                    <div>
                      <strong>{item.artist}</strong>
                      <span>{item.show_date} - {item.venue}{item.city ? ` - ${item.city}` : ""}</span>
                    </div>
                    <div className="booking-metrics">
                      <span>Cachet {localAmount(item.cachet_amount, item.currency)}</span>
                      {Math.abs((item.contracted_cachet_amount || item.cachet_amount) - item.cachet_amount) > 0.01 && (
                        <span>Pactado {localAmount(item.contracted_cachet_amount, item.currency)}</span>
                      )}
                      <span>Neto {localAmount(item.net_amount, item.currency)}</span>
                      <span>Base split {localAmount(item.split_base_amount || item.net_amount, item.currency)}</span>
                      <span>Artista {localAmount(item.artist_cash_target_amount || item.artist_share_amount, item.currency)}</span>
                      <span>VPO {localAmount(item.producer_cash_target_amount || item.producer_share_amount, item.currency)}</span>
                    </div>
                    <div className="booking-status">
                      <span>{item.status}</span>
                      <span className={(item.settlement_status || "pendiente") === "cerrado" ? "status-ok" : "status-warn"}>
                        Cierre: {item.settlement_status || "pendiente"}
                      </span>
                      {Math.abs(item.balance_producer_amount || 0) > 0.01 && (
                        <span className="status-danger">Saldo VPO {ars(item.balance_producer_amount)}</span>
                      )}
                      {Math.abs(item.venue_balance_amount || 0) > 0.01 && (
                        <span className="status-danger">Deuda boliche {ars(item.venue_balance_amount)}</span>
                      )}
                      {item.show_expenses.length > 0 && <span>{item.show_expenses.length} gasto(s)</span>}
                      {item.pre_split_adjustments.length > 0 && <span>{item.pre_split_adjustments.length} ajuste(s) pre split</span>}
                      {(item.external_shares || []).length > 0 && <span>{item.external_shares.length} tercero(s)</span>}
                      {item.receipt_refs.length > 0 && <span>{item.receipt_refs.length} comprobante(s)</span>}
                      {item.artist_adjustments.length > 0 && <span>{item.artist_adjustments.length} ajuste(s)</span>}
                    </div>
                    <div className="booking-actions">
                      <button type="button" onClick={() => editBookingShow(item)}>Editar</button>
                    </div>
                  </article>
                ))}
              </div>
              {filteredBookingItems.length > visibleBookingItems.length && (
                <div className="booking-actions load-more-actions">
                  <button type="button" onClick={() => setBookingVisibleCount((current) => current + 5)}>
                    Cargar 5 mas
                  </button>
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
