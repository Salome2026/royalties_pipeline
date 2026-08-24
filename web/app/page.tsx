"use client";

import Image from "next/image";
import { FormEvent, MouseEvent, useEffect, useMemo, useState } from "react";
import { FileSpreadsheet, FileText } from "lucide-react";
import { PeriodControl } from "./components/PeriodControl";
import { BookingDashboard, type BookingAgendaEvent } from "./components/BookingDashboard";
import { VpoHome } from "./components/VpoHome";
import {
  isResolvedPeriodInvalid,
  resolvePeriod,
  selectionFromMonths,
  selectionFromUntil,
  type PeriodProfile,
  type PeriodSelection,
} from "./lib/period";

type Message = {
  type: "ok" | "error";
  text: string;
};

type WebUser = {
  username: string;
  role: "viewer" | "editor" | "admin";
  canEdit: boolean;
  mustChangePassword?: boolean;
};

type View = "menu" | "statement" | "royalties" | "custom-reports" | "participation" | "digital-income" | "royalties-dashboard" | "source-monitor" | "catalog" | "distributor-config" | "booking" | "booking-lab" | "booking-summary" | "commissions" | "booking-artist-summary" | "artist-finance" | "finance-movements" | "artists" | "employees" | "caserio";
type BookingWorkspaceMode = "individual" | "shared";
type BookingSurface = "dashboard" | "settlement";

const VIEW_MODULE_KEYS: Partial<Record<View, string>> = {
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

type ParticipationItem = {
  source: string;
  amount_usd: number;
  percentage: number;
};

type ParticipationAccountItem = {
  source: string;
  account: string;
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
  account_items: ParticipationAccountItem[];
};

const LOS_ANORMALES_DEFAULT_TERMS = [
  "BAILE INOLVIDABLE RKT",
  "LLAMÁNDOME RKT",
  "MOVIMIENTO RKT",
  "REGGAETON RKT",
  "COQUETA",
  "PAPASITO",
  "la fiesta empezó",
  "TU TA DEMASIADO LOCA RKT",
  "PIDE LO QUE TÚ QUIERAS X TIKITIKI RKT",
  "PASO SOLITA X RELACIÓN RKT",
  "LA LLEVO PA EL ESPACIO RKT",
  "INTRO TU JARDÍN CON ENANITOS RKT",
  "INTRO AY VAMOS RKT",
  "BESOS MOJADOS RKT",
  "PIERDO LA CABEZA RKT",
  "NO PARE RKT",
  "MÉTELO SÁCALO RKT",
].join("\n");

const CUSTOM_REPORT_STATE_KEY = "vpo_custom_report_states_v1";

type CustomReportTemplate = {
  key: string;
  title: string;
  terms: string[];
  description?: string;
  enabled?: boolean;
  requires_terms?: boolean;
  supports_sources?: boolean;
  supports_start_month?: boolean;
  default_end_month?: string;
  options?: CustomReportOption[];
};

type CustomReportOption = {
  key: string;
  label: string;
  description?: string;
  default?: boolean;
};

type CustomReportSourceAccount = {
  source: string;
  account: string;
};

type CustomReportOptions = {
  templates: CustomReportTemplate[];
  sources: string[];
  source_accounts: CustomReportSourceAccount[];
};

type RoyaltyReportOutput = "excel" | "executive_pdf";

type RoyaltyReportSourceAccount = {
  source: string;
  account: string;
  display_name: string;
};

type RoyaltyReportOptions = {
  sources: string[];
  source_accounts: RoyaltyReportSourceAccount[];
};

type CustomReportSavedState = {
  title: string;
  startMonth: string;
  endMonth: string;
  terms: string;
  sourceAccounts: string[];
  flags?: Record<string, boolean>;
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
  recovery_auto_apply?: number | boolean;
  notes: string | null;
};

type BookingDirectCommission = {
  id: number;
  show_id: number;
  concept: string;
  recipient: string | null;
  destination: "salida_directa" | "incorpora_base";
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

type BookingAccountTarget = "artist" | "producer" | "venue";

type BookingAccountApplication = {
  id: number;
  show_id: number;
  application_date: string;
  target_balance: BookingAccountTarget;
  application_type: "artist_payment" | "artist_reimbursement" | "producer_reimbursement" | "venue_payment" | "compensation" | "adjustment";
  amount: number;
  effect_amount: number;
  payment_method: "transferencia" | "efectivo" | "compensacion" | "ajuste" | "otro";
  counterparty: string | null;
  linked_show_id: number | null;
  proof_refs: string[];
  notes: string | null;
};

type BookingParentMovementType =
  | "cobro_deuda_booking"
  | "pago_saldo_artista"
  | "compensacion_booking"
  | "pago_deuda_boliche"
  | "ajuste_booking";

type BookingParentMovementDraft = {
  movementDate: string;
  movementType: BookingParentMovementType;
  amount: string;
  paymentMethod: "transferencia" | "efectivo" | "compensacion" | "ajuste" | "otro";
  counterparty: string;
  proofRefs: string;
  notes: string;
  applications: Record<number, string>;
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
  venue_shortfall_policy: "deuda_boliche" | "ajustar_cachet";
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
  open_balance_artist_amount?: number;
  open_balance_producer_amount?: number;
  open_venue_balance_amount?: number;
  account_open_balance_amount?: number;
  account_status?: string;
  settlement_status: string | null;
  settlement_group: string | null;
  settlement_closed_at: string | null;
  settlement_notes: string | null;
  booking_commission_exempt: number;
  booking_commission_notes: string | null;
  show_expenses: BookingExpense[];
  cash_movements: BookingCashMovement[];
  pre_split_adjustments: BookingPreSplitAdjustment[];
  direct_commissions: BookingDirectCommission[];
  external_shares: BookingExternalShare[];
  artist_adjustments: BookingAdjustment[];
  account_applications?: BookingAccountApplication[];
  receipt_refs: string[];
  notes: string | null;
};

const BOOKING_CLOSED_SETTLEMENT_STATUSES = new Set([
  "cerrado",
  "cerrado_con_pago_posterior",
  "cerrado_compensado",
  "cerrado_con_cuenta_corriente",
  "cerrado_con_cuenta_corriente_saldada",
  "cerrado_cc",
]);

function bookingSettlementIsClosed(status: string | null | undefined) {
  return BOOKING_CLOSED_SETTLEMENT_STATUSES.has(status || "");
}

function bookingOpenTargetBalance(item: BookingShow, target: BookingAccountTarget) {
  if (target === "artist") return item.open_balance_artist_amount ?? item.balance_artist_amount ?? 0;
  if (target === "producer") return item.open_balance_producer_amount ?? item.balance_producer_amount ?? 0;
  return item.open_venue_balance_amount ?? item.venue_balance_amount ?? 0;
}

function bookingCurrentAccountNet(producerBalance: number, artistBalance: number) {
  const producer = producerBalance || 0;
  const artist = artistBalance || 0;
  if (Math.abs(producer) <= 0.01) return Math.abs(artist) <= 0.01 ? 0 : -artist;
  if (Math.abs(artist) <= 0.01) return producer;
  if (producer * artist < 0) return Math.abs(producer) >= Math.abs(artist) ? producer : -artist;
  return producer - artist;
}

function bookingOpenBalanceAmount(item: BookingShow) {
  return Math.abs(
    bookingCurrentAccountNet(
      bookingOpenTargetBalance(item, "producer"),
      bookingOpenTargetBalance(item, "artist"),
    )
  ) + Math.max(0, bookingOpenTargetBalance(item, "venue"));
}

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

type EmployeePermission = {
  module_key: string;
  can_access: boolean;
  can_create: boolean;
  can_view_history: boolean;
  can_edit: boolean;
  can_approve: boolean;
  scope: Array<Record<string, string>>;
  notes: string | null;
};

type EmployeeUser = {
  id: number;
  username: string;
  global_role: "viewer" | "editor" | "admin";
  active: boolean;
  auth_source: string;
  has_password?: boolean;
  must_change_password?: boolean;
  last_login_at?: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

type EmployeeRecord = {
  id: number;
  display_name: string;
  legal_name: string | null;
  cuit: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  compensation_type: EmployeeCompensationType;
  salary_amount: number;
  salary_currency: "ARS" | "USD";
  salary_frequency: "monthly";
  salary_notes: string | null;
  notes: string | null;
  active: boolean;
  functions: string[];
  users: EmployeeUser[];
  permissions: EmployeePermission[];
  created_at: string;
  updated_at: string;
};

type EmployeeCompensationType =
  | "none"
  | "salary"
  | "salary_plus_booking_commission"
  | "booking_commission_only";

const employeeCompensationLabels: Record<EmployeeCompensationType, string> = {
  none: "Sin compensacion fija",
  salary: "Salario mensual",
  salary_plus_booking_commission: "Salario + comision booking",
  booking_commission_only: "Solo comision booking",
};

type CommissionEmployeeRecord = {
  id: number;
  display_name: string;
  active: boolean;
  functions: string[];
  permissions: EmployeePermission[];
  created_at?: string;
  updated_at?: string;
};

type FinanceEmployeeOption = {
  id: number;
  display_name: string;
  compensation_type: EmployeeCompensationType;
  salary_amount: number;
  salary_currency: "ARS" | "USD";
  salary_frequency: "monthly";
  active: boolean;
  functions: string[];
  created_at?: string;
  updated_at?: string;
};

type EmployeeModule = {
  module_key: string;
  label: string;
};

type EmployeeForm = {
  displayName: string;
  legalName: string;
  cuit: string;
  phone: string;
  email: string;
  address: string;
  functions: string[];
  compensationType: EmployeeCompensationType;
  salaryAmount: string;
  salaryCurrency: "ARS" | "USD";
  salaryFrequency: "monthly";
  salaryNotes: string;
  username: string;
  newPassword: string;
  mustChangePassword: boolean;
  userRole: "viewer" | "editor" | "admin";
  userActive: boolean;
  permissions: EmployeePermission[];
  notes: string;
  active: boolean;
};

const ARTIST_SCOPED_MODULES = new Set([
  "booking",
  "booking_detail",
  "booking_summary",
  "booking_commissions",
  "artist_finance",
  "finance_movements",
]);

type BookingSummaryMonth = {
  shows: number;
  indyana_total: number;
  commissionable_total: number;
  non_commissionable_total: number;
  commission_total: number;
  indyana_net_total: number;
  commission_details: BookingSummaryCommissionDetail[];
};

type BookingSummaryItem = {
  artist: string;
  shows: number;
  indyana_total: number;
  commissionable_total: number;
  non_commissionable_total: number;
  commission_total: number;
  indyana_net_total: number;
  commission_details: BookingSummaryCommissionDetail[];
  months: Record<string, BookingSummaryMonth>;
  notes: string[];
};

type BookingSummaryCommissionDetail = {
  employee_id: number;
  employee_name: string;
  artist: string;
  month: string;
  priority_order: number;
  percent: number;
  base_amount: number;
  commission_amount: number;
  show_excludes_general: boolean;
  include_booking_fee_paid_shows: boolean;
};

type BookingSummaryCommissionRule = {
  employee_id: number;
  employee_name: string;
  artist: string;
  percent: number;
  base: "commissionable" | "total";
  include_booking_fee_paid_shows: boolean;
  priority_order?: number | null;
  start_month?: string | null;
  end_month?: string | null;
  active: boolean;
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
    commission_total: number;
    indyana_net_total: number;
  };
  commission_rules: BookingSummaryCommissionRule[];
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

type ArtistFinanceOpenBalance = {
  id: number;
  artist: string;
  show_date: string;
  venue: string;
  indyana_balance: number;
  artist_balance: number;
  venue_balance: number;
  settlement_status: string | null;
  status: string;
  notes: string | null;
};

type ArtistFinanceLegacyMovement = {
  id: number;
  artist: string;
  movement_date: string;
  movement_type: string;
  concept: string;
  category: string;
  project: string | null;
  amount: number;
  recoverable: number;
  artist_percent: number;
  producer_percent: number;
  show_id: number | null;
  notes: string | null;
};

type ArtistFinanceMonthlyBooking = {
  month: string;
  shows: number;
  indyana_target: number;
  indyana_balance: number;
  artist_balance: number;
  venue_balance: number;
};

type ArtistFinanceLedgerEntry = {
  id: string;
  ledger_date: string;
  artist: string;
  business_area: string;
  ledger_type: string;
  project_name: string | null;
  concept: string;
  source_module: string;
  source_table: string;
  source_id: string;
  source_label: string | null;
  amount_ars: number;
  account_delta_ars: number;
  venue_receivable_ars: number;
  investment_ars: number;
  recoverable_origin_ars: number;
  recovered_amount_ars: number;
  recoverable_open_ars: number;
  status: string | null;
  notes: string | null;
};

type ArtistFinanceSummary = {
  generated_at: string;
  selected_artist: string | null;
  artists: string[];
  summary: {
    booking: {
      shows: number;
      cachet_total: number;
      show_expenses: number;
      artist_target: number;
      indyana_target: number;
      artist_paid: number;
      indyana_received: number;
      artist_balance: number;
      indyana_balance: number;
      venue_balance: number;
      commissionable_indyana: number;
      non_commissionable_indyana: number;
      booking_current_balance_indyana: number;
    };
    legacy_ledger: {
      rows: number;
      amount_total: number;
      recoverable_amount_total: number;
      official: boolean;
      note: string;
    };
    recoverables: {
      open_amount: number;
      paid_basis_amount: number;
      recovered_amount: number;
      pending_amount: number;
      official: boolean;
      note: string;
    };
    finance_staging: {
      rows: number;
      amount_ars: number;
      paid_amount_ars: number;
      pending_amount_ars: number;
      recoverable_amount_ars: number;
      recovered_amount_ars: number;
      recoverable_paid_basis_ars: number;
      recoverable_pending_basis_ars: number;
      recoverable_defined_open_ars: number;
      recoverable_pending_criteria_ars: number;
      by_status: { status: string; rows: number; amount_ars: number; paid_amount_ars: number; pending_amount_ars: number }[];
      official: boolean;
      note: string;
    };
  };
  monthly_booking: ArtistFinanceMonthlyBooking[];
  open_booking_balances: ArtistFinanceOpenBalance[];
  finance_ledger: {
    entries: ArtistFinanceLedgerEntry[];
    summary: {
      account_current_net_ars: number;
      artist_owes_indyana_ars: number;
      indyana_owes_artist_ars: number;
      venue_receivable_ars: number;
      investment_ars: number;
      recoverable_origin_ars: number;
      recovered_amount_ars: number;
      recoverable_open_ars: number;
      rows: number;
      official: boolean;
      note: string;
    };
  };
  legacy_movements: ArtistFinanceLegacyMovement[];
  finance_project_summary: {
    project_name: string;
    business_area: string;
    first_date: string | null;
    last_date: string | null;
    rows: number;
    amount_ars: number;
    paid_amount_ars: number;
    pending_amount_ars: number;
    recoverable_amount_ars: number;
    recoverable_paid_ars: number;
    recoverable_pending_criteria_ars: number;
    recoverable_defined_ars: number;
    recovered_amount_ars: number;
    recoverable_open_ars: number;
    recoverable_defined_open_ars: number;
    recoverable_pending_criteria_open_ars: number;
  }[];
  finance_movements: FinanceMovement[];
  recovery_applications: {
    id: number;
    artist: string;
    application_date: string;
    finance_movement_id: number;
    project_name: string | null;
    source_type: string;
    source_id: string | null;
    source_label: string | null;
    amount_ars: number;
    recovery_method: string;
    notes: string | null;
    created_at: string;
  }[];
};

type FinanceProject = {
  id: number;
  name: string;
  artist: string | null;
  business_area: string;
  status: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

type FinanceMovement = {
  id: number;
  movement_date: string;
  artist: string;
  business_area: string;
  movement_type: string;
  category: string;
  project_id: number | null;
  project_name: string | null;
  concept: string;
  counterparty: string | null;
  paid_by: string;
  paid_by_employee_id: number | null;
  paid_by_employee_name: string | null;
  amount: number;
  currency: "ARS" | "USD";
  fx_rate: number | null;
  amount_ars: number;
  paid_amount: number;
  paid_amount_ars: number;
  pending_amount_ars: number;
  payment_status: "pendiente" | "parcial" | "pagado";
  due_date: string | null;
  recoverable: number;
  recoverable_percent: number;
  recovery_method: string;
  artist_percent: number;
  producer_percent: number;
  recovered_amount_ars: number;
  recoverable_open_ars: number;
  account_effect: string;
  status: string;
  source_type: string;
  source_id: string | null;
  created_by: string | null;
  proof_refs: string[];
  allocation_lines: FinanceMovementAllocation[];
  document_detail: FinanceDocumentDetail | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

type FinancePaidBy = "indyana" | "artista" | "manager" | "empleado" | "tercero" | "desconocido";

type FinanceMovementAllocation = {
  id?: number;
  movement_id?: number;
  allocation_type: FinanceAllocationType;
  target_name: string;
  business_area: string | null;
  amount: number;
  currency: "ARS" | "USD";
  fx_rate: number | null;
  amount_ars: number;
  notes: string | null;
};

type FinanceDocumentDetail = {
  id: number;
  movement_id: number;
  document_number: number;
  document_date: string;
  document_type: "show_deposit_receipt" | "payment_order" | "collection_receipt";
  issuer_company: FinanceDocumentIssuerCompany;
  counterparty_name: string;
  amount: number;
  currency: "ARS" | "USD";
  fx_rate: number | null;
  amount_ars: number;
  vat_mode: "no_aplica" | "mas_iva" | "iva_incluido";
  concept: string;
  show_date: string | null;
  venue: string | null;
  artist_names: string[];
  booking_show_id: number | null;
  status: string;
  notes: string | null;
};

type FinanceDocumentIssuerCompany =
  | "VPO Corp"
  | "Indyana Records LLC"
  | "Carolina Vanesa Alvarez"
  | "Mawz SRL"
  | "Mawz Records LLC"
  | "Mawz Records SRL";

const financeDocumentIssuerCompanies: FinanceDocumentIssuerCompany[] = [
  "VPO Corp",
  "Indyana Records LLC",
  "Carolina Vanesa Alvarez",
  "Mawz SRL",
  "Mawz Records LLC",
  "Mawz Records SRL",
];

type FinanceMovementData = {
  generated_at: string;
  selected_artist: string | null;
  selected_project: string | null;
  artists: string[];
  items: FinanceMovement[];
  projects: FinanceProject[];
  project_options: string[];
  employee_reimbursements: {
    summary: {
      employee_name: string;
      rows: number;
      amount_ars: number;
      first_date: string | null;
      last_date: string | null;
    }[];
    items: {
      id: number;
      artist: string;
      employee_name: string;
      entry_date: string;
      movement_id: number;
      concept: string;
      amount_ars: number;
      applied_amount_ars: number;
      balance_ars: number;
      status: string;
      notes: string | null;
    }[];
  };
  summary: {
    rows: number;
    amount_ars: number;
    paid_amount_ars: number;
    pending_amount_ars: number;
    by_status: { status: string; rows: number; amount_ars: number }[];
    official: boolean;
    note: string;
  };
};

type FinanceMovementLineForm = {
  uid: string;
  concept: string;
  counterparty: string;
  paidBy: FinancePaidBy;
  paidByEmployeeId: string;
  amount: string;
  paidAmount: string;
  dueDate: string;
  paymentStatus: "pendiente" | "parcial" | "pagado" | "";
  currency: "ARS" | "USD";
  fxRate: string;
};

type FinanceAllocationType =
  | "indyana_cost"
  | "third_party_receivable"
  | "artist_current_account"
  | "other";

type FinanceBusinessArea = "booking" | "label" | "marketing" | "digitales" | "management" | "administracion" | "estructura" | "general";

type FinanceAllocationForm = {
  uid: string;
  allocationType: FinanceAllocationType;
  targetName: string;
  businessArea: FinanceBusinessArea;
  amount: string;
  currency: "ARS" | "USD";
  fxRate: string;
  notes: string;
};

type FinanceAccountApplicationForm = {
  accountEntryId: number;
  amountArs: string;
};

const financeAllocationTypeLabels: Record<FinanceAllocationType, string> = {
  indyana_cost: "Costo Indyana",
  third_party_receivable: "Cuenta por cobrar a tercero",
  artist_current_account: "Cuenta corriente artista",
  other: "Otra imputacion",
};

type FinanceMovementForm = {
  movementDate: string;
  artist: string;
  businessArea: FinanceBusinessArea | "";
  movementType: "gasto" | "ingreso" | "recupero" | "adelanto" | "prestamo" | "ajuste" | "pago" | "salario";
  category: string;
  projectName: string;
  multipleConcepts: boolean;
  concept: string;
  counterparty: string;
  paidBy: FinancePaidBy;
  paidByEmployeeId: string;
  amount: string;
  paidAmount: string;
  dueDate: string;
  paymentStatus: "pendiente" | "parcial" | "pagado" | "";
  currency: "ARS" | "USD";
  fxRate: string;
  recoverable: boolean;
  recoverablePercent: string;
  recoveryMethod: "none" | "before_split" | "after_split" | "direct_account" | "royalties" | "manual";
  artistPercent: string;
  producerPercent: string;
  accountEffect: "sin_impacto" | "artista_debe_indyana" | "indyana_debe_artista" | "inversion_indyana";
  status: "borrador" | "pendiente_control" | "aprobado" | "aplicado" | "anulado";
  sourceType: "manual" | "legacy" | "booking" | "royalties" | "import";
  sourceId: string;
  proofRefs: string;
  notes: string;
  conceptLines: FinanceMovementLineForm[];
  accountApplications: FinanceAccountApplicationForm[];
  economicDistributionEnabled: boolean;
  allocationLines: FinanceAllocationForm[];
  generateDocumentPdf: boolean;
  documentIssuerCompany: FinanceDocumentIssuerCompany;
  documentCounterparty: string;
  documentShowDate: string;
  documentVenue: string;
  documentPrimaryArtist: string;
  documentArtists: string[];
  documentVatMode: "no_aplica" | "mas_iva" | "iva_incluido";
  documentNotes: string;
};

type SourceMonitorItem = {
  id: string;
  source: string;
  account: string;
  display_name: string;
  input_path: string;
  expected_frequency: string;
  max_age_months: number;
  monitoring_active: boolean;
  alert_silenced: boolean;
  portal_url: string;
  notes: string;
  last_manual_review_at: string | null;
  last_statement_period: string | null;
  statement_age_months: number | null;
  statement_files_in_mart: number;
  rows_in_mart: number;
  files_in_mart: number;
  raw_files: number;
  raw_inventory_summary?: Record<string, number>;
  ignored_raw_count?: number;
  ignored_raw_files?: { file_name: string; status: string; reason: string; rows?: number | null }[];
  latest_raw_file: string | null;
  latest_raw_modified: string | null;
  unprocessed_raw_files: string[];
  unprocessed_raw_count: number;
  status: "ok" | "attention" | "alert" | "inactive";
  alert: boolean;
  reason: string;
};

type SourceMonitorData = {
  generated_at: string;
  items: SourceMonitorItem[];
  summary: {
    total: number;
    alerts: number;
    status_counts: Record<string, number>;
  };
};

type SourceMonitorProcessResult = {
  ok: boolean;
  processed_at: string;
  display_name: string;
  source: string;
  account: string;
  pending_files_before: string[];
  last_statement_before: string | null;
  last_statement_after: string | null;
  pending_files_after: string[];
  summary: { statement_period: string; rows: number; amount_usd: number; files: number }[];
  total_rows: number;
  total_amount_usd: number;
};

type SourceMonitorPublishResult = {
  ok: boolean;
  published_at: string;
  bucket: string;
  prefix: string;
  uploaded: { file_name: string; object_name: string; size_bytes: number; size_mb: number }[];
};

type SourceMonitorPublishJob = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: SourceMonitorPublishResult | null;
  error: unknown;
};

type CatalogItem = {
  catalog_key: string;
  asset_isrc: string | null;
  track_id: string | null;
  track_title: string | null;
  artist_statement: string | null;
  first_transaction_month: string | null;
  last_transaction_month: string | null;
  amount_usd: number;
  units: number;
  sources: string | null;
  accounts: string | null;
  content_types: string | null;
  source_sheets: string | null;
  title_variants: string | null;
  artist_variants: string | null;
  external_release_date: string | null;
  external_match_url: string | null;
  external_label: string | null;
  label_normalized_auto: string | null;
  label_normalized_override: string | null;
  label_normalized: string | null;
  active: boolean;
  include_in_reports: boolean;
  catalog_business_status: string | null;
  status_notes: string | null;
  status_updated_at: string | null;
};

type CatalogData = {
  items: CatalogItem[];
  total: number;
  limit: number;
  offset: number;
  totals: {
    amount_usd: number;
    units: number;
  };
  options: {
    sources: string[];
    accounts: string[];
    artists: string[];
    labels: string[];
    first_month: string | null;
    last_month: string | null;
  };
};

type DigitalIncomeItem = {
  statement_period: string;
  source: string;
  account: string;
  artist: string;
  title: string;
  total_usd: number;
  total_eur: number;
  has_share_in_out: boolean;
  raw_rows: number;
};

type DigitalIncomeMonth = {
  statement_period: string;
  total_usd: number;
  total_eur: number;
  rows: number;
};

type DigitalIncomeSource = {
  source: string;
  account: string;
  total_usd: number;
  total_eur: number;
  rows: number;
  artists: number;
};

type DigitalIncomeMatrixRow = {
  source: string;
  account: string;
  months: Record<string, number>;
  total_usd: number;
  total_eur: number;
  rows: number;
  artists: number;
  has_share_in_out: boolean;
};

type DigitalIncomeData = {
  items: DigitalIncomeItem[];
  monthly: DigitalIncomeMonth[];
  by_source: DigitalIncomeSource[];
  matrix: DigitalIncomeMatrixRow[];
  matrix_months: string[];
  total: number;
  limit: number;
  offset: number;
  keyword: string;
  totals: {
    total_usd: number;
    total_eur: number;
    rows: number;
    months: number;
    sources: number;
    accounts: number;
    first_month: string | null;
    last_month: string | null;
  };
  options: {
    sources: string[];
    accounts: string[];
    source_accounts: { source: string; account: string }[];
    artists: string[];
    first_month: string | null;
    last_month: string | null;
  };
};

type RoyaltiesDashboardRank = {
  name: string;
  amount_usd: number;
  units: number;
  rows: number;
  percentage: number;
};

type RoyaltiesDashboardMatrixRow = {
  source: string;
  account: string;
  months: Record<string, number>;
  amount_usd: number;
  units: number;
  rows: number;
  artists: number;
  titles: number;
};

type RoyaltiesDashboardData = {
  report_personalization: {
    enabled: boolean;
    amount_basis?: string;
    scope?: string;
    policy_version: number;
    updated_at?: string | null;
  };
  period_basis: "statement_period" | "transaction_month";
  period_column: string;
  period_months: string[];
  keyword: string;
  totals: {
    amount_usd: number;
    units: number;
    rows: number;
    months: number;
    sources: number;
    accounts: number;
    titles: number;
    artists: number;
    first_month: string | null;
    last_month: string | null;
  };
  monthly: { month: string; amount_usd: number; units: number; rows: number }[];
  matrix: RoyaltiesDashboardMatrixRow[];
  rankings: {
    sources: RoyaltiesDashboardRank[];
    dsp: RoyaltiesDashboardRank[];
    store: RoyaltiesDashboardRank[];
    monetization: RoyaltiesDashboardRank[];
    content_origin: RoyaltiesDashboardRank[];
    plan: RoyaltiesDashboardRank[];
    territory: RoyaltiesDashboardRank[];
    sale_type: RoyaltiesDashboardRank[];
    artist: RoyaltiesDashboardRank[];
    title: RoyaltiesDashboardRank[];
    label: RoyaltiesDashboardRank[];
  };
  youtube: {
    totals: { amount_usd: number; units: number; rows: number; titles: number; artists: number };
    monetization: RoyaltiesDashboardRank[];
    content_origin: RoyaltiesDashboardRank[];
    plan: RoyaltiesDashboardRank[];
    title: RoyaltiesDashboardRank[];
    territory: RoyaltiesDashboardRank[];
  };
  options: {
    sources: string[];
    accounts: string[];
    source_accounts: { source: string; account: string }[];
    first_month: string | null;
    last_month: string | null;
  };
};

type StatementDictionaryEntry = {
  source: string;
  account: string;
  raw_sheet_or_file_type: string;
  human_name: string;
  human_description: string;
  business_meaning: string;
  amount_column: string | null;
  currency_column: string | null;
  period_column: string | null;
  artist_column: string | null;
  title_column: string | null;
  identifier_columns: string[];
  default_catalog_view: boolean | string;
  default_statement_view: boolean | string;
  default_cash_view: boolean | string;
  decision_reason: string;
  known_risks: string;
  last_reviewed_at: string;
  reviewed_by: string;
};

type ContractCutoff = {
  cutoff_id: string;
  source: string;
  account: string;
  business_entity: string;
  contract_start_date: string | null;
  contract_start_month: string | null;
  date_status: string;
  cutoff_basis: string;
  evidence_type: string;
  evidence_terms: string[];
  evidence_first_transaction_month?: string | null;
  evidence_first_statement_period?: string | null;
  old_content_policy: string;
  new_content_policy: string;
  unknown_content_policy: string;
  confidence: string;
  notes: string;
};

type DistributorAccountPolicy = {
  policy_id: string;
  source: string;
  account: string;
  display_name: string;
  account_type: string;
  ownership_default: string;
  monitoring_active: boolean;
  catalog_view_enabled: boolean;
  statement_view_enabled: boolean;
  cash_view_enabled: boolean | string;
  cash_view_mode?: string;
  cash_view_label?: string;
  cash_view_description?: string;
  default_time_basis: string;
  contract_cutoff_id: string | null;
  shares_policy: string;
  report_net_adjustment_pct?: number;
  sheet_rules: Record<string, Record<string, boolean | string>>;
  notes: string;
  statement_dictionary: StatementDictionaryEntry[];
  contract_cutoff: ContractCutoff | null;
  rule_preview?: {
    enabled: boolean;
    cutoff_id?: string | null;
    cutoff_basis?: string;
    contract_start_date?: string | null;
    contract_start_month?: string | null;
    summary: {
      status: string;
      works: number;
      amount_usd: number;
      rows: number;
    }[];
    final_summary?: {
      status: string;
      works: number;
      amount_usd: number;
      rows: number;
    }[];
    alerts?: {
      status: string;
      rule_status?: string;
      final_status?: string;
      decision_basis: string | null;
      reason: string;
      final_reason?: string;
      attention_level?: string;
      catalog_key?: string | null;
      catalog_active?: boolean | null;
      catalog_include_in_reports?: boolean | null;
      catalog_business_status?: string | null;
      catalog_status_notes?: string | null;
      source_sheet: string;
      asset_isrc: string | null;
      track_title: string | null;
      artist: string | null;
      amount_usd: number;
      rows: number;
      first_transaction_month: string | null;
      last_transaction_month: string | null;
      external_release_date: string | null;
      external_label: string | null;
    }[];
    items: {
      status: string;
      rule_status?: string;
      final_status?: string;
      decision_basis: string | null;
      reason: string;
      final_reason?: string;
      attention_level?: string;
      catalog_key?: string | null;
      catalog_active?: boolean | null;
      catalog_include_in_reports?: boolean | null;
      catalog_business_status?: string | null;
      catalog_status_notes?: string | null;
      source_sheet: string;
      asset_isrc: string | null;
      track_title: string | null;
      artist: string | null;
      amount_usd: number;
      rows: number;
      first_transaction_month: string | null;
      last_transaction_month: string | null;
      external_release_date: string | null;
      external_label: string | null;
    }[];
  };
  account_impact_stats?: {
    rows: number;
    works: number;
    amount_usd: number;
    units: number;
    first_transaction_month: string | null;
    last_transaction_month: string | null;
    sheet_breakdown: {
      source_sheet: string;
      rows: number;
      works: number;
      amount_usd: number;
      units: number;
      first_transaction_month: string | null;
      last_transaction_month: string | null;
    }[];
  };
  catalog_stats?: {
    works: number;
    active: number;
    inactive: number;
    excluded_from_reports: number;
    release_dates: number;
    missing_release_dates: number;
    labels: number;
    missing_labels: number;
    amount_usd: number;
    first_transaction_month: string | null;
    last_transaction_month: string | null;
  };
};

type ReportTemplateConfig = {
  template_key: string;
  title: string;
  report_family: string;
  time_basis: string;
  uses_catalog_status: boolean;
  uses_account_policy: boolean | string;
  output_profile: string;
  default_filters: Record<string, string | number | boolean | null>;
  rule_version: string;
  enabled: boolean;
  notes: string;
};

type DistributorConfigData = {
  generated_at: string;
  mode: string;
  policy_version?: number;
  report_personalization?: {
    enabled: boolean;
    amount_basis?: string;
    scope?: string;
  };
  accounts: DistributorAccountPolicy[];
  statement_dictionary: StatementDictionaryEntry[];
  contract_cutoffs: ContractCutoff[];
  report_templates: ReportTemplateConfig[];
  summary: {
    accounts: number;
    dictionary_entries: number;
    contract_cutoffs: number;
    report_templates: number;
    sources: Record<string, number>;
    account_types: Record<string, number>;
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
  venueShortfallPolicy: "deuda_boliche" | "ajustar_cachet";
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
  recoveryAutoApply: boolean;
  notes: string;
};

type BookingDirectCommissionForm = {
  uid: string;
  concept: string;
  recipient: string;
  destination: "salida_directa" | "incorpora_base";
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

type BookingAccountApplicationForm = {
  targetBalance: BookingAccountTarget;
  applicationType: "artist_payment" | "artist_reimbursement" | "producer_reimbursement" | "venue_payment" | "compensation" | "adjustment";
  applicationDate: string;
  amount: string;
  paymentMethod: "transferencia" | "efectivo" | "compensacion" | "ajuste" | "otro";
  counterparty: string;
  linkedShowId: string;
  proofRefs: string;
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
  venueShortfallPolicy: "deuda_boliche" | "ajustar_cachet";
  venuePaymentNotes: string;
  showExpenses: BookingExpenseForm[];
  cashMovements: BookingCashMovementForm[];
  preSplitAdjustments: BookingPreSplitAdjustmentForm[];
  directCommissions: BookingDirectCommissionForm[];
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

function moneyCents(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function eurCents(value: number) {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function pct(value: number) {
  return `${value.toFixed(1)}%`;
}

function ars(value: number) {
  return new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 0 }).format(value);
}

function employeeSalaryAmount(currency: "ARS" | "USD", value: number) {
  return currency === "USD" ? money(value) : ars(value);
}

type CommissionRuleDraft = {
  employee: string;
  artist: string;
  percent: number;
  base: "commissionable" | "total";
  includeBookingFeePaidShows: boolean;
  priorityOrder: number | null;
  startMonth: string;
  endMonth: string;
  active: boolean;
  notes: string;
};

type CommissionRuleDraftState = Omit<CommissionRuleDraft, "employee" | "artist">;

type StoredCommissionRule = {
  artist: string;
  percent: number;
  base: "commissionable" | "total";
  include_booking_fee_paid_shows?: boolean;
  priority_order?: number | null;
  start_month?: string | null;
  end_month?: string | null;
  active: boolean;
  notes?: string | null;
};

const SOURCE_MONITOR_STATUS_LABELS: Record<string, string> = {
  loaded_to_mart: "Cargados",
  pending_real: "Pendientes",
  ignored_empty: "Vacíos",
  ignored_summary: "Summaries omitidos",
  legacy_manual: "Legacy",
};

function sourceMonitorInventoryLabel(summary?: Record<string, number>) {
  if (!summary) return "";
  return Object.entries(summary)
    .filter(([, count]) => count > 0)
    .map(([status, count]) => `${SOURCE_MONITOR_STATUS_LABELS[status] || status}: ${count}`)
    .join(" · ");
}

function flagLabel(value: boolean | string | null | undefined) {
  if (value === true) return "Si";
  if (value === false) return "No";
  if (value === null || value === undefined || value === "") return "-";
  if (value === "partial_by_contract_cutoff") return "Parcial por fecha contractual";
  if (value === "only_content_after_contract_start") return "Desde contrato";
  if (value === "depends_on_account_policy") return "Segun cuenta";
  if (value === "cash_or_audit_not_generation") return "Caja/auditoria";
  if (value === "audit_only") return "Solo auditoria";
  if (value === "not_applicable") return "No aplica";
  if (value === "not_relevant_currently") return "No relevante";
  if (value === "transaction_month") return "Transaction month";
  if (value === "statement_period") return "Statement period";
  if (value === "release_date_preferred_transaction_month_fallback") return "Release date, fallback transaction";
  if (value === "estimated") return "Estimada";
  if (value === "confirmed") return "Confirmada";
  if (value === "medium") return "Media";
  if (value === "high") return "Alta";
  if (value === "low") return "Baja";
  if (value === "exclude_even_if_generates_later") return "Excluir aunque genere despues";
  if (value === "include_if_content_first_seen_on_or_after_contract_start") return "Incluir si nace desde el contrato";
  if (value === "include_if_release_date_or_content_first_seen_on_or_after_contract_start") return "Incluir si release/primer visto es desde contrato";
  if (value === "manual_review") return "Revision manual";
  return String(value);
}

function cashModeClass(value: boolean | string | null | undefined) {
  if (value === true || value === "complete") return "ok";
  if (value === "partial_by_contract_cutoff" || value === "partial_by_rule") return "warning";
  return "inactive";
}

function accountCashLabel(account: DistributorAccountPolicy) {
  if (account.cash_view_label) return account.cash_view_label;
  if (account.cash_view_enabled === true) return "Caja completa";
  if (account.cash_view_enabled === "partial_by_contract_cutoff") return "Caja parcial por regla";
  return "No caja";
}

function ruleStatusLabel(status: string) {
  if (status === "included") return "Incluido";
  if (status === "excluded") return "Excluido";
  if (status === "manual_review") return "Revision manual";
  return status;
}

function ruleStatusClass(status: string) {
  if (status === "included") return "ok";
  if (status === "excluded") return "inactive";
  if (status === "manual_review") return "warning";
  return "inactive";
}

function finalDecisionLabel(status: string) {
  if (status === "reportable") return "Reportable final";
  if (status === "excluded_by_rule") return "Excluido por contrato";
  if (status === "excluded_by_catalog") return "Excluido por catalogo";
  if (status === "manual_review") return "Revision manual";
  return status;
}

function finalDecisionClass(status: string) {
  if (status === "reportable") return "ok";
  if (status === "excluded_by_rule") return "inactive";
  if (status === "excluded_by_catalog") return "warning";
  if (status === "manual_review") return "warning";
  return "inactive";
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

function amountToInput(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") return "";
  const parsed = typeof value === "number"
    ? value
    : Number(String(value).trim().replace(",", "."));
  if (!Number.isFinite(parsed) || parsed === 0) return "";
  const normalized = Number.isInteger(parsed)
    ? String(parsed)
    : parsed.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
  return normalized;
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
    recoveryAutoApply: destination === "producer",
    notes: "",
  };
}

function newBookingDirectCommission(destination: "salida_directa" | "incorpora_base" = "salida_directa"): BookingDirectCommissionForm {
  return {
    uid: `${Date.now()}-${Math.random()}`,
    concept: "",
    recipient: "",
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

function initialBookingAccountApplicationForm(): BookingAccountApplicationForm {
  return {
    targetBalance: "artist",
    applicationType: "compensation",
    applicationDate: new Date().toISOString().slice(0, 10),
    amount: "",
    paymentMethod: "transferencia",
    counterparty: "",
    linkedShowId: "",
    proofRefs: "",
    notes: "",
  };
}

function initialBookingParentMovementDraft(): BookingParentMovementDraft {
  return {
    movementDate: new Date().toISOString().slice(0, 10),
    movementType: "cobro_deuda_booking",
    amount: "",
    paymentMethod: "transferencia",
    counterparty: "",
    proofRefs: "",
    notes: "",
    applications: {},
  };
}

function bookingDefaultAccountTarget(item: BookingShow): BookingAccountTarget {
  if (Math.abs(bookingOpenTargetBalance(item, "artist")) > 0.01) return "artist";
  if (Math.abs(bookingOpenTargetBalance(item, "producer")) > 0.01) return "producer";
  return "venue";
}

function bookingAccountTargetLabel(item: BookingShow, target: BookingAccountTarget) {
  const balance = bookingOpenTargetBalance(item, target);
  if (target === "artist") {
    return balance >= 0 ? "Indyana debe artista" : "Artista debe Indyana";
  }
  if (target === "producer") {
    return balance >= 0 ? "Falta rendir a Indyana" : "Indyana cobro de mas";
  }
  return "Boliche debe Indyana";
}

function bookingSuggestedApplicationType(item: BookingShow, target: BookingAccountTarget): BookingAccountApplicationForm["applicationType"] {
  const balance = bookingOpenTargetBalance(item, target);
  if (target === "venue") return "venue_payment";
  if (target === "artist") return balance >= 0 ? "artist_payment" : "artist_reimbursement";
  return balance >= 0 ? "producer_reimbursement" : "adjustment";
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
    venueShortfallPolicy: "deuda_boliche",
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

function newFinanceMovementLine(): FinanceMovementLineForm {
  return {
    uid: `${Date.now()}-${Math.random()}`,
    concept: "",
    counterparty: "",
    paidBy: "indyana",
    paidByEmployeeId: "",
    amount: "",
    paidAmount: "",
    dueDate: "",
    paymentStatus: "",
    currency: "ARS",
    fxRate: "",
  };
}

function newFinanceAllocationLine(values: Partial<FinanceAllocationForm> = {}): FinanceAllocationForm {
  return {
    uid: `${Date.now()}-${Math.random()}`,
    allocationType: values.allocationType || "indyana_cost",
    targetName: values.targetName || "Indyana",
    businessArea: values.businessArea || "estructura",
    amount: values.amount || "",
    currency: values.currency || "ARS",
    fxRate: values.fxRate || "",
    notes: values.notes || "",
  };
}

function initialFinanceMovementForm(): FinanceMovementForm {
  return {
    movementDate: new Date().toISOString().slice(0, 10),
    artist: "",
    businessArea: "",
    movementType: "gasto",
    category: "",
    projectName: "",
    multipleConcepts: false,
    concept: "",
    counterparty: "",
    paidBy: "indyana",
    paidByEmployeeId: "",
    amount: "",
    paidAmount: "",
    dueDate: "",
    paymentStatus: "",
    currency: "ARS",
    fxRate: "",
    recoverable: false,
    recoverablePercent: "0",
    recoveryMethod: "none",
    artistPercent: "0",
    producerPercent: "100",
    accountEffect: "inversion_indyana",
    status: "pendiente_control",
    sourceType: "manual",
    sourceId: "",
    proofRefs: "",
    notes: "",
    conceptLines: [newFinanceMovementLine()],
    accountApplications: [],
    economicDistributionEnabled: false,
    allocationLines: [newFinanceAllocationLine()],
    generateDocumentPdf: false,
    documentIssuerCompany: "VPO Corp",
    documentCounterparty: "",
    documentShowDate: "",
    documentVenue: "",
    documentPrimaryArtist: "",
    documentArtists: [],
    documentVatMode: "no_aplica",
    documentNotes: "",
  };
}

function applyResolvedPeriod(
  selection: PeriodSelection,
  profile: PeriodProfile,
  setStartMonth: (value: string) => void,
  setEndMonth: (value: string) => void,
) {
  const resolved = resolvePeriod(selection, profile);
  setStartMonth(resolved.startMonth || "");
  setEndMonth(resolved.endMonth || "");
}

export default function Home() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [view, setView] = useState<View>("menu");
  const [bookingWorkspaceMode, setBookingWorkspaceMode] = useState<BookingWorkspaceMode>("individual");
  const [currentUser, setCurrentUser] = useState<WebUser | null>(null);
  const [currentUserModuleAccess, setCurrentUserModuleAccess] = useState<string[] | null>(null);
  const [currentUserPermissions, setCurrentUserPermissions] = useState<EmployeePermission[] | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [keywords, setKeywords] = useState("");
  const [startMonth, setStartMonth] = useState("");
  const [endMonth, setEndMonth] = useState("");
  const [periodBasis, setPeriodBasis] = useState("transaction_month");
  const [mode, setMode] = useState("any");
  const [rawLimit, setRawLimit] = useState("5000");
  const [royaltyReportOutput, setRoyaltyReportOutput] = useState<RoyaltyReportOutput>("excel");
  const [royaltyReportOptions, setRoyaltyReportOptions] = useState<RoyaltyReportOptions | null>(null);
  const [royaltyReportSource, setRoyaltyReportSource] = useState("");
  const [royaltyReportAccount, setRoyaltyReportAccount] = useState("");
  const [statementMinTotal, setStatementMinTotal] = useState("0");
  const [statementIncludeZeros, setStatementIncludeZeros] = useState(false);
  const [statementReportVersion, setStatementReportVersion] = useState("legacy");
  const [customReportOptions, setCustomReportOptions] = useState<CustomReportOptions | null>(null);
  const [customReportTemplateKey, setCustomReportTemplateKey] = useState("los_anormales");
  const [customReportTitle, setCustomReportTitle] = useState("Regalias Los Anormales");
  const [customReportStartMonth, setCustomReportStartMonth] = useState("");
  const [customReportEndMonth, setCustomReportEndMonth] = useState("2026-03");
  const [customReportTerms, setCustomReportTerms] = useState(LOS_ANORMALES_DEFAULT_TERMS);
  const [customReportSources, setCustomReportSources] = useState<string[]>([]);
  const [customReportSourceAccounts, setCustomReportSourceAccounts] = useState<string[]>([]);
  const [customReportFlags, setCustomReportFlags] = useState<Record<string, boolean>>({});
  const [customReportLoading, setCustomReportLoading] = useState(false);
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
  const [sourceMonitor, setSourceMonitor] = useState<SourceMonitorData | null>(null);
  const [sourceMonitorLoading, setSourceMonitorLoading] = useState(false);
  const [sourceMonitorProcessingId, setSourceMonitorProcessingId] = useState("");
  const [sourceMonitorLastProcess, setSourceMonitorLastProcess] = useState<SourceMonitorProcessResult | null>(null);
  const [sourceMonitorPublishing, setSourceMonitorPublishing] = useState(false);
  const [sourceMonitorLastPublish, setSourceMonitorLastPublish] = useState<SourceMonitorPublishResult | null>(null);
  const [sourceMonitorPublishJob, setSourceMonitorPublishJob] = useState<SourceMonitorPublishJob | null>(null);
  const [catalogData, setCatalogData] = useState<CatalogData | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogSource, setCatalogSource] = useState("");
  const [catalogAccount, setCatalogAccount] = useState("");
  const [catalogArtist, setCatalogArtist] = useState("");
  const [catalogKeyword, setCatalogKeyword] = useState("");
  const [catalogLabel, setCatalogLabel] = useState("");
  const [catalogPeriod, setCatalogPeriod] = useState<PeriodSelection>({ mode: "all" });
  const [catalogStatus, setCatalogStatus] = useState<"active" | "inactive" | "all">("active");
  const [catalogOffset, setCatalogOffset] = useState(0);
  const [catalogLabelEditKey, setCatalogLabelEditKey] = useState("");
  const [catalogLabelDraft, setCatalogLabelDraft] = useState("");
  const [catalogLabelSaving, setCatalogLabelSaving] = useState("");
  const catalogLimit = 50;
  const [digitalIncome, setDigitalIncome] = useState<DigitalIncomeData | null>(null);
  const [digitalIncomeLoading, setDigitalIncomeLoading] = useState(false);
  const [digitalIncomeArtistKeyword, setDigitalIncomeArtistKeyword] = useState("");
  const [digitalIncomeSource, setDigitalIncomeSource] = useState("");
  const [digitalIncomeAccount, setDigitalIncomeAccount] = useState("");
  const [digitalIncomePeriod, setDigitalIncomePeriod] = useState<PeriodSelection>({ mode: "last_6_months" });
  const digitalIncomeLimit = 500;
  const [royaltiesDashboard, setRoyaltiesDashboard] = useState<RoyaltiesDashboardData | null>(null);
  const [royaltiesDashboardLoading, setRoyaltiesDashboardLoading] = useState(false);
  const [royaltiesDashboardKeyword, setRoyaltiesDashboardKeyword] = useState("");
  const [royaltiesDashboardSource, setRoyaltiesDashboardSource] = useState("");
  const [royaltiesDashboardAccount, setRoyaltiesDashboardAccount] = useState("");
  const [royaltiesDashboardPeriod, setRoyaltiesDashboardPeriod] = useState<PeriodSelection>({ mode: "last_6_months" });
  const [royaltiesDashboardPeriodBasis, setRoyaltiesDashboardPeriodBasis] = useState<"statement_period" | "transaction_month">("statement_period");
  const [royaltiesDashboardTab, setRoyaltiesDashboardTab] = useState<"overview" | "youtube">("overview");
  const [distributorConfig, setDistributorConfig] = useState<DistributorConfigData | null>(null);
  const [distributorConfigLoading, setDistributorConfigLoading] = useState(false);
  const [distributorConfigSource, setDistributorConfigSource] = useState("");
  const [distributorConfigAccountId, setDistributorConfigAccountId] = useState("");
  const [distributorPersonalizationEnabled, setDistributorPersonalizationEnabled] = useState(false);
  const [distributorAdjustmentDrafts, setDistributorAdjustmentDrafts] = useState<Record<string, string>>({});
  const [distributorPersonalizationSaving, setDistributorPersonalizationSaving] = useState(false);
  const [bookingLoading, setBookingLoading] = useState(false);
  const [bookingItems, setBookingItems] = useState<BookingShow[]>([]);
  const [bookingSearch, setBookingSearch] = useState("");
  const [bookingVisibleCount, setBookingVisibleCount] = useState(5);
  const [bookingArtists, setBookingArtists] = useState<string[]>([]);
  const [bookingAccountShowId, setBookingAccountShowId] = useState<number | null>(null);
  const [bookingAccountForm, setBookingAccountForm] = useState<BookingAccountApplicationForm>(() => initialBookingAccountApplicationForm());
  const [bookingSummary, setBookingSummary] = useState<BookingSummary | null>(null);
  const [bookingSummaryLoading, setBookingSummaryLoading] = useState(false);
  const [commissionSummary, setCommissionSummary] = useState<BookingSummary | null>(null);
  const [commissionSummaryLoading, setCommissionSummaryLoading] = useState(false);
  const [commissionsEmployee, setCommissionsEmployee] = useState("");
  const [commissionsTab, setCommissionsTab] = useState<"settlement" | "config">("settlement");
  const [commissionEmployeeRecords, setCommissionEmployeeRecords] = useState<CommissionEmployeeRecord[]>([]);
  const [commissionEmployeesLoading, setCommissionEmployeesLoading] = useState(false);
  const [commissionRuleDrafts, setCommissionRuleDrafts] = useState<Record<string, CommissionRuleDraftState>>({});
  const [commissionRulesLoading, setCommissionRulesLoading] = useState(false);
  const [commissionRulesSaving, setCommissionRulesSaving] = useState(false);
  const [commissionDirtyEmployees, setCommissionDirtyEmployees] = useState<Record<string, boolean>>({});
  const [commissionStartMonth, setCommissionStartMonth] = useState("");
  const [commissionEndMonth, setCommissionEndMonth] = useState("");
  const [commissionSettlementSearch, setCommissionSettlementSearch] = useState("");
  const [bookingArtistSummary, setBookingArtistSummary] = useState<BookingArtistSummary | null>(null);
  const [bookingArtistSummaryArtist, setBookingArtistSummaryArtist] = useState("");
  const [bookingArtistSummaryLoading, setBookingArtistSummaryLoading] = useState(false);
  const [bookingArtistSummaryLatestOnly, setBookingArtistSummaryLatestOnly] = useState(true);
  const [artistFinance, setArtistFinance] = useState<ArtistFinanceSummary | null>(null);
  const [artistFinanceArtist, setArtistFinanceArtist] = useState("");
  const [artistFinanceView, setArtistFinanceView] = useState<"summary" | "booking" | "projects" | "account" | "technical">("summary");
  const [artistFinanceProjectFilter, setArtistFinanceProjectFilter] = useState("");
  const [artistFinanceLoading, setArtistFinanceLoading] = useState(false);
  const [artistFinanceBookingMovementOpen, setArtistFinanceBookingMovementOpen] = useState(false);
  const [artistFinanceBookingMovementDraft, setArtistFinanceBookingMovementDraft] = useState<BookingParentMovementDraft>(() => initialBookingParentMovementDraft());
  const [financeMovements, setFinanceMovements] = useState<FinanceMovementData | null>(null);
  const [financeMovementLoading, setFinanceMovementLoading] = useState(false);
  const [financeMovementEditingId, setFinanceMovementEditingId] = useState<number | null>(null);
  const [financeMovementArtistFilter, setFinanceMovementArtistFilter] = useState("");
  const [financeMovementProjectFilter, setFinanceMovementProjectFilter] = useState("");
  const [financeMovementStatusFilter, setFinanceMovementStatusFilter] = useState("");
  const [financeMovementForm, setFinanceMovementForm] = useState<FinanceMovementForm>(() => initialFinanceMovementForm());
  const [financeMovementProjectMode, setFinanceMovementProjectMode] = useState<"existing" | "new">("existing");
  const [financeMovementLastReceiptPdf, setFinanceMovementLastReceiptPdf] = useState<{ href: string; label: string } | null>(null);
  const [financeEmployeeOptions, setFinanceEmployeeOptions] = useState<FinanceEmployeeOption[]>([]);
  const [financeEmployeeOptionsLoading, setFinanceEmployeeOptionsLoading] = useState(false);
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
  const [employeeRecords, setEmployeeRecords] = useState<EmployeeRecord[]>([]);
  const [employeeFunctionOptions, setEmployeeFunctionOptions] = useState<string[]>([]);
  const [employeeModules, setEmployeeModules] = useState<EmployeeModule[]>([]);
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [employeeLoading, setEmployeeLoading] = useState(false);
  const [employeeEditingId, setEmployeeEditingId] = useState<number | null>(null);
  const [employeeForm, setEmployeeForm] = useState<EmployeeForm>({
    displayName: "",
    legalName: "",
    cuit: "",
    phone: "",
    email: "",
    address: "",
    functions: [],
    compensationType: "none",
    salaryAmount: "",
    salaryCurrency: "ARS",
    salaryFrequency: "monthly",
    salaryNotes: "",
    username: "",
    newPassword: "",
    mustChangePassword: true,
    userRole: "viewer",
    userActive: true,
    permissions: [],
    notes: "",
    active: true,
  });
  const [caserioLoading, setCaserioLoading] = useState(false);
  const [caserioEvents, setCaserioEvents] = useState<CaserioEvent[]>([]);
  const [compositeBookingEvents, setCompositeBookingEvents] = useState<BookingCompositeEvent[]>([]);
  const [bookingSurface, setBookingSurface] = useState<BookingSurface>("dashboard");
  const [bookingAgendaEventId, setBookingAgendaEventId] = useState<number | null>(null);
  const [compositeBookingAgendaEventId, setCompositeBookingAgendaEventId] = useState<number | null>(null);
  const [bookingAgendaCandidates, setBookingAgendaCandidates] = useState<BookingAgendaEvent[]>([]);
  const [bookingAgendaCandidateId, setBookingAgendaCandidateId] = useState("");
  const [bookingAgendaCandidatesLoading, setBookingAgendaCandidatesLoading] = useState(false);
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
    venueShortfallPolicy: "deuda_boliche",
    venuePaymentNotes: "",
    showExpenses: [],
    cashMovements: [],
    preSplitAdjustments: [],
    directCommissions: [],
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
    if (authenticated && currentUser) {
      loadCurrentUserPermissions();
    } else {
      setCurrentUserModuleAccess(null);
    }
  }, [authenticated, currentUser?.username, currentUser?.role]);

  useEffect(() => {
    if (!authenticated || view !== "booking" || currentUserModuleAccess === null) return;
    if (bookingSurface === "dashboard" && canAccessModule("booking_agenda")) return;
    if (canAccessBookingMode(bookingWorkspaceMode)) return;
    if (canAccessBookingMode("individual")) {
      setBookingWorkspaceMode("individual");
    } else if (canAccessBookingMode("shared")) {
      setBookingWorkspaceMode("shared");
    } else {
      setView("menu");
    }
  }, [authenticated, view, bookingSurface, bookingWorkspaceMode, currentUserModuleAccess, currentUser?.role]);

  useEffect(() => {
    if (authenticated && view === "participation" && !participation) {
      loadParticipation(false);
    }
  }, [authenticated, view, participation]);

  useEffect(() => {
    if (authenticated && view === "booking" && bookingSurface === "settlement") {
      loadBookingArtists();
      loadBookingAgendaCandidates();
      if (bookingWorkspaceMode === "individual") {
        loadBookingShows();
      } else {
        loadCompositeBookingEvents();
      }
    }
  }, [authenticated, view, bookingWorkspaceMode, bookingSurface]);

  useEffect(() => {
    if (authenticated && view === "source-monitor") {
      loadSourceMonitor();
    }
  }, [authenticated, view]);

  useEffect(() => {
    if (authenticated && view === "royalties" && !royaltyReportOptions) {
      loadRoyaltyReportOptions();
    }
  }, [authenticated, view, royaltyReportOptions]);

  useEffect(() => {
    if (authenticated && view === "catalog") {
      loadCatalog();
    }
  }, [authenticated, view, catalogSource, catalogAccount, catalogArtist, catalogStatus, catalogPeriod, catalogOffset]);

  useEffect(() => {
    if (authenticated && view === "digital-income") {
      loadDigitalIncome();
    }
  }, [authenticated, view]);

  useEffect(() => {
    if (authenticated && view === "royalties-dashboard") {
      loadRoyaltiesDashboard();
    }
  }, [authenticated, view]);

  useEffect(() => {
    if (authenticated && view === "distributor-config" && !distributorConfig) {
      loadDistributorConfig();
    }
  }, [authenticated, view, distributorConfig]);

  useEffect(() => {
    setCatalogOffset(0);
  }, [catalogSource, catalogAccount, catalogArtist, catalogKeyword, catalogLabel, catalogStatus, catalogPeriod]);

  useEffect(() => {
    if (authenticated && view === "custom-reports" && !customReportOptions) {
      loadCustomReportOptions();
    }
  }, [authenticated, view, customReportOptions]);

  useEffect(() => {
    if (authenticated && view === "custom-reports" && customReportOptions) {
      saveCustomReportState();
    }
  }, [
    authenticated,
    view,
    customReportOptions,
    customReportTemplateKey,
    customReportTitle,
    customReportStartMonth,
    customReportEndMonth,
    customReportTerms,
    customReportSourceAccounts,
    customReportFlags,
  ]);

  useEffect(() => {
    setBookingVisibleCount(5);
  }, [bookingSearch]);

  useEffect(() => {
    if (authenticated && view === "artists") {
      loadArtistRecords();
    }
  }, [authenticated, view]);

  useEffect(() => {
    if (authenticated && view === "employees") {
      loadBookingArtists();
      loadEmployeeRecords();
    }
  }, [authenticated, view]);

  useEffect(() => {
    if (authenticated && view === "caserio") {
      loadBookingArtists();
      loadCaserioEvents();
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
    if (authenticated && view === "commissions") {
      loadCommissionEmployeeRecords();
      loadBookingArtists();
      loadCommissionsSummary();
    }
  }, [authenticated, view]);

  useEffect(() => {
    if (authenticated && view === "commissions" && commissionsEmployee) {
      loadCommissionRules(commissionsEmployee);
    }
  }, [authenticated, view, commissionsEmployee]);

  useEffect(() => {
    if (authenticated && view === "booking-artist-summary") {
      loadBookingArtistSummary();
    }
  }, [authenticated, view, bookingArtistSummaryArtist]);

  useEffect(() => {
    if (authenticated && view === "artist-finance") {
      loadArtistFinance();
    }
  }, [authenticated, view, artistFinanceArtist]);

  useEffect(() => {
    if (
      authenticated
      && view === "finance-movements"
      && financeMovementForm.movementType === "pago"
      && financeMovementForm.businessArea === "booking"
      && financeMovementForm.artist
    ) {
      if (artistFinanceArtist !== financeMovementForm.artist) {
        setArtistFinanceArtist(financeMovementForm.artist);
      }
      loadArtistFinance(financeMovementForm.artist);
    }
  }, [
    authenticated,
    view,
    financeMovementForm.movementType,
    financeMovementForm.businessArea,
    financeMovementForm.artist,
  ]);

  useEffect(() => {
    if (authenticated && view === "finance-movements") {
      loadBookingArtists();
      loadFinanceEmployeeOptions();
      loadFinanceMovements();
    }
  }, [authenticated, view, currentUserModuleAccess, financeMovementArtistFilter, financeMovementProjectFilter, financeMovementStatusFilter]);

  useEffect(() => {
    setFinanceMovementForm((current) => {
      const canUseOffice = currentUser?.role === "admin" || Boolean(currentModulePermission("payroll_compensation")?.can_access);
      const hasArtist = Boolean(current.artist.trim());
      let nextArea = current.businessArea;
      let nextCategory = current.category;
      if (nextArea === "estructura" && !canUseOffice) {
        nextArea = "";
        nextCategory = "";
      }
      if (current.movementType === "pago") {
        if (nextArea === "booking" && hasArtist) {
          nextCategory = nextCategory || "cuenta_booking";
        }
        if (nextArea === "booking" && !hasArtist) {
          nextCategory = "";
        }
      } else if (nextArea === "estructura" && hasArtist) {
        nextArea = "";
        nextCategory = "";
      }
      if (nextArea === current.businessArea && nextCategory === current.category) return current;
      return {
        ...current,
        businessArea: nextArea,
        category: nextCategory,
      };
    });
  }, [financeMovementForm.artist, financeMovementForm.businessArea, financeMovementForm.movementType, currentUser?.role, currentUserPermissions]);

  const royaltyReportAccountOptions = useMemo(() => {
    if (!royaltyReportOptions || !royaltyReportSource) return [];
    return royaltyReportOptions.source_accounts.filter((item) => item.source === royaltyReportSource);
  }, [royaltyReportOptions, royaltyReportSource]);

  const digitalIncomeAccountOptions = useMemo(() => {
    if (!digitalIncome) return [];
    if (!digitalIncomeSource) return digitalIncome.options.accounts;
    return digitalIncome.options.source_accounts
      .filter((item) => item.source === digitalIncomeSource)
      .map((item) => item.account);
  }, [digitalIncome, digitalIncomeSource]);

  const royaltiesDashboardAccountOptions = useMemo(() => {
    if (!royaltiesDashboard) return [];
    if (!royaltiesDashboardSource) return royaltiesDashboard.options.accounts;
    return royaltiesDashboard.options.source_accounts
      .filter((item) => item.source === royaltiesDashboardSource)
      .map((item) => item.account);
  }, [royaltiesDashboard, royaltiesDashboardSource]);

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

  const bookingDirectCommissionSummary = useMemo(() => {
    return bookingForm.directCommissions.reduce((totals, commission) => {
      const amount = parseAmountInput(commission.amount, bookingFxRate);
      totals.total += amount;
      if (commission.destination === "incorpora_base") {
        totals.incorporated += amount;
      } else {
        totals.outgoing += amount;
      }
      return totals;
    }, { total: 0, outgoing: 0, incorporated: 0 });
  }, [bookingForm.directCommissions, bookingFxRate]);

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
    if (bookingForm.venueShortfallPolicy === "deuda_boliche") {
      return parseAmountInput(bookingForm.cachetAmount, bookingFxRate);
    }
    return parseAmountInput(bookingForm.venueCollectedAmount, bookingFxRate);
  }, [bookingForm.cachetAmount, bookingForm.venueCollectedAmount, bookingForm.venuePaymentIssue, bookingForm.venueShortfallPolicy, bookingFxRate]);

  const bookingVenueBalance = useMemo(() => {
    if (!bookingForm.venuePaymentIssue) return 0;
    if (bookingForm.venueShortfallPolicy === "ajustar_cachet") return 0;
    return Math.max(0, parseAmountInput(bookingForm.cachetAmount, bookingFxRate) - parseAmountInput(bookingForm.venueCollectedAmount, bookingFxRate));
  }, [bookingForm.cachetAmount, bookingForm.venueCollectedAmount, bookingForm.venuePaymentIssue, bookingForm.venueShortfallPolicy, bookingFxRate]);

  const bookingSuggestion = useMemo(() => {
    const cachet = bookingEffectiveCachet;
    const expenses = bookingExpenseTotal;
    const artistPercent = parseMoneyInput(bookingForm.artistPercent);
    const producerPercent = bookingForm.producerPercent
      ? parseMoneyInput(bookingForm.producerPercent)
      : Math.max(0, 100 - artistPercent);
    const net = cachet - expenses - bookingDirectCommissionSummary.total + bookingDirectCommissionSummary.incorporated;
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
    bookingDirectCommissionSummary.total,
    bookingDirectCommissionSummary.incorporated,
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
      if (status === "historico") return false;
      return (
        !bookingSettlementIsClosed(status)
        || bookingOpenBalanceAmount(item) > 0.01
      );
    });
    const closed = bookingItems.filter((item) => {
      const status = item.settlement_status || "pendiente";
      return bookingSettlementIsClosed(status) && bookingOpenBalanceAmount(item) <= 0.01;
    });
    const historical = bookingItems.filter((item) => (item.settlement_status || "") === "historico");

    return {
      totalShows: bookingItems.length,
      closedShows: closed.length,
      historicalShows: historical.length,
      pendingShows: pending.length,
      pendingAmount: pending.reduce((total, item) => total + bookingOpenBalanceAmount(item), 0),
      venueDebtAmount: bookingItems.reduce((total, item) => total + Math.max(0, bookingOpenTargetBalance(item, "venue")), 0),
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

  const selectedCommissionEmployee = useMemo(() => {
    return commissionEmployeeRecords.find((item) => String(item.id) === commissionsEmployee) || null;
  }, [commissionEmployeeRecords, commissionsEmployee]);

  const selectedCommissionPermission = useMemo(() => {
    return selectedCommissionEmployee?.permissions.find((permission) => permission.module_key === "booking_commissions") || null;
  }, [selectedCommissionEmployee]);

  const commissionAvailableArtists = useMemo(() => {
    if (!selectedCommissionPermission?.can_access) return [];
    const summaryArtists = (commissionSummary?.items || []).map((item) => item.artist);
    const baseArtists = summaryArtists.length ? summaryArtists : bookingArtists;
    const uniqueArtists = Array.from(new Set(baseArtists.filter(Boolean))).sort((a, b) => a.localeCompare(b));
    if (permissionHasAllArtists(selectedCommissionPermission)) {
      return uniqueArtists;
    }
    const scoped = new Set(permissionArtistNames(selectedCommissionPermission).map(artistScopeKey));
    return uniqueArtists.filter((artist) => scoped.has(artistScopeKey(artist)));
  }, [selectedCommissionPermission, commissionSummary, bookingArtists]);

  function commissionRuleKey(employeeId: string, artist: string) {
    return `${employeeId}::${artist}`;
  }

  function defaultCommissionRule(): CommissionRuleDraftState {
    return {
      percent: 0,
      base: "commissionable",
      includeBookingFeePaidShows: false,
      priorityOrder: null,
      startMonth: "",
      endMonth: "",
      active: true,
      notes: "",
    };
  }

  function storedCommissionRuleToDraft(rule: StoredCommissionRule): CommissionRuleDraftState {
    return {
      percent: Number(rule.percent || 0),
      base: rule.base === "total" ? "total" : "commissionable",
      includeBookingFeePaidShows: Boolean(rule.include_booking_fee_paid_shows),
      priorityOrder: rule.priority_order ? Number(rule.priority_order) : null,
      startMonth: rule.start_month || "",
      endMonth: rule.end_month || "",
      active: Boolean(rule.active),
      notes: rule.notes || "",
    };
  }

  function commissionRuleForArtist(artist: string) {
    return commissionRuleDrafts[commissionRuleKey(commissionsEmployee, artist)] || defaultCommissionRule();
  }

  function commissionPriorityOptions(artist: string, currentPriority: number | null) {
    const selectedEmployeeId = Number(commissionsEmployee || 0);
    const used = new Set(
      (commissionSummary?.commission_rules || [])
        .filter((rule) => artistScopeKey(rule.artist) === artistScopeKey(artist))
        .filter((rule) => rule.active && Number(rule.percent || 0) > 0)
        .filter((rule) => Number(rule.employee_id) !== selectedEmployeeId)
        .map((rule) => Number(rule.priority_order || 0))
        .filter((order) => order >= 1 && order <= 5),
    );
    const available = [1, 2, 3, 4, 5].filter((order) => !used.has(order));
    if (available.length === 0 && currentPriority && currentPriority >= 1 && currentPriority <= 5 && !used.has(currentPriority)) {
      return [currentPriority];
    }
    return available;
  }

  const commissionRulesForEmployee = useMemo(() => {
    if (!commissionsEmployee || !selectedCommissionPermission?.can_access) return [];
    return commissionAvailableArtists.map((artist) => ({
      employee: selectedCommissionEmployee?.display_name || "",
      artist,
      ...commissionRuleForArtist(artist),
    }));
  }, [commissionsEmployee, selectedCommissionEmployee, selectedCommissionPermission, commissionAvailableArtists, commissionRuleDrafts]);

  const commissionRulesMissingPriority = useMemo(() => {
    return commissionRulesForEmployee.filter((rule) => rule.active && Number(rule.percent || 0) > 0 && !rule.priorityOrder);
  }, [commissionRulesForEmployee]);

  const commissionResolvedPeriod = useMemo(
    () => resolvePeriod(selectionFromMonths(commissionStartMonth, commissionEndMonth), "commission_period"),
    [commissionStartMonth, commissionEndMonth],
  );

  const commissionSettlementRows = useMemo(() => {
    if (!commissionsEmployee || !selectedCommissionPermission?.can_access) return [];
    const allowedArtists = new Set(commissionAvailableArtists);
    return (commissionSummary?.items || [])
      .filter((item) => allowedArtists.has(item.artist))
      .flatMap((item) => Object.entries(item.months)
      .filter(([month]) => {
        if (commissionResolvedPeriod.startMonth && month < commissionResolvedPeriod.startMonth) return false;
        if (commissionResolvedPeriod.endMonth && month > commissionResolvedPeriod.endMonth) return false;
        return true;
      })
      .map(([month, monthItem]) => {
        const employeeId = Number(commissionsEmployee);
        const rule = commissionRuleForArtist(item.artist);
        const ruleInPeriod = (!rule.startMonth || month >= rule.startMonth) && (!rule.endMonth || month <= rule.endMonth);
        const percent = rule.active && ruleInPeriod ? Number(rule.percent || 0) : 0;
        const details = (monthItem.commission_details || []).filter((detail) => Number(detail.employee_id) === employeeId);
        const baseAmount = details.reduce((sum, detail) => sum + Number(detail.base_amount || 0), 0);
        const commissionAmount = details.reduce((sum, detail) => sum + Number(detail.commission_amount || 0), 0);
        const firstPriority = details.length ? Math.min(...details.map((detail) => Number(detail.priority_order || 1))) : rule.priorityOrder;
        return {
          month,
          artist: item.artist,
          shows: monthItem.shows,
          indyanaTotal: monthItem.indyana_total,
          commissionableBase: monthItem.commissionable_total,
          nonCommissionable: monthItem.non_commissionable_total,
          percent,
          priorityOrder: firstPriority,
          baseAmount: percent > 0 ? baseAmount : 0,
          commissionAmount: percent > 0 ? commissionAmount : 0,
          notes: item.notes.length ? item.notes.join(" / ") : "Comisiona normal",
          ruleNotes: !rule.active
            ? "Regla inactiva."
            : !ruleInPeriod
              ? "Fuera de vigencia."
              : rule.notes || (percent > 0
                ? rule.includeBookingFeePaidShows
                  ? "Cobra tambien shows con booking ya pagado."
                  : "Respeta exclusion general."
                : "Sin porcentaje configurado."),
        };
      }))
      .sort((a, b) => b.month.localeCompare(a.month) || a.artist.localeCompare(b.artist));
  }, [commissionSummary, commissionsEmployee, selectedCommissionPermission, commissionAvailableArtists, commissionRuleDrafts, commissionResolvedPeriod]);

  const visibleCommissionSettlementRows = useMemo(() => {
    const query = commissionSettlementSearch.trim().toLowerCase();
    if (!query) return commissionSettlementRows;
    return commissionSettlementRows.filter((item) => [
      item.month,
      item.artist,
      item.notes,
      item.ruleNotes,
    ].some((value) => String(value || "").toLowerCase().includes(query)));
  }, [commissionSettlementRows, commissionSettlementSearch]);

  const commissionTotals = useMemo(() => {
    return visibleCommissionSettlementRows.reduce(
      (totals, item) => ({
        shows: totals.shows + item.shows,
        indyanaTotal: totals.indyanaTotal + item.indyanaTotal,
        baseAmount: totals.baseAmount + item.baseAmount,
        nonCommissionable: totals.nonCommissionable + item.nonCommissionable,
        commissionAmount: totals.commissionAmount + item.commissionAmount,
      }),
      { shows: 0, indyanaTotal: 0, baseAmount: 0, nonCommissionable: 0, commissionAmount: 0 },
    );
  }, [visibleCommissionSettlementRows]);

  const commissionPeriodLabel = commissionResolvedPeriod.label === "Todo" ? "Todos los meses" : commissionResolvedPeriod.label;

  function escapePrintHtml(value: unknown) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function printCommissionSettlement() {
    if (!selectedCommissionEmployee || !selectedCommissionPermission?.can_access) {
      setMessage({ type: "error", text: "Selecciona un empleado con acceso a Comisiones." });
      return;
    }

    const generatedAt = new Date().toLocaleString("es-AR");
    const rowsHtml = visibleCommissionSettlementRows.length
      ? visibleCommissionSettlementRows.map((item) => `
          <tr>
            <td>${escapePrintHtml(item.month)}</td>
            <td><strong>${escapePrintHtml(item.artist)}</strong></td>
            <td class="number">${item.shows}</td>
            <td class="money">${escapePrintHtml(ars(item.indyanaTotal))}</td>
            <td class="money">${escapePrintHtml(ars(item.baseAmount))}</td>
            <td class="money">${escapePrintHtml(ars(item.nonCommissionable))}</td>
            <td class="number">${escapePrintHtml(item.priorityOrder || "-")}</td>
            <td class="number">${escapePrintHtml(pct(item.percent))}</td>
            <td class="money strong">${escapePrintHtml(ars(item.commissionAmount))}</td>
            <td>${escapePrintHtml(item.notes)}<span>${escapePrintHtml(item.ruleNotes)}</span></td>
          </tr>
        `).join("")
      : `<tr><td colspan="9">Sin movimientos para los filtros seleccionados.</td></tr>`;

    const searchLabel = commissionSettlementSearch.trim()
      ? `Busqueda aplicada: ${commissionSettlementSearch.trim()}`
      : "Sin busqueda adicional";
    const popup = window.open("", "_blank", "width=1100,height=800");
    if (!popup) {
      setMessage({ type: "error", text: "El navegador bloqueo la ventana de impresion." });
      return;
    }

    popup.document.write(`<!doctype html>
      <html>
        <head>
          <meta charset="utf-8" />
          <title>Liquidacion de comisiones - ${escapePrintHtml(selectedCommissionEmployee.display_name)}</title>
          <style>
            @page { size: A4 landscape; margin: 14mm; }
            * { box-sizing: border-box; }
            body {
              margin: 0;
              color: #162033;
              font-family: Arial, Helvetica, sans-serif;
              font-size: 11px;
              background: #ffffff;
            }
            .header {
              display: flex;
              justify-content: space-between;
              gap: 24px;
              border-bottom: 3px solid #1f4e78;
              padding-bottom: 14px;
              margin-bottom: 18px;
            }
            .brand {
              font-size: 13px;
              color: #607089;
              font-weight: 700;
              letter-spacing: 0.04em;
              text-transform: uppercase;
            }
            h1 {
              margin: 6px 0 4px;
              font-size: 26px;
              color: #10243f;
            }
            .meta {
              text-align: right;
              color: #607089;
              line-height: 1.5;
              min-width: 230px;
            }
            .kpis {
              display: grid;
              grid-template-columns: repeat(5, 1fr);
              gap: 10px;
              margin-bottom: 18px;
            }
            .kpi {
              border: 1px solid #d8e1ef;
              border-radius: 8px;
              padding: 10px 12px;
              background: #f7f9fc;
              min-height: 64px;
            }
            .kpi span {
              display: block;
              color: #607089;
              font-size: 10px;
              font-weight: 700;
              text-transform: uppercase;
              margin-bottom: 6px;
            }
            .kpi strong {
              display: block;
              font-size: 17px;
              color: #10243f;
            }
            .kpi.total {
              background: #ecf7f2;
              border-color: #9fd7bd;
            }
            table {
              width: 100%;
              border-collapse: collapse;
              table-layout: fixed;
            }
            th {
              background: #1f4e78;
              color: white;
              font-size: 10px;
              padding: 8px 7px;
              text-align: left;
            }
            td {
              border-bottom: 1px solid #d9e2ef;
              padding: 7px;
              vertical-align: top;
              line-height: 1.25;
            }
            tbody tr:nth-child(even) td { background: #f8fafc; }
            .number, .money { text-align: right; white-space: nowrap; }
            .strong { font-weight: 700; color: #0f5132; }
            td span {
              display: block;
              margin-top: 3px;
              color: #607089;
              font-size: 9px;
            }
            .note {
              margin-top: 12px;
              color: #607089;
              font-size: 10px;
            }
            .footer {
              margin-top: 16px;
              border-top: 1px solid #d9e2ef;
              padding-top: 8px;
              color: #607089;
              display: flex;
              justify-content: space-between;
              font-size: 10px;
            }
          </style>
        </head>
        <body>
          <header class="header">
            <div>
              <div class="brand">VPO Corp</div>
              <h1>Liquidacion de comisiones</h1>
              <div>Empleado: <strong>${escapePrintHtml(selectedCommissionEmployee.display_name)}</strong></div>
              <div>Periodo: <strong>${escapePrintHtml(commissionPeriodLabel)}</strong></div>
              <div>${escapePrintHtml(searchLabel)}</div>
            </div>
            <div class="meta">
              <div>Generado: ${escapePrintHtml(generatedAt)}</div>
              <div>Fuente: Booking Indyana</div>
              <div>Base: reglas guardadas de comision</div>
            </div>
          </header>
          <section class="kpis">
            <div class="kpi"><span>Shows incluidos</span><strong>${commissionTotals.shows}</strong></div>
            <div class="kpi"><span>Indyana total</span><strong>${escapePrintHtml(ars(commissionTotals.indyanaTotal))}</strong></div>
            <div class="kpi"><span>Base empleado</span><strong>${escapePrintHtml(ars(commissionTotals.baseAmount))}</strong></div>
            <div class="kpi"><span>Excluido general</span><strong>${escapePrintHtml(ars(commissionTotals.nonCommissionable))}</strong></div>
            <div class="kpi total"><span>Comision calculada</span><strong>${escapePrintHtml(ars(commissionTotals.commissionAmount))}</strong></div>
          </section>
          <table>
            <thead>
              <tr>
                <th style="width: 8%;">Mes</th>
                <th style="width: 17%;">Artista</th>
                <th style="width: 7%;">Shows</th>
                <th style="width: 12%;">Indyana total</th>
                <th style="width: 12%;">Base empleado</th>
                <th style="width: 12%;">Excluido general</th>
                <th style="width: 7%;">Orden</th>
                <th style="width: 8%;">%</th>
                <th style="width: 12%;">Comision</th>
                <th style="width: 12%;">Notas</th>
              </tr>
            </thead>
            <tbody>${rowsHtml}</tbody>
          </table>
          <p class="note">Este informe refleja los filtros visibles en pantalla al momento de imprimir.</p>
          <footer class="footer">
            <span>VPO Corp - Comisiones</span>
            <span>${escapePrintHtml(selectedCommissionEmployee.display_name)} - ${escapePrintHtml(commissionPeriodLabel)}</span>
          </footer>
          <script>
            window.addEventListener("load", () => {
              window.focus();
              setTimeout(() => window.print(), 250);
            });
          </script>
        </body>
      </html>`);
    popup.document.close();
  }

  function updateCommissionRuleDraft(artist: string, patch: Partial<CommissionRuleDraftState>) {
    if (!commissionsEmployee) return;
    const key = commissionRuleKey(commissionsEmployee, artist);
    setCommissionRuleDrafts((current) => ({
      ...current,
      [key]: {
        ...defaultCommissionRule(),
        ...current[key],
        ...patch,
      },
    }));
    setCommissionDirtyEmployees((current) => ({ ...current, [commissionsEmployee]: true }));
  }

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

  const filteredEmployeeRecords = useMemo(() => {
    const query = employeeSearch.trim().toLowerCase();
    if (!query) return employeeRecords;

    return employeeRecords.filter((item) => [
      item.display_name,
      item.legal_name,
      item.cuit,
      item.phone,
      item.email,
      item.address,
      item.notes,
      item.functions.join(" "),
      item.active ? "activo" : "inactivo",
    ].some((value) => String(value || "").toLowerCase().includes(query)));
  }, [employeeRecords, employeeSearch]);

  function canAccessModule(moduleKey: string) {
    if (currentUser?.role === "admin") return true;
    const allowed = currentUserModuleAccess ?? [];
    return allowed.includes("*") || allowed.includes(moduleKey);
  }

  function canShowMenuView(targetView: View) {
    if (targetView === "menu") return true;
    if (targetView === "booking") {
      return canAccessModule("booking_agenda") || canAccessBookingMode("individual") || canAccessBookingMode("shared");
    }
    const moduleKey = VIEW_MODULE_KEYS[targetView];
    return moduleKey ? canAccessModule(moduleKey) : false;
  }

  function canAccessBookingMode(mode: BookingWorkspaceMode) {
    return canAccessModule(mode === "individual" ? "booking" : "composite_booking");
  }

  function currentModulePermission(moduleKey: string) {
    if (currentUser?.role === "admin") {
      return {
        module_key: moduleKey,
        can_access: true,
        can_create: true,
        can_view_history: true,
        can_edit: true,
        can_approve: true,
        scope: [{ scope_type: "all", scope_ref: "*" }],
        notes: null,
      } as EmployeePermission;
    }
    return (currentUserPermissions || []).find((permission) => permission.module_key === moduleKey) || null;
  }

  function canCreateModule(moduleKey: string) {
    return Boolean(currentModulePermission(moduleKey)?.can_create);
  }

  function canEditModule(moduleKey: string) {
    return Boolean(currentModulePermission(moduleKey)?.can_edit);
  }

  function canApproveModule(moduleKey: string) {
    return Boolean(currentModulePermission(moduleKey)?.can_approve);
  }

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
    const effectiveGross = bookingLabForm.venueShortfallPolicy === "ajustar_cachet" ? collected : gross;
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
    const eventBase = effectiveGross - eventExpenses - directCommissions;
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
      effectiveGross,
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
      venueBalance: bookingLabForm.venueShortfallPolicy === "deuda_boliche" ? gross - collected : 0,
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
    setPassword("");
    setCurrentPassword("");
    setNewPassword("");
    setNewPasswordConfirm("");
    setView("menu");
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");
  }

  async function changeOwnPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    if (newPassword !== newPasswordConfirm) {
      setMessage({ type: "error", text: "La confirmacion no coincide." });
      return;
    }
    setLoading(true);
    const response = await fetch("/api/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ currentPassword, newPassword }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo cambiar la contrasena." }));
      setMessage({ type: "error", text: data.error || "No se pudo cambiar la contrasena." });
      setLoading(false);
      return;
    }
    const data = await response.json();
    setCurrentUser(data.user || (currentUser ? { ...currentUser, mustChangePassword: false } : null));
    setCurrentPassword("");
    setNewPassword("");
    setNewPasswordConfirm("");
    setMessage({ type: "ok", text: "Contrasena actualizada correctamente." });
    setLoading(false);
  }

  function buildPayload(output: "excel" | "google_sheet" | "executive_pdf") {
    const period = resolvePeriod(selectionFromMonths(startMonth, endMonth), "monthly_report");
    return {
      keywords: keywords.split(/[;,]/).map((item) => item.trim()).filter(Boolean),
      start_month: period.startMonth,
      end_month: period.endMonth,
      period_basis: periodBasis,
      mode,
      raw_limit: Number(rawLimit) || 0,
      source: royaltyReportSource || null,
      account: royaltyReportAccount || null,
      refresh_cache: false,
      output,
    };
  }

  async function loadRoyaltyReportOptions() {
    const response = await fetch("/api/report-options", { cache: "no-store" });
    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudieron cargar las distribuidoras." }));
      setMessage({ type: "error", text: data.error || "No se pudieron cargar las distribuidoras." });
      return;
    }
    setRoyaltyReportOptions(await response.json());
  }

  function validatePeriod() {
    const period = resolvePeriod(selectionFromMonths(startMonth, endMonth), "monthly_report");
    if (isResolvedPeriodInvalid(period)) {
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

  async function generateExecutivePdf() {
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");
    if (!validatePeriod()) return;
    setLoading(true);

    const response = await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload("executive_pdf")),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo generar el PDF ejecutivo." }));
      setMessage({ type: "error", text: data.error || "No se pudo generar el PDF ejecutivo." });
      setLoading(false);
      return;
    }

    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
    const filename = filenameMatch?.[1] || "reporte_ejecutivo_regalias.pdf";
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    setLastFile(filename);
    setMessage({ type: "ok", text: "PDF ejecutivo generado correctamente." });
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
        include_zero_total_artists: statementIncludeZeros,
        report_version: statementReportVersion,
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

  async function loadCustomReportOptions() {
    const response = await fetch("/api/custom-reports", { cache: "no-store" });
    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudieron cargar los reportes personalizados." }));
      setMessage({ type: "error", text: data.error || "No se pudieron cargar los reportes personalizados." });
      return;
    }

    const data = await response.json() as CustomReportOptions;
    setCustomReportOptions(data);
    const allAccountKeys = (data.source_accounts || []).map(customReportSourceAccountKey);
    if (data.sources?.length) {
      setCustomReportSources(data.sources);
    }
    const template = data.templates?.find((item) => item.key === "los_anormales") || data.templates?.[0];
    if (template) {
      applyCustomReportTemplateState(template.key, template, allAccountKeys);
    }
  }

  function readCustomReportStates(): Record<string, CustomReportSavedState> {
    if (typeof window === "undefined") return {};
    try {
      const raw = window.localStorage.getItem(CUSTOM_REPORT_STATE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function saveCustomReportState(key = customReportTemplateKey) {
    if (typeof window === "undefined" || !key) return;
    try {
      const states = readCustomReportStates();
      states[key] = {
        title: customReportTitle,
        startMonth: customReportStartMonth,
        endMonth: customReportEndMonth,
        terms: customReportTerms,
        sourceAccounts: customReportSourceAccounts,
        flags: customReportFlags,
      };
      window.localStorage.setItem(CUSTOM_REPORT_STATE_KEY, JSON.stringify(states));
    } catch {
      // El reporte sigue funcionando aunque el navegador bloquee localStorage.
    }
  }

  function applyCustomReportTemplateState(key: string, template: CustomReportTemplate, allAccountKeys?: string[]) {
    const saved = readCustomReportStates()[key];
    const defaultFlags = Object.fromEntries((template.options || []).map((option) => [option.key, Boolean(option.default)]));
    setCustomReportTemplateKey(key);
    setCustomReportTitle(saved?.title || template.title);
    setCustomReportStartMonth(saved?.startMonth || "");
    setCustomReportEndMonth(saved?.endMonth || template.default_end_month || "2026-03");
    setCustomReportTerms(saved?.terms || template.terms.join("\n"));
    setCustomReportSourceAccounts(saved?.sourceAccounts?.length ? saved.sourceAccounts : (allAccountKeys || (customReportOptions?.source_accounts || []).map(customReportSourceAccountKey)));
    setCustomReportFlags(saved?.flags || defaultFlags);
  }

  function selectCustomReportTemplate(key: string) {
    if (key === customReportTemplateKey) return;
    saveCustomReportState();
    const template = customReportOptions?.templates.find((item) => item.key === key);
    if (template) {
      applyCustomReportTemplateState(key, template);
      setLastFile("");
      setMessage(null);
    }
  }

  function customReportTermList() {
    return customReportTerms
      .split(/\r?\n|;/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function currentCustomReportTemplate() {
    return customReportOptions?.templates.find((template) => template.key === customReportTemplateKey);
  }

  function customReportRequiresTerms() {
    return currentCustomReportTemplate()?.requires_terms !== false;
  }

  function customReportSupportsSources() {
    return currentCustomReportTemplate()?.supports_sources !== false;
  }

  function customReportSupportsStartMonth() {
    return currentCustomReportTemplate()?.supports_start_month !== false;
  }

  function setCustomReportFlag(key: string, value: boolean) {
    setCustomReportFlags((current) => ({ ...current, [key]: value }));
  }

  function customReportSourceAccountKey(item: CustomReportSourceAccount) {
    return `${item.source}||${item.account}`;
  }

  function customReportAccountPayload() {
    return customReportSourceAccounts
      .map((key) => {
        const [source, account] = key.split("||");
        return { source, account };
      })
      .filter((item) => item.source && item.account);
  }

  function customReportAccountsForSource(source: string) {
    return (customReportOptions?.source_accounts || []).filter((item) => item.source === source);
  }

  function customReportSourceFullySelected(source: string) {
    const accounts = customReportAccountsForSource(source);
    return accounts.length > 0 && accounts.every((item) => customReportSourceAccounts.includes(customReportSourceAccountKey(item)));
  }

  function toggleCustomReportSource(source: string) {
    const accountKeys = customReportAccountsForSource(source).map(customReportSourceAccountKey);
    if (!accountKeys.length) return;
    const allSelected = accountKeys.every((key) => customReportSourceAccounts.includes(key));
    setCustomReportSourceAccounts((current) => (
      allSelected
        ? current.filter((key) => !accountKeys.includes(key))
        : Array.from(new Set([...current, ...accountKeys]))
    ));
  }

  function toggleCustomReportSourceAccount(key: string) {
    setCustomReportSourceAccounts((current) => (
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key]
    ));
  }

  function selectAllCustomReportSources() {
    setCustomReportSources(customReportOptions?.sources || []);
    setCustomReportSourceAccounts((customReportOptions?.source_accounts || []).map(customReportSourceAccountKey));
  }

  function clearCustomReportSources() {
    setCustomReportSources([]);
    setCustomReportSourceAccounts([]);
  }

  async function generateCustomReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setLastFile("");

    const customReportPeriod = customReportSupportsStartMonth()
      ? resolvePeriod(selectionFromMonths(customReportStartMonth, customReportEndMonth), "custom_report")
      : resolvePeriod(selectionFromUntil(customReportEndMonth), "custom_report");

    if (customReportSupportsStartMonth() && isResolvedPeriodInvalid(customReportPeriod)) {
      setMessage({ type: "error", text: "El periodo desde no puede ser mayor que hasta." });
      return;
    }

    const terms = customReportTermList();
    if (customReportRequiresTerms() && terms.length === 0) {
      setMessage({ type: "error", text: "La lista editable no puede quedar vacia." });
      return;
    }
    if (customReportSupportsSources() && customReportOptions?.source_accounts?.length && customReportSourceAccounts.length === 0) {
      setMessage({ type: "error", text: "Selecciona al menos una distribuidora/cuenta." });
      return;
    }

    const selectedAccounts = customReportSupportsSources() ? customReportAccountPayload() : [];
    setCustomReportLoading(true);
    const response = await fetch("/api/custom-reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template_key: customReportTemplateKey,
        report_title: customReportTitle || "Regalias Los Anormales",
        terms,
        start_month: customReportSupportsStartMonth() ? customReportPeriod.startMonth : null,
        end_month: customReportPeriod.endMonth,
        sources: Array.from(new Set(selectedAccounts.map((item) => item.source))),
        source_accounts: selectedAccounts,
        refresh_cache: false,
        hide_zero_amounts: Boolean(customReportFlags.hide_zero_amounts),
        exclude_related_videos: Boolean(customReportFlags.exclude_related_videos),
      }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo generar el reporte personalizado." }));
      setMessage({ type: "error", text: data.error || "No se pudo generar el reporte personalizado." });
      setCustomReportLoading(false);
      return;
    }

    const blob = await response.blob();
    const filename = filenameFromDisposition(response.headers.get("content-disposition"), "reporte_personalizado.xlsx");
    downloadBlob(blob, filename);
    setLastFile(filename);
    setMessage({ type: "ok", text: "Reporte personalizado generado correctamente." });
    setCustomReportLoading(false);
  }

  async function loadParticipation(refresh: boolean) {
    setMessage(null);
    const participationPeriod = resolvePeriod(
      selectionFromMonths(participationStartMonth, participationEndMonth),
      "preset_or_range",
    );

    if (
      participationPreset === "custom"
      && isResolvedPeriodInvalid(participationPeriod)
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
      if (participationPeriod.startMonth) params.set("start_month", participationPeriod.startMonth);
      if (participationPeriod.endMonth) params.set("end_month", participationPeriod.endMonth);
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
      preSplitAdjustments: current.preSplitAdjustments.map((adjustment) => {
        if (adjustment.uid !== uid) return adjustment;
        const next = { ...adjustment, [key]: value };
        if (key === "destination" && value === "artist") {
          next.recoveryAutoApply = false;
        }
        return next;
      }),
    }));
  }

  function addBookingDirectCommission(destination: "salida_directa" | "incorpora_base" = "salida_directa") {
    setBookingForm((current) => ({
      ...current,
      directCommissions: [...current.directCommissions, newBookingDirectCommission(destination)],
    }));
  }

  function removeBookingDirectCommission(uid: string) {
    setBookingForm((current) => ({
      ...current,
      directCommissions: current.directCommissions.filter((commission) => commission.uid !== uid),
    }));
  }

  function updateBookingDirectCommissionField<K extends keyof BookingDirectCommissionForm>(
    uid: string,
    key: K,
    value: BookingDirectCommissionForm[K],
  ) {
    setBookingForm((current) => ({
      ...current,
      directCommissions: current.directCommissions.map((commission) => (
        commission.uid === uid ? { ...commission, [key]: value } : commission
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

  async function loadSourceMonitor() {
    setSourceMonitorLoading(true);
    try {
      const response = await fetch("/api/source-monitor", { cache: "no-store" });
      if (response.ok) {
        const data = await response.json();
        setSourceMonitor(data);
      } else {
        setMessage({ type: "error", text: "No se pudo cargar el control de distribuidoras." });
      }
    } catch {
      setMessage({ type: "error", text: "No se pudo cargar el control de distribuidoras." });
    } finally {
      setSourceMonitorLoading(false);
    }
  }

  async function loadCatalog(nextOffset = catalogOffset) {
    setCatalogLoading(true);
    try {
      const resolvedCatalogPeriod = resolvePeriod(catalogPeriod, "activity_window");
      const params = new URLSearchParams();
      if (catalogSource) params.set("source", catalogSource);
      if (catalogAccount) params.set("account", catalogAccount);
      if (catalogArtist) params.set("artist", catalogArtist);
      if (catalogKeyword.trim()) params.set("keyword", catalogKeyword.trim());
      if (catalogLabel.trim()) params.set("label", catalogLabel.trim());
      if (resolvedCatalogPeriod.startMonth) params.set("start_month", resolvedCatalogPeriod.startMonth);
      if (resolvedCatalogPeriod.endMonth) params.set("end_month", resolvedCatalogPeriod.endMonth);
      params.set("status", catalogStatus);
      params.set("limit", String(catalogLimit));
      params.set("offset", String(nextOffset));

      const response = await fetch(`/api/catalog?${params.toString()}`, { cache: "no-store" });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ error: "No se pudo cargar el catalogo." }));
        setMessage({ type: "error", text: payload.error || "No se pudo cargar el catalogo." });
        return;
      }
      const data = await response.json();
      setCatalogData(data);
      setCatalogOffset(nextOffset);
    } catch {
      setMessage({ type: "error", text: "No se pudo cargar el catalogo." });
    } finally {
      setCatalogLoading(false);
    }
  }

  async function loadDigitalIncome() {
    setDigitalIncomeLoading(true);
    try {
      const digitalPeriod = resolvePeriod(digitalIncomePeriod, "dashboard_period");
      const params = new URLSearchParams();
      if (digitalIncomeArtistKeyword.trim()) params.set("artist_keyword", digitalIncomeArtistKeyword.trim());
      if (digitalIncomeSource) params.set("source", digitalIncomeSource);
      if (digitalIncomeAccount) params.set("account", digitalIncomeAccount);
      if (digitalPeriod.startMonth) params.set("start_month", digitalPeriod.startMonth);
      if (digitalPeriod.endMonth) params.set("end_month", digitalPeriod.endMonth);
      params.set("period_mode", digitalPeriod.mode);
      params.set("limit", String(digitalIncomeLimit));

      const response = await fetch(`/api/digital-income?${params.toString()}`, { cache: "no-store" });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ error: "No se pudo cargar ingresos digitales." }));
        setMessage({ type: "error", text: payload.error || "No se pudo cargar ingresos digitales." });
        return;
      }
      const data = await response.json();
      setDigitalIncome(data);
    } catch {
      setMessage({ type: "error", text: "No se pudo cargar ingresos digitales." });
    } finally {
      setDigitalIncomeLoading(false);
    }
  }

  async function loadRoyaltiesDashboard() {
    setRoyaltiesDashboardLoading(true);
    try {
      const dashboardPeriod = resolvePeriod(royaltiesDashboardPeriod, "dashboard_period");
      const params = new URLSearchParams();
      if (royaltiesDashboardKeyword.trim()) params.set("keyword", royaltiesDashboardKeyword.trim());
      if (royaltiesDashboardSource) params.set("source", royaltiesDashboardSource);
      if (royaltiesDashboardAccount) params.set("account", royaltiesDashboardAccount);
      if (dashboardPeriod.startMonth) params.set("start_month", dashboardPeriod.startMonth);
      if (dashboardPeriod.endMonth) params.set("end_month", dashboardPeriod.endMonth);
      params.set("period_mode", dashboardPeriod.mode);
      params.set("period_basis", royaltiesDashboardPeriodBasis);
      params.set("limit", "10");

      const response = await fetch(`/api/royalties-dashboard?${params.toString()}`, { cache: "no-store" });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ error: "No se pudo cargar dashboard de regalias." }));
        setMessage({ type: "error", text: payload.error || "No se pudo cargar dashboard de regalias." });
        return;
      }
      const data = await response.json();
      setRoyaltiesDashboard(data);
    } catch {
      setMessage({ type: "error", text: "No se pudo cargar dashboard de regalias." });
    } finally {
      setRoyaltiesDashboardLoading(false);
    }
  }

  async function loadDistributorConfig() {
    setDistributorConfigLoading(true);
    try {
      const response = await fetch("/api/distributor-config", { cache: "no-store" });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ error: "No se pudo cargar el configurador." }));
        setMessage({ type: "error", text: payload.error || "No se pudo cargar el configurador." });
        return;
      }
      const data = await response.json();
      setDistributorConfig(data);
      setDistributorPersonalizationEnabled(Boolean(data.report_personalization?.enabled));
      setDistributorAdjustmentDrafts(Object.fromEntries(
        (data.accounts || []).map((account: DistributorAccountPolicy) => [
          account.policy_id,
          String(Number(account.report_net_adjustment_pct || 0)),
        ]),
      ));
      if (!distributorConfigAccountId && data.accounts?.length) {
        setDistributorConfigAccountId(data.accounts[0].policy_id);
      }
    } catch {
      setMessage({ type: "error", text: "No se pudo cargar el configurador." });
    } finally {
      setDistributorConfigLoading(false);
    }
  }

  function parseDistributorAdjustment(value: string) {
    const normalized = String(value || "0").replace(/\./g, "").replace(",", ".").trim();
    const parsed = Number(normalized || "0");
    return Number.isFinite(parsed) ? parsed : NaN;
  }

  function updateDistributorAdjustment(policyId: string, value: string) {
    setDistributorAdjustmentDrafts((current) => ({ ...current, [policyId]: value }));
  }

  async function saveDistributorPersonalization() {
    if (!currentUser?.canEdit) {
      setMessage({ type: "error", text: "Necesitas permisos de editor/admin para guardar porcentajes." });
      return;
    }
    setDistributorPersonalizationSaving(true);
    try {
      const accounts = (distributorConfig?.accounts || []).map((account) => {
        const pct = parseDistributorAdjustment(distributorAdjustmentDrafts[account.policy_id] ?? "0");
        if (!Number.isFinite(pct) || pct < 0 || pct > 100) {
          throw new Error(`Porcentaje invalido en ${account.display_name}.`);
        }
        return {
          policy_id: account.policy_id,
          report_net_adjustment_pct: pct,
        };
      });
      const response = await fetch("/api/distributor-config", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: distributorPersonalizationEnabled,
          accounts,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ error: "No se pudo guardar la personalizacion." }));
        setMessage({ type: "error", text: payload.error || "No se pudo guardar la personalizacion." });
        return;
      }
      setRoyaltiesDashboard(null);
      setMessage({ type: "ok", text: "Porcentajes guardados. El dashboard y los nuevos reportes ya usan esta configuracion." });
      await loadDistributorConfig();
    } catch (error) {
      const text = error instanceof Error ? error.message : "No se pudo guardar la personalizacion.";
      setMessage({ type: "error", text });
    } finally {
      setDistributorPersonalizationSaving(false);
    }
  }

  async function updateCatalogStatus(item: CatalogItem, active: boolean) {
    const response = await fetch("/api/catalog", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        catalog_key: item.catalog_key,
        active,
        include_in_reports: active,
        business_status: active ? "vpo_catalog" : "inactive",
        notes: active ? "" : "Excluido manualmente desde Catalogo General.",
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ error: "No se pudo actualizar el catalogo." }));
      setMessage({ type: "error", text: payload.error || "No se pudo actualizar el catalogo." });
      return;
    }
    setMessage({ type: "ok", text: active ? "Tema marcado como activo." : "Tema marcado como inactivo." });
    await loadCatalog(catalogOffset);
  }

  async function updateCatalogLabel(item: CatalogItem) {
    if (!currentUser?.canEdit) return;
    setCatalogLabelSaving(item.catalog_key);
    const response = await fetch("/api/catalog", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        catalog_key: item.catalog_key,
        active: item.active,
        include_in_reports: item.include_in_reports,
        business_status: item.catalog_business_status || (item.active ? "vpo_catalog" : "inactive"),
        notes: item.status_notes || "",
        label_normalized_override: catalogLabelDraft.trim() || null,
      }),
    });
    setCatalogLabelSaving("");
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ error: "No se pudo actualizar el label." }));
      setMessage({ type: "error", text: payload.error || "No se pudo actualizar el label." });
      return;
    }
    setCatalogLabelEditKey("");
    setCatalogLabelDraft("");
    setMessage({ type: "ok", text: "Label normalizado actualizado." });
    await loadCatalog(catalogOffset);
  }

  async function updateSourceMonitorItem(id: string, body: Partial<SourceMonitorItem>) {
    setSourceMonitorLoading(true);
    try {
      const response = await fetch(`/api/source-monitor?id=${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        setMessage({ type: "error", text: "No se pudo actualizar el control de la distribuidora." });
        return;
      }
      await loadSourceMonitor();
    } catch {
      setMessage({ type: "error", text: "No se pudo actualizar el control de la distribuidora." });
    } finally {
      setSourceMonitorLoading(false);
    }
  }

  async function processSourceMonitorItem(id: string) {
    setSourceMonitorProcessingId(id);
    setMessage(null);
    try {
      const response = await fetch(`/api/source-monitor?id=${encodeURIComponent(id)}&action=process`, {
        method: "POST",
      });
      if (!response.ok) {
        let text = "No se pudo procesar la distribuidora.";
        try {
          const payload = await response.json();
          text = payload.error || text;
        } catch {
          // keep generic message
        }
        setMessage({ type: "error", text });
        return;
      }
      const data = await response.json();
      setSourceMonitorLastProcess(data);
      await loadSourceMonitor();
      setMessage({ type: "ok", text: "Pipeline nuevo procesado localmente. Revisa el resumen antes de publicar a cloud." });
    } catch {
      setMessage({ type: "error", text: "No se pudo procesar la distribuidora." });
    } finally {
      setSourceMonitorProcessingId("");
    }
  }

  async function publishSourceMonitorMarts() {
    setSourceMonitorPublishing(true);
    setSourceMonitorPublishJob(null);
    setMessage(null);
    try {
      const response = await fetch("/api/source-monitor?action=publish", {
        method: "POST",
      });
      if (!response.ok) {
        let text = "No se pudieron publicar los marts a cloud.";
        try {
          const payload = await response.json();
          text = payload.error || text;
        } catch {
          // keep generic message
        }
        setMessage({ type: "error", text });
        return;
      }
      const data = await response.json();
      setSourceMonitorPublishJob(data);
      setMessage({ type: "ok", text: "Publicacion iniciada. Podes dejar la pantalla abierta mientras se actualiza el estado." });
      pollSourceMonitorPublishJob(data.job_id);
    } catch {
      setMessage({ type: "error", text: "No se pudo iniciar la publicacion de datos analiticos." });
      setSourceMonitorPublishing(false);
    }
  }

  async function pollSourceMonitorPublishJob(jobId: string) {
    try {
      const response = await fetch(`/api/source-monitor?action=publish-status&job_id=${encodeURIComponent(jobId)}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        let text = "No se pudo consultar el estado de publicacion.";
        try {
          const payload = await response.json();
          text = payload.error || text;
        } catch {
          // keep generic message
        }
        setMessage({ type: "error", text });
        setSourceMonitorPublishing(false);
        return;
      }
      const job: SourceMonitorPublishJob = await response.json();
      setSourceMonitorPublishJob(job);
      if (job.status === "completed" && job.result) {
        setSourceMonitorLastPublish(job.result);
        setMessage({ type: "ok", text: "Datos analiticos publicados a cloud. La web online puede usar estos datos." });
        setSourceMonitorPublishing(false);
        await loadSourceMonitor();
        return;
      }
      if (job.status === "failed") {
        const errorText = typeof job.error === "string" ? job.error : JSON.stringify(job.error || "Error de publicacion");
        setMessage({ type: "error", text: `Fallo la publicacion: ${errorText}` });
        setSourceMonitorPublishing(false);
        return;
      }
      window.setTimeout(() => pollSourceMonitorPublishJob(jobId), 4000);
    } catch {
      setMessage({ type: "error", text: "No se pudo consultar el estado de publicacion." });
      setSourceMonitorPublishing(false);
    }
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

  async function loadCommissionsSummary() {
    setCommissionSummaryLoading(true);
    const response = await fetch("/api/booking/commissions-summary", { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      setCommissionSummary(data);
    } else {
      setCommissionSummary(null);
      const data = await response.json().catch(() => ({}));
      setMessage({ type: "error", text: data.error || "No se pudo cargar la liquidacion de comisiones." });
    }
    setCommissionSummaryLoading(false);
  }

  async function loadCommissionRules(employeeId: string) {
    setCommissionRulesLoading(true);
    const response = await fetch(`/api/booking/commission-rules?employee_id=${encodeURIComponent(employeeId)}`, { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      const rules = (data.rules || []) as StoredCommissionRule[];
      setCommissionRuleDrafts((current) => {
        const prefix = `${employeeId}::`;
        const next = Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(prefix)));
        rules.forEach((rule) => {
          next[commissionRuleKey(employeeId, rule.artist)] = storedCommissionRuleToDraft(rule);
        });
        return next;
      });
      setCommissionDirtyEmployees((current) => ({ ...current, [employeeId]: false }));
    } else {
      const data = await response.json().catch(() => ({}));
      setMessage({ type: "error", text: data.error || "No se pudieron cargar las reglas de comision." });
    }
    setCommissionRulesLoading(false);
  }

  async function saveCommissionRules() {
    if (!commissionsEmployee || !selectedCommissionPermission?.can_access) return;
    if (!canEditModule("booking_commissions")) {
      setMessage({ type: "error", text: "No tenes permiso para editar Comisiones." });
      return;
    }
    if (commissionRulesMissingPriority.length > 0) {
      setMessage({
        type: "error",
        text: `Elegí orden de cobro para: ${commissionRulesMissingPriority.map((rule) => rule.artist).join(", ")}.`,
      });
      return;
    }
    setCommissionRulesSaving(true);
    const payload = {
      employee_id: Number(commissionsEmployee),
      rules: commissionRulesForEmployee.map((rule) => ({
        artist: rule.artist,
        percent: Number(rule.percent || 0),
        base: rule.base,
        include_booking_fee_paid_shows: Boolean(rule.includeBookingFeePaidShows),
        priority_order: rule.priorityOrder || null,
        start_month: rule.startMonth || null,
        end_month: rule.endMonth || null,
        active: Boolean(rule.active),
        notes: rule.notes || null,
      })),
    };
    const response = await fetch("/api/booking/commission-rules", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (response.ok) {
      const data = await response.json();
      const rules = (data.rules || []) as StoredCommissionRule[];
      setCommissionRuleDrafts((current) => {
        const prefix = `${commissionsEmployee}::`;
        const next = Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(prefix)));
        rules.forEach((rule) => {
          next[commissionRuleKey(commissionsEmployee, rule.artist)] = storedCommissionRuleToDraft(rule);
        });
        return next;
      });
      setCommissionDirtyEmployees((current) => ({ ...current, [commissionsEmployee]: false }));
      setMessage({ type: "ok", text: "Reglas de comision guardadas." });
    } else {
      const data = await response.json().catch(() => ({}));
      setMessage({ type: "error", text: data.error || "No se pudieron guardar las reglas de comision." });
    }
    setCommissionRulesSaving(false);
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

  async function loadArtistFinance(artistOverride?: string) {
    setArtistFinanceLoading(true);
    const params = new URLSearchParams();
    const selectedArtist = artistOverride ?? artistFinanceArtist;
    if (selectedArtist) params.set("artist", selectedArtist);
    const response = await fetch(`/api/artist-finance${params.toString() ? `?${params.toString()}` : ""}`, { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      setArtistFinance(data);
      if (!selectedArtist && data.artists?.length === 1) {
        setArtistFinanceArtist(data.artists[0]);
      }
    }
    setArtistFinanceLoading(false);
  }

  async function loadFinanceMovements() {
    setFinanceMovementLoading(true);
    const params = new URLSearchParams();
    if (financeMovementArtistFilter) params.set("artist", financeMovementArtistFilter);
    if (financeMovementProjectFilter) params.set("project", financeMovementProjectFilter);
    if (financeMovementStatusFilter) params.set("status", financeMovementStatusFilter);
    const response = await fetch(`/api/finance/movements${params.toString() ? `?${params.toString()}` : ""}`, { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      setFinanceMovements(data);
    } else {
      const data = await response.json().catch(() => ({}));
      setMessage({ type: "error", text: data.error || "No se pudieron cargar los movimientos financieros." });
    }
    setFinanceMovementLoading(false);
  }

  function updateFinanceMovementField<K extends keyof FinanceMovementForm>(key: K, value: FinanceMovementForm[K]) {
    setFinanceMovementForm((current) => {
      const next = { ...current, [key]: value };
      if (key === "counterparty" && !current.documentCounterparty) {
        next.documentCounterparty = String(value || "");
      }
      if (key === "counterparty") {
        next.accountApplications = [];
      }
      if (key === "category" && value !== "employee_reimbursement") {
        next.accountApplications = [];
      }
      if (key === "category" && value === "employee_reimbursement") {
        next.artist = "";
        next.projectName = "";
        next.concept = next.concept || "Reintegro a empleado";
        next.paidBy = "indyana";
        next.paymentStatus = "pagado";
        next.accountEffect = "sin_impacto";
        next.recoverable = false;
        next.recoverablePercent = "0";
        next.recoveryMethod = "none";
      }
      if (key === "paidBy" && value !== "empleado") {
        next.paidByEmployeeId = "";
      }
      return next;
    });
  }

  function updateFinanceMovementArtist(value: string) {
    const hasArtist = Boolean(value.trim());
    setFinanceMovementProjectMode("existing");
    setFinanceMovementForm((current) => {
      let nextArea = current.businessArea;
      let nextCategory = current.category;
      if (hasArtist && nextArea === "estructura") return current;
      if (!hasArtist && current.movementType === "pago" && nextArea === "booking") {
        nextArea = "";
        nextCategory = "sin_aplicar";
      }
      return {
        ...current,
        artist: value,
        businessArea: nextArea,
        category: nextCategory,
        documentPrimaryArtist: hasArtist && !current.documentPrimaryArtist ? value : current.documentPrimaryArtist,
        documentArtists: hasArtist ? Array.from(new Set([value, ...current.documentArtists.filter(Boolean)])) : current.documentArtists,
      };
    });
    if (hasArtist && financeMovementForm.movementType === "pago") {
      setArtistFinanceArtist(value);
    }
  }

  function updateFinanceMovementType(value: FinanceMovementForm["movementType"]) {
    if (value === "pago") {
      setArtistFinanceBookingMovementOpen(true);
      if (financeMovementForm.artist) setArtistFinanceArtist(financeMovementForm.artist);
    }
    setFinanceMovementForm((current) => {
      const hasArtist = Boolean(current.artist.trim());
      if (value === "pago") {
        const paymentCategories = new Set(["cuenta_booking", "sena_show", "payment_order", "collection_receipt", "employee_reimbursement"]);
        return {
          ...current,
          movementType: value,
          category: paymentCategories.has(current.category) ? current.category : "",
          recoverable: false,
          recoverablePercent: "0",
          recoveryMethod: "none",
          accountEffect: "sin_impacto",
          generateDocumentPdf: false,
          accountApplications: current.category === "employee_reimbursement" ? current.accountApplications : [],
        };
      }
      if (value !== "salario") {
        return {
          ...current,
          movementType: value,
          category: value === current.movementType && current.category !== "cuenta_booking" ? current.category : "",
          generateDocumentPdf: false,
        };
      }
      return {
        ...current,
        movementType: value,
        businessArea: "estructura",
        category: current.category || "salario",
        recoverable: false,
        recoverablePercent: "0",
        recoveryMethod: "none",
        accountEffect: "sin_impacto",
      };
    });
  }

  function updateFinanceMovementArea(value: FinanceMovementForm["businessArea"]) {
    setFinanceMovementProjectMode("existing");
    if (financeMovementForm.movementType === "pago" && value === "booking") {
      setArtistFinanceBookingMovementOpen(true);
      if (financeMovementForm.artist) setArtistFinanceArtist(financeMovementForm.artist);
    }
    setFinanceMovementForm((current) => ({
      ...current,
      businessArea: value,
      artist: value === "estructura" ? "" : current.artist,
      projectName: value === "estructura" ? "" : current.projectName,
      counterparty: value !== "estructura" && current.category === "salario" ? "" : current.counterparty,
      category: current.businessArea === value
        ? current.category
        : "",
    }));
  }

  function setFinanceMovementMultipleConcepts(enabled: boolean) {
    setFinanceMovementForm((current) => {
      if (!enabled) {
        const firstLine = current.conceptLines[0] || newFinanceMovementLine();
        return {
          ...current,
          multipleConcepts: false,
          concept: current.concept || firstLine.concept,
          counterparty: current.counterparty || firstLine.counterparty,
          paidBy: firstLine.paidBy || current.paidBy,
          paidByEmployeeId: firstLine.paidByEmployeeId || current.paidByEmployeeId,
          amount: current.amount || firstLine.amount,
          paidAmount: current.paidAmount || firstLine.paidAmount,
          dueDate: current.dueDate || firstLine.dueDate,
          paymentStatus: current.paymentStatus || firstLine.paymentStatus,
          currency: firstLine.currency || current.currency,
          fxRate: current.fxRate || firstLine.fxRate,
        };
      }
      const seedLine: FinanceMovementLineForm = {
        uid: `${Date.now()}-${Math.random()}`,
        concept: current.concept,
        counterparty: current.counterparty,
        paidBy: current.paidBy,
        paidByEmployeeId: current.paidByEmployeeId,
        amount: current.amount,
        paidAmount: current.paidAmount,
        dueDate: current.dueDate,
        paymentStatus: current.paymentStatus,
        currency: current.currency,
        fxRate: current.fxRate,
      };
      const existingLines = current.conceptLines.length > 0 ? current.conceptLines : [seedLine];
      const hasContent = existingLines.some((line) => (
        line.concept.trim() || line.amount.trim() || line.counterparty.trim()
      ));
      return {
        ...current,
        multipleConcepts: true,
        conceptLines: hasContent ? existingLines : [seedLine],
      };
    });
  }

  function addFinanceMovementLine() {
    setFinanceMovementForm((current) => ({
      ...current,
      conceptLines: [
        ...current.conceptLines,
        {
          ...newFinanceMovementLine(),
          paidBy: current.paidBy,
          paidByEmployeeId: current.paidByEmployeeId,
          currency: current.currency,
          fxRate: current.fxRate,
          paymentStatus: current.paymentStatus,
          dueDate: current.dueDate,
        },
      ],
    }));
  }

  function removeFinanceMovementLine(uid: string) {
    setFinanceMovementForm((current) => ({
      ...current,
      conceptLines: current.conceptLines.length <= 1
        ? current.conceptLines
        : current.conceptLines.filter((line) => line.uid !== uid),
    }));
  }

  function updateFinanceMovementLineField<K extends keyof FinanceMovementLineForm>(
    uid: string,
    key: K,
    value: FinanceMovementLineForm[K],
  ) {
    setFinanceMovementForm((current) => ({
      ...current,
      conceptLines: current.conceptLines.map((line) => (
        line.uid === uid
          ? { ...line, [key]: value, ...(key === "paidBy" && value !== "empleado" ? { paidByEmployeeId: "" } : {}) }
          : line
      )),
    }));
  }

  function setFinanceEconomicDistributionEnabled(enabled: boolean) {
    setFinanceMovementForm((current) => ({
      ...current,
      economicDistributionEnabled: enabled,
      allocationLines: current.allocationLines.length
        ? current.allocationLines.map((line, index) => (
          index === 0 && enabled && !line.amount
            ? { ...line, amount: current.amount, currency: current.currency, fxRate: current.fxRate }
            : line
        ))
        : [newFinanceAllocationLine({
          businessArea: (current.businessArea || "general") as FinanceAllocationForm["businessArea"],
          amount: current.amount,
          currency: current.currency,
          fxRate: current.fxRate,
        })],
    }));
  }

  function addFinanceAllocationLine() {
    setFinanceMovementForm((current) => ({
      ...current,
      allocationLines: [
        ...current.allocationLines,
        newFinanceAllocationLine({
          allocationType: "third_party_receivable",
          targetName: "",
          businessArea: (current.businessArea || "general") as FinanceAllocationForm["businessArea"],
          currency: current.currency,
          fxRate: current.fxRate,
        }),
      ],
    }));
  }

  function selectedFinanceAccountApplicationAmount(entryId: number) {
    const selected = financeMovementForm.accountApplications.find((application) => application.accountEntryId === entryId);
    return selected?.amountArs || "";
  }

  function toggleFinanceAccountApplication(entryId: number, amountArs: number, enabled: boolean) {
    setFinanceMovementForm((current) => {
      const remaining = current.accountApplications.filter((application) => application.accountEntryId !== entryId);
      if (!enabled) {
        return { ...current, accountApplications: remaining };
      }
      return {
        ...current,
        accountApplications: [
          ...remaining,
          { accountEntryId: entryId, amountArs: amountToInput(amountArs) },
        ],
      };
    });
  }

  function updateFinanceAccountApplicationAmount(entryId: number, value: string) {
    setFinanceMovementForm((current) => {
      if (!current.accountApplications.some((application) => application.accountEntryId === entryId)) {
        return {
          ...current,
          accountApplications: [
            ...current.accountApplications,
            { accountEntryId: entryId, amountArs: value },
          ],
        };
      }
      return {
        ...current,
        accountApplications: current.accountApplications.map((application) => (
          application.accountEntryId === entryId
            ? { ...application, amountArs: value }
            : application
        )),
      };
    });
  }

  function removeFinanceAllocationLine(uid: string) {
    setFinanceMovementForm((current) => ({
      ...current,
      allocationLines: current.allocationLines.length <= 1
        ? current.allocationLines
        : current.allocationLines.filter((line) => line.uid !== uid),
    }));
  }

  function updateFinanceAllocationLineField<K extends keyof FinanceAllocationForm>(
    uid: string,
    key: K,
    value: FinanceAllocationForm[K],
  ) {
    setFinanceMovementForm((current) => ({
      ...current,
      allocationLines: current.allocationLines.map((line) => (
        line.uid === uid ? { ...line, [key]: value } : line
      )),
    }));
  }

  function isFinanceMovementLocked(status: string) {
    return ["aprobado", "aplicado", "anulado"].includes(status);
  }

  function editFinanceMovement(item: FinanceMovement) {
    if (isFinanceMovementLocked(item.status)) {
      setMessage({ type: "error", text: "Este movimiento financiero ya esta bloqueado. Para corregirlo, carga un nuevo movimiento." });
      return;
    }
    const normalizedMovementType = item.movement_type === "salario"
      ? "gasto"
      : item.movement_type as FinanceMovementForm["movementType"];
    const normalizedBusinessArea = item.movement_type === "salario"
      ? "estructura"
      : item.business_area as FinanceMovementForm["businessArea"];
    const normalizedCategory = item.movement_type === "salario"
      ? item.category || "salario"
      : item.category;
    setFinanceMovementEditingId(item.id);
    setFinanceMovementProjectMode("existing");
    setFinanceMovementForm({
      movementDate: item.movement_date,
      artist: item.artist,
      businessArea: normalizedBusinessArea,
      movementType: normalizedMovementType,
      category: normalizedCategory,
      projectName: item.project_name || "",
      multipleConcepts: false,
      concept: item.concept,
      counterparty: item.counterparty || "",
      paidBy: item.paid_by as FinanceMovementForm["paidBy"],
      paidByEmployeeId: item.paid_by_employee_id ? String(item.paid_by_employee_id) : "",
      amount: amountToInput(item.amount),
      paidAmount: amountToInput(item.paid_amount),
      dueDate: item.due_date || "",
      paymentStatus: item.payment_status,
      currency: item.currency,
      fxRate: amountToInput(item.fx_rate),
      recoverable: Boolean(item.recoverable),
      recoverablePercent: amountToInput(item.recoverable_percent),
      recoveryMethod: (item.recovery_method || "none") as FinanceMovementForm["recoveryMethod"],
      artistPercent: amountToInput(item.artist_percent),
      producerPercent: amountToInput(item.producer_percent),
      accountEffect: item.account_effect as FinanceMovementForm["accountEffect"],
      status: item.status as FinanceMovementForm["status"],
      sourceType: item.source_type as FinanceMovementForm["sourceType"],
      sourceId: item.source_id || "",
      proofRefs: (item.proof_refs || []).join("\n"),
      notes: item.notes || "",
      conceptLines: [{
        uid: `${Date.now()}-${Math.random()}`,
        concept: item.concept,
        counterparty: item.counterparty || "",
        paidBy: item.paid_by as FinanceMovementForm["paidBy"],
        paidByEmployeeId: item.paid_by_employee_id ? String(item.paid_by_employee_id) : "",
        amount: amountToInput(item.amount),
        paidAmount: amountToInput(item.paid_amount),
        dueDate: item.due_date || "",
        paymentStatus: item.payment_status,
        currency: item.currency,
        fxRate: amountToInput(item.fx_rate),
      }],
      accountApplications: [],
      economicDistributionEnabled: Boolean(item.allocation_lines?.length),
      allocationLines: item.allocation_lines?.length
        ? item.allocation_lines.map((line) => newFinanceAllocationLine({
          allocationType: line.allocation_type,
          targetName: line.target_name,
          businessArea: (line.business_area || normalizedBusinessArea || "estructura") as FinanceAllocationForm["businessArea"],
          amount: amountToInput(line.amount),
          currency: line.currency,
          fxRate: amountToInput(line.fx_rate),
          notes: line.notes || "",
        }))
        : [newFinanceAllocationLine({
          businessArea: normalizedBusinessArea as FinanceAllocationForm["businessArea"],
          amount: amountToInput(item.amount),
          currency: item.currency,
          fxRate: amountToInput(item.fx_rate),
        })],
      generateDocumentPdf: Boolean(item.document_detail),
      documentCounterparty: item.document_detail?.counterparty_name || item.counterparty || "",
      documentIssuerCompany: item.document_detail?.issuer_company || "VPO Corp",
      documentShowDate: item.document_detail?.show_date || "",
      documentVenue: item.document_detail?.venue || "",
      documentPrimaryArtist: item.document_detail?.artist_names?.[0] || item.artist || "",
      documentArtists: item.document_detail?.artist_names?.length ? item.document_detail.artist_names : [item.artist].filter(Boolean),
      documentVatMode: item.document_detail?.vat_mode || "no_aplica",
      documentNotes: item.document_detail?.notes || "",
    });
    setMessage({ type: "ok", text: `Editando movimiento financiero #${item.id}.` });
  }

  function resetFinanceMovementForm() {
    setFinanceMovementEditingId(null);
    setFinanceMovementProjectMode("existing");
    setFinanceMovementForm(initialFinanceMovementForm());
  }

  async function saveFinanceMovement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setFinanceMovementLastReceiptPdf(null);
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const shouldOpenFinancialDocumentPdf = submitter?.value === "save_print_document";

    if (!financeMovementCanSave) {
      setMessage({
        type: "error",
        text: financeMovementEditingId
          ? "No tenes permiso para editar movimientos financieros."
          : "No tenes permiso para cargar movimientos financieros.",
      });
      return;
    }

    if (financeMovementEditingId && financeMovementForm.multipleConcepts) {
      setMessage({ type: "error", text: "Para editar un movimiento existente usa un solo concepto. Para un lote, carga movimientos nuevos." });
      return;
    }
    if (financeMovementEditingId && financeMovementIsEmployeeReimbursementFlow) {
      setMessage({ type: "error", text: "Para corregir un reintegro aplicado, anula o carga un nuevo movimiento de ajuste." });
      return;
    }
    if (financeMovementForm.multipleConcepts && financeMovementForm.economicDistributionEnabled) {
      setMessage({ type: "error", text: "Para usar distribucion economica, carga un solo concepto por movimiento." });
      return;
    }

    const rawLines: FinanceMovementLineForm[] = financeMovementIsEmployeeReimbursementFlow
      ? [{
        uid: "employee-reimbursement",
        concept: financeMovementForm.concept || "Reintegro a empleado",
        counterparty: financeMovementForm.counterparty,
        paidBy: "indyana",
        paidByEmployeeId: "",
        amount: financeMovementForm.amount,
        paidAmount: financeMovementForm.amount,
        dueDate: "",
        paymentStatus: "pagado",
        currency: financeMovementForm.currency,
        fxRate: financeMovementForm.fxRate,
      }]
      : financeMovementIsFinancialDocumentFlow
      ? [{
        uid: "financial-document",
        concept: financeMovementForm.concept || financeMovementDocumentDefaultConcept,
        counterparty: financeMovementForm.documentCounterparty,
        paidBy: financeMovementDocumentType === "collection_receipt" ? "tercero" : "indyana",
        paidByEmployeeId: "",
        amount: financeMovementForm.amount,
        paidAmount: financeMovementForm.amount,
        dueDate: "",
        paymentStatus: "pagado",
        currency: financeMovementForm.currency,
        fxRate: financeMovementForm.fxRate,
      }]
      : financeMovementForm.multipleConcepts
      ? financeMovementForm.conceptLines
      : [{
        uid: "single",
        concept: financeMovementForm.concept,
        counterparty: financeMovementForm.counterparty,
        paidBy: financeMovementForm.paidBy,
        paidByEmployeeId: financeMovementForm.paidByEmployeeId,
        amount: financeMovementForm.amount,
        paidAmount: financeMovementForm.paidAmount,
        dueDate: financeMovementForm.dueDate,
        paymentStatus: financeMovementForm.paymentStatus,
        currency: financeMovementForm.currency,
        fxRate: financeMovementForm.fxRate,
      }];

    const movementLines = rawLines
      .map((line) => {
        const amount = parseMoneyInput(stripUsdPrefix(line.amount));
        const currency = isUsdAmountInput(line.amount) ? "USD" : line.currency;
        const fxRate = parseMoneyInput(line.fxRate);
        const paidAmount = line.paidAmount.trim()
          ? parseMoneyInput(stripUsdPrefix(line.paidAmount))
          : null;
        return {
          ...line,
          concept: line.concept.trim(),
          counterparty: line.counterparty.trim(),
          amount,
          paidAmount,
          currency,
          fxRate,
        };
      })
      .filter((line) => line.concept || line.amount > 0 || line.counterparty);

    if (!financeMovementForm.businessArea) {
      setMessage({ type: "error", text: "Elegi primero el area del movimiento." });
      return;
    }
    if (financeMovementRequiresArtist && !financeMovementIsShowDepositDocumentFlow && !financeMovementForm.artist.trim()) {
      setMessage({ type: "error", text: "Para esta area, elegi el artista desde la lista." });
      return;
    }
    if (financeMovementNeedsEmployee && !financeMovementForm.counterparty.trim()) {
      setMessage({
        type: "error",
        text: financeMovementIsEmployeeReimbursementFlow
          ? "Para reintegrar gastos, elegi el empleado desde el ABM."
          : "Para sueldo o comision interna, elegi el empleado desde el ABM.",
      });
      return;
    }
    if (!financeMovementForm.category) {
      setMessage({ type: "error", text: "Completa la categoria del movimiento." });
      return;
    }
    const financeMovementDocumentCounterpartyValue = financeMovementForm.documentCounterparty.trim() || financeMovementForm.counterparty.trim();
    if (financeMovementUsesDocumentDetail && !financeMovementDocumentCounterpartyValue) {
      setMessage({ type: "error", text: `Completa ${financeMovementDocumentCounterpartyLabel.toLowerCase()}.` });
      return;
    }
    if (financeMovementIsShowDepositDocumentFlow && !financeMovementForm.documentPrimaryArtist.trim()) {
      setMessage({ type: "error", text: "Elegir el artista principal del recibo." });
      return;
    }
    if (movementLines.length === 0) {
      setMessage({
        type: "error",
        text: financeMovementForm.multipleConcepts
          ? "Agrega al menos un concepto con compromiso total."
          : "Completa Concepto y Compromiso total.",
      });
      return;
    }
    const invalidLineIndex = movementLines.findIndex((line) => !line.concept || line.amount <= 0);
    if (invalidLineIndex >= 0) {
      const invalidLine = movementLines[invalidLineIndex];
      const missingConcept = !invalidLine.concept;
      const missingAmount = invalidLine.amount <= 0;
      const missingText = missingConcept && missingAmount
        ? "concepto y compromiso total"
        : missingConcept
          ? "concepto"
          : "compromiso total";
      setMessage({
        type: "error",
        text: financeMovementForm.multipleConcepts
          ? `Completa ${missingText} en la linea ${invalidLineIndex + 1}.`
          : `Completa ${missingText}.`,
      });
      return;
    }
    const missingEmployeePayerIndex = movementLines.findIndex((line) => line.paidBy === "empleado" && !line.paidByEmployeeId);
    if (missingEmployeePayerIndex >= 0) {
      setMessage({ type: "error", text: `Elegí el empleado que pagó en la linea ${missingEmployeePayerIndex + 1}.` });
      return;
    }
    if (financeMovementForm.recoverable && financeMovementForm.recoveryMethod === "none") {
      setMessage({ type: "error", text: "Elegi como se recupera el gasto para que no quede ambiguo." });
      return;
    }
    const missingFxIndex = movementLines.findIndex((line) => line.currency === "USD" && line.fxRate <= 0);
    if (missingFxIndex >= 0) {
      setMessage({ type: "error", text: `Para cargar USD, completa el tipo de cambio en la linea ${missingFxIndex + 1}.` });
      return;
    }
    const accountApplications = financeMovementIsEmployeeReimbursementFlow
      ? financeMovementForm.accountApplications
        .map((application) => ({
          accountEntryId: application.accountEntryId,
          amountArs: parseMoneyInput(application.amountArs),
        }))
        .filter((application) => application.amountArs > 0)
      : [];
    if (financeMovementIsEmployeeReimbursementFlow) {
      if (accountApplications.length === 0) {
        setMessage({ type: "error", text: "Selecciona al menos un reintegro pendiente para aplicar el pago." });
        return;
      }
      const paymentAmountArs = movementLines[0]?.currency === "USD"
        ? movementLines[0].amount * movementLines[0].fxRate
        : movementLines[0]?.amount || 0;
      const applicationTotalArs = accountApplications.reduce((total, application) => total + application.amountArs, 0);
      if (applicationTotalArs - paymentAmountArs > 0.05) {
        setMessage({ type: "error", text: "El total aplicado a reintegros no puede superar el importe pagado." });
        return;
      }
      const pendingById = new Map(financeMovementSelectedEmployeePendingReimbursements.map((item) => [item.id, item]));
      const invalidApplication = accountApplications.find((application) => {
        const pending = pendingById.get(application.accountEntryId);
        return !pending || application.amountArs - (pending.balance_ars || pending.amount_ars || 0) > 0.05;
      });
      if (invalidApplication) {
        setMessage({ type: "error", text: "Hay un importe aplicado mayor al saldo pendiente del reintegro." });
        return;
      }
    }
    const allocationLines = financeMovementForm.economicDistributionEnabled
      ? financeMovementForm.allocationLines
        .map((line) => {
          const amount = parseMoneyInput(stripUsdPrefix(line.amount));
          const currency = isUsdAmountInput(line.amount) ? "USD" : line.currency;
          const fxRate = parseMoneyInput(line.fxRate);
          return {
            ...line,
            targetName: line.targetName.trim(),
            amount,
            currency,
            fxRate,
          };
        })
          .filter((line) => line.targetName || line.amount > 0)
      : [];
    if (financeMovementForm.economicDistributionEnabled) {
      const invalidAllocationIndex = allocationLines.findIndex((line) => !line.targetName || line.amount <= 0);
      if (invalidAllocationIndex >= 0) {
        setMessage({ type: "error", text: `Completa destino e importe en la imputacion ${invalidAllocationIndex + 1}.` });
        return;
      }
      const missingAllocationFxIndex = allocationLines.findIndex((line) => line.currency === "USD" && line.fxRate <= 0);
      if (missingAllocationFxIndex >= 0) {
        setMessage({ type: "error", text: `Para imputaciones en USD, completa el tipo de cambio en la imputacion ${missingAllocationFxIndex + 1}.` });
        return;
      }
      if (Math.abs(financeAllocationDifferenceArs) > 0.05) {
        setMessage({ type: "error", text: "La distribucion economica debe cerrar contra el compromiso total del movimiento." });
        return;
      }
    }

    setFinanceMovementLoading(true);
    let savedCount = 0;
    let savedReceiptPdf: { href: string; label: string } | null = null;
    const movementBusinessArea = financeMovementForm.businessArea as FinanceBusinessArea;
    const movementArtist = financeMovementIsShowDepositDocumentFlow
      ? financeMovementForm.documentPrimaryArtist.trim()
      : financeMovementForm.artist.trim() || "Sin artista asignado";
    for (const line of movementLines) {
      const payload = {
        movement_date: financeMovementForm.movementDate,
        artist: movementArtist,
        business_area: movementBusinessArea,
        movement_type: financeMovementForm.movementType,
        category: financeMovementForm.category,
        project_name: financeMovementForm.projectName || null,
        concept: line.concept,
        counterparty: line.counterparty || null,
        paid_by: line.paidBy,
        paid_by_employee_id: line.paidBy === "empleado" ? Number(line.paidByEmployeeId) : null,
        amount: line.amount,
        paid_amount: line.paidAmount,
        due_date: line.dueDate || null,
        payment_status: line.paymentStatus || null,
        currency: line.currency,
        fx_rate: line.currency === "USD" ? line.fxRate : null,
        recoverable: financeMovementForm.recoverable,
        recoverable_percent: parseMoneyInput(financeMovementForm.recoverablePercent),
        recovery_method: financeMovementForm.recoverable ? financeMovementForm.recoveryMethod : "none",
        artist_percent: parseMoneyInput(financeMovementForm.artistPercent),
        producer_percent: parseMoneyInput(financeMovementForm.producerPercent),
        account_effect: financeMovementForm.accountEffect,
        status: financeMovementForm.status,
        source_type: financeMovementForm.sourceType,
        source_id: financeMovementForm.sourceId || null,
        proof_refs: financeMovementForm.proofRefs.split(/\r?\n/).map((proofLine) => proofLine.trim()).filter(Boolean),
        notes: financeMovementForm.notes || null,
        allocation_lines: allocationLines.map((allocation) => ({
          allocation_type: allocation.allocationType,
          target_name: allocation.targetName,
          business_area: allocation.businessArea || movementBusinessArea,
          amount: allocation.amount,
          currency: allocation.currency,
          fx_rate: allocation.currency === "USD" ? allocation.fxRate : null,
          notes: allocation.notes || null,
        })),
        account_applications: financeMovementIsEmployeeReimbursementFlow ? accountApplications.map((application) => ({
          account_entry_id: application.accountEntryId,
          amount_ars: application.amountArs,
        })) : [],
        document_detail: financeMovementUsesDocumentDetail ? {
          document_type: financeMovementDocumentType,
          issuer_company: financeMovementForm.documentIssuerCompany,
          counterparty_name: financeMovementDocumentCounterpartyValue,
          show_date: financeMovementIsShowDepositDocumentFlow ? financeMovementForm.documentShowDate || null : null,
          venue: financeMovementIsShowDepositDocumentFlow ? financeMovementForm.documentVenue || null : null,
          artist_names: Array.from(new Set([
            movementArtist,
            ...financeMovementForm.documentArtists,
          ].map((artist) => artist.trim()).filter(Boolean))),
          booking_show_id: null,
          vat_mode: financeMovementForm.documentVatMode,
          notes: financeMovementForm.documentNotes || null,
        } : null,
      };

      const url = financeMovementEditingId
        ? `/api/finance/movements?id=${financeMovementEditingId}`
        : "/api/finance/movements";
      const response = await fetch(url, {
        method: financeMovementEditingId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setFinanceMovementLoading(false);
        setMessage({ type: "error", text: data.error || `No se pudo guardar la linea ${savedCount + 1}.` });
        return;
      }
      if (financeMovementUsesDocumentDetail && data.item?.document_detail?.id) {
        const documentNumber = String(data.item.document_detail.document_number || "").padStart(6, "0");
        savedReceiptPdf = {
          href: `/api/finance/documents/${data.item.document_detail.id}/pdf`,
          label: `${financeMovementDocumentTitle} #${documentNumber}`,
        };
      }
      savedCount += 1;
    }

    setFinanceMovementLoading(false);
    if (savedReceiptPdf) {
      setFinanceMovementLastReceiptPdf(savedReceiptPdf);
      if (shouldOpenFinancialDocumentPdf) {
        window.open(savedReceiptPdf.href, "_blank", "noopener,noreferrer");
      }
    }
    setMessage({
      type: "ok",
      text: savedReceiptPdf
        ? `${savedReceiptPdf.label} guardado.`
        : financeMovementEditingId
        ? "Movimiento financiero actualizado."
        : savedCount === 1
          ? "Movimiento financiero cargado en staging."
          : `${savedCount} movimientos financieros cargados en staging para el mismo proyecto.`,
    });
    resetFinanceMovementForm();
    loadFinanceMovements();
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

  async function loadEmployeeRecords() {
    const response = await fetch("/api/employees", { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    setEmployeeRecords(data.items || []);
    setEmployeeFunctionOptions(data.function_options || []);
    setEmployeeModules(data.modules || []);
    if (!employeeEditingId) {
      const modules = (data.modules || []) as EmployeeModule[];
      setEmployeeForm((current) => current.permissions.length ? current : {
        ...current,
        permissions: modules
          .filter((module) => module.module_key !== "home")
          .map(defaultEmployeePermission),
      });
    }
  }

  async function loadFinanceEmployeeOptions() {
    setFinanceEmployeeOptionsLoading(true);
    const response = await fetch("/api/employees/finance-options", { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      setFinanceEmployeeOptions(data.items || []);
    } else {
      setFinanceEmployeeOptions([]);
    }
    setFinanceEmployeeOptionsLoading(false);
  }

  async function loadCommissionEmployeeRecords() {
    setCommissionEmployeesLoading(true);
    const response = await fetch("/api/employees/commission-options", { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      setCommissionEmployeeRecords(data.items || []);
    } else {
      const data = await response.json().catch(() => ({}));
      setCommissionEmployeeRecords([]);
      setMessage({ type: "error", text: data.error || "No se pudieron cargar los empleados para comisiones." });
    }
    setCommissionEmployeesLoading(false);
  }

  async function loadCurrentUserPermissions() {
    if (!currentUser) {
      setCurrentUserModuleAccess(null);
      setCurrentUserPermissions(null);
      return;
    }
    if (currentUser.role === "admin") {
      setCurrentUserModuleAccess(["*"]);
      setCurrentUserPermissions(null);
      return;
    }

    const response = await fetch("/api/me/permissions", { cache: "no-store" });
    if (!response.ok) {
      setCurrentUserModuleAccess([]);
      setCurrentUserPermissions([]);
      return;
    }
    const data = await response.json();
    const permissions = (data.permissions || []) as EmployeePermission[];
    const access = permissions
      .filter((permission) => permission.can_access)
      .map((permission) => permission.module_key)
      .filter((moduleKey) => moduleKey !== "home");

    setCurrentUserPermissions(permissions);
    setCurrentUserModuleAccess(access);
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

  async function loadBookingAgendaCandidates() {
    setBookingAgendaCandidatesLoading(true);
    const response = await fetch("/api/booking/events?limit=1000", { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      const today = new Date();
      const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
      const items = ((data.items || []) as BookingAgendaEvent[])
        .filter((item) => item.event_type === "show")
        .filter((item) => item.event_date <= todayKey)
        .filter((item) => item.commercial_status !== "cancelado")
        .filter((item) => !item.booking_show_id && !item.composite_event_id && !item.caserio_event_id)
        .sort((left, right) => right.event_date.localeCompare(left.event_date) || right.id - left.id);
      setBookingAgendaCandidates(items);
      setBookingAgendaCandidateId((current) => items.some((item) => String(item.id) === current) ? current : "");
    }
    setBookingAgendaCandidatesLoading(false);
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
    setCompositeBookingAgendaEventId(null);
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
        "Creado desde Booking compartido como show simple, sin evento madre.",
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
          booking_event_id: compositeBookingAgendaEventId,
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
      loadBookingAgendaCandidates();
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
        booking_event_id: compositeBookingAgendaEventId,
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
    loadBookingAgendaCandidates();
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

  function defaultEmployeePermissions() {
    return employeeModules
      .filter((module) => module.module_key !== "home")
      .map(defaultEmployeePermission);
  }

  function defaultEmployeePermission(module: EmployeeModule): EmployeePermission {
    const agendaView = module.module_key === "booking_agenda";
    return {
      module_key: module.module_key,
      can_access: agendaView,
      can_create: false,
      can_view_history: agendaView,
      can_edit: false,
      can_approve: false,
      scope: agendaView ? [{ scope_type: "all", scope_ref: "*" }] : [],
      notes: agendaView ? "Acceso inicial de lectura a la Agenda Booking." : null,
    };
  }

  function mergedEmployeePermissions(item?: EmployeeRecord) {
    const existing = new Map((item?.permissions || []).map((permission) => [permission.module_key, permission]));
    return employeeModules
      .filter((module) => module.module_key !== "home")
      .map((module) => existing.get(module.module_key) || defaultEmployeePermission(module));
  }

  function updateEmployeeField<K extends keyof EmployeeForm>(key: K, value: EmployeeForm[K]) {
    setEmployeeForm((current) => ({ ...current, [key]: value }));
  }

  function employeePermissionLevel(permission: EmployeePermission) {
    if (permission.can_approve && permission.can_edit && permission.can_create && permission.can_view_history && permission.can_access) return "admin";
    if (permission.can_edit) return "edit";
    if (permission.can_create) return "create";
    if (permission.can_access || permission.can_view_history) return "view";
    return "none";
  }

  function permissionUsesArtistScope(permission: EmployeePermission) {
    return ARTIST_SCOPED_MODULES.has(permission.module_key);
  }

  function permissionHasAllArtists(permission: EmployeePermission) {
    if (!permission.scope || permission.scope.length === 0) return true;
    return permission.scope.some((item) => item.scope_type === "all" && item.scope_ref === "*");
  }

  function permissionArtistNames(permission: EmployeePermission) {
    if (permissionHasAllArtists(permission)) return [];
    return (permission.scope || [])
      .filter((item) => item.scope_type === "artist" && item.scope_ref)
      .map((item) => item.scope_ref);
  }

  function artistScopeKey(value: string) {
    return String(value || "")
      .trim()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  function normalizeEmployeePermissionForSave(permission: EmployeePermission) {
    if (!permission.can_access || !permissionUsesArtistScope(permission)) {
      return permission;
    }
    if (permissionHasAllArtists(permission)) {
      return { ...permission, scope: [{ scope_type: "all", scope_ref: "*" }] };
    }
    const artists = permissionArtistNames(permission);
    if (artists.length === 0) {
      return { ...permission, scope: [{ scope_type: "none", scope_ref: "*" }] };
    }
    return permission;
  }

  function updateEmployeePermissionLevel(moduleKey: string, level: string) {
    const values = {
      can_access: level !== "none",
      can_create: ["create", "edit", "admin"].includes(level),
      can_view_history: ["view", "edit", "admin"].includes(level) || (moduleKey === "booking_agenda" && level === "create"),
      can_edit: ["edit", "admin"].includes(level),
      can_approve: level === "admin",
    };
    setEmployeeForm((current) => {
      const basePermissions = current.permissions.length ? current.permissions : defaultEmployeePermissions();
      return {
        ...current,
        permissions: basePermissions
          .map((permission) => (
            permission.module_key === moduleKey
              ? { ...permission, ...values }
              : permission
          ))
          .map((permission) => (
            permission.module_key === moduleKey && permission.can_access && permissionUsesArtistScope(permission) && (!permission.scope || permission.scope.length === 0)
              ? { ...permission, scope: [{ scope_type: "all", scope_ref: "*" }] }
              : permission
          )),
      };
    });
  }

  function updateEmployeePermissionArtistMode(moduleKey: string, mode: "all" | "selected") {
    setEmployeeForm((current) => {
      const basePermissions = current.permissions.length ? current.permissions : defaultEmployeePermissions();
      return {
        ...current,
        permissions: basePermissions.map((permission) => {
          if (permission.module_key !== moduleKey) return permission;
          return {
            ...permission,
            scope: mode === "all" ? [{ scope_type: "all", scope_ref: "*" }] : [{ scope_type: "none", scope_ref: "*" }],
          };
        }),
      };
    });
  }

  function toggleEmployeePermissionArtist(moduleKey: string, artist: string) {
    setEmployeeForm((current) => {
      const basePermissions = current.permissions.length ? current.permissions : defaultEmployeePermissions();
      return {
        ...current,
        permissions: basePermissions.map((permission) => {
          if (permission.module_key !== moduleKey) return permission;
          const currentArtists = new Set(permissionArtistNames(permission));
          if (currentArtists.has(artist)) {
            currentArtists.delete(artist);
          } else {
            currentArtists.add(artist);
          }
          return {
            ...permission,
            scope: currentArtists.size === 0
              ? [{ scope_type: "none", scope_ref: "*" }]
              : Array.from(currentArtists)
                .sort((a, b) => a.localeCompare(b))
                .map((scope_ref) => ({ scope_type: "artist", scope_ref })),
          };
        }),
      };
    });
  }

  function toggleEmployeeFunction(functionName: string) {
    setEmployeeForm((current) => {
      const exists = current.functions.includes(functionName);
      return {
        ...current,
        functions: exists
          ? current.functions.filter((item) => item !== functionName)
          : [...current.functions, functionName],
      };
    });
  }

  function resetEmployeeForm() {
    setEmployeeEditingId(null);
    setEmployeeForm({
      displayName: "",
      legalName: "",
      cuit: "",
      phone: "",
      email: "",
      address: "",
      functions: [],
      compensationType: "none",
      salaryAmount: "",
      salaryCurrency: "ARS",
      salaryFrequency: "monthly",
      salaryNotes: "",
      username: "",
      newPassword: "",
      mustChangePassword: true,
      userRole: "viewer",
      userActive: true,
      permissions: defaultEmployeePermissions(),
      notes: "",
      active: true,
    });
  }

  function editEmployeeRecord(item: EmployeeRecord) {
    const primaryUser = item.users?.[0];
    setEmployeeEditingId(item.id);
    setEmployeeForm({
      displayName: item.display_name,
      legalName: item.legal_name || "",
      cuit: item.cuit || "",
      phone: item.phone || "",
      email: item.email || "",
      address: item.address || "",
      functions: item.functions || [],
      compensationType: item.compensation_type || "none",
      salaryAmount: amountToInput(item.salary_amount || 0),
      salaryCurrency: item.salary_currency || "ARS",
      salaryFrequency: item.salary_frequency || "monthly",
      salaryNotes: item.salary_notes || "",
      username: primaryUser?.username || "",
      newPassword: "",
      mustChangePassword: primaryUser?.must_change_password ?? true,
      userRole: primaryUser?.global_role || "viewer",
      userActive: primaryUser?.active ?? true,
      permissions: mergedEmployeePermissions(item),
      notes: item.notes || "",
      active: item.active,
    });
  }

  async function submitEmployeeRecord(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setEmployeeLoading(true);
    setMessage(null);

    const response = await fetch(
      employeeEditingId ? `/api/employees?id=${employeeEditingId}` : "/api/employees",
      {
        method: employeeEditingId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: employeeForm.displayName,
          legal_name: employeeForm.displayName || null,
          cuit: employeeForm.cuit || null,
          phone: employeeForm.phone || null,
          email: employeeForm.email || null,
          address: employeeForm.address || null,
          functions: employeeForm.functions,
          compensation_type: employeeForm.compensationType,
          salary_amount: parseMoneyInput(employeeForm.salaryAmount),
          salary_currency: employeeForm.salaryCurrency,
          salary_frequency: employeeForm.salaryFrequency,
          salary_notes: employeeForm.salaryNotes || null,
          username: employeeForm.username || null,
          password: employeeForm.newPassword || null,
          must_change_password: employeeForm.newPassword ? employeeForm.mustChangePassword : null,
          user_role: employeeForm.userRole,
          user_active: employeeForm.userActive,
          permissions: employeeForm.permissions
            .filter((permission) => permission.module_key !== "home")
            .map(normalizeEmployeePermissionForSave),
          notes: employeeForm.notes || null,
          active: employeeForm.active,
        }),
      },
    );

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo guardar el empleado." }));
      setMessage({ type: "error", text: data.error || "No se pudo guardar el empleado." });
      setEmployeeLoading(false);
      return;
    }

    const data = await response.json();
    const item = data.item as EmployeeRecord;
    setEmployeeRecords((current) => {
      if (employeeEditingId) {
        return current.map((record) => (record.id === item.id ? item : record));
      }
      return [item, ...current];
    });
    resetEmployeeForm();
    setMessage({ type: "ok", text: employeeEditingId ? "Empleado actualizado correctamente." : "Empleado creado correctamente." });
    setEmployeeLoading(false);
  }

  async function deactivateEmployeeRecord(item: EmployeeRecord) {
    setEmployeeLoading(true);
    setMessage(null);
    const response = await fetch(`/api/employees?id=${item.id}`, { method: "DELETE" });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo desactivar el empleado." }));
      setMessage({ type: "error", text: data.error || "No se pudo desactivar el empleado." });
      setEmployeeLoading(false);
      return;
    }

    const data = await response.json();
    const updated = data.item as EmployeeRecord;
    setEmployeeRecords((current) => current.map((record) => (record.id === updated.id ? updated : record)));
    if (employeeEditingId === updated.id) resetEmployeeForm();
    setMessage({ type: "ok", text: "Empleado desactivado. Sigue guardado para historial y auditoria." });
    setEmployeeLoading(false);
  }

  async function resetEmployeePassword(item: EmployeeRecord) {
    setEmployeeLoading(true);
    setMessage(null);
    const response = await fetch(`/api/employees?id=${item.id}&action=password`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        use_default: true,
        must_change_password: true,
      }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo establecer la contrasena." }));
      setMessage({ type: "error", text: data.error || "No se pudo establecer la contrasena." });
      setEmployeeLoading(false);
      return;
    }

    const data = await response.json();
    const updated = data.item as EmployeeRecord;
    setEmployeeRecords((current) => current.map((record) => (record.id === updated.id ? updated : record)));
    if (employeeEditingId === updated.id) editEmployeeRecord(updated);
    setMessage({ type: "ok", text: `Contrasena default establecida para ${item.display_name}.` });
    setEmployeeLoading(false);
  }

  function resetBookingForm() {
    setBookingEditingId(null);
    setBookingAgendaEventId(null);
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
      venueShortfallPolicy: "deuda_boliche",
      venuePaymentNotes: "",
      showExpenses: [],
      cashMovements: [],
      preSplitAdjustments: [],
      directCommissions: [],
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
    if (!canEditModule("booking")) {
      setMessage({ type: "error", text: "No tenes permiso para editar shows de Booking Indyana." });
      return;
    }
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
      venueShortfallPolicy: item.venue_shortfall_policy || "deuda_boliche",
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
        recoveryAutoApply: Boolean(adjustment.recovery_auto_apply),
        notes: adjustment.notes || "",
      })),
      directCommissions: (item.direct_commissions || []).map((commission) => ({
        uid: `direct-commission-${commission.id}-${Date.now()}`,
        concept: commission.concept || "",
        recipient: commission.recipient || "",
        destination: commission.destination || "salida_directa",
        amount: amountToInput(commission.amount),
        notes: commission.notes || "",
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
      artistPercent: amountToInput(item.artist_percent),
      producerPercent: amountToInput(item.producer_percent),
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
        artistPercent: amountToInput(adjustment.artist_percent),
        producerPercent: amountToInput(adjustment.producer_percent),
        notes: adjustment.notes || "",
      })),
      receiptRefs: item.receipt_refs.join("\n"),
      notes: item.notes || "",
    });
    setMessage({ type: "ok", text: `Editando show #${item.id}. Guardar actualiza la carga existente.` });
  }

  function openBookingAccountApplication(item: BookingShow) {
    if (!canEditModule("booking")) {
      setMessage({ type: "error", text: "No tenes permiso para aplicar saldos de Booking." });
      return;
    }
    const target = bookingDefaultAccountTarget(item);
    setBookingAccountShowId(item.id);
    setBookingAccountForm({
      ...initialBookingAccountApplicationForm(),
      targetBalance: target,
      applicationType: bookingSuggestedApplicationType(item, target),
      amount: amountToInput(Math.abs(bookingOpenTargetBalance(item, target))),
      counterparty: target === "venue" ? item.venue : item.artist,
      notes: "",
    });
  }

  function updateBookingAccountField<K extends keyof BookingAccountApplicationForm>(key: K, value: BookingAccountApplicationForm[K]) {
    setBookingAccountForm((current) => ({ ...current, [key]: value }));
  }

  function updateBookingAccountTarget(item: BookingShow, target: BookingAccountTarget) {
    setBookingAccountForm((current) => ({
      ...current,
      targetBalance: target,
      applicationType: bookingSuggestedApplicationType(item, target),
      amount: amountToInput(Math.abs(bookingOpenTargetBalance(item, target))),
      counterparty: target === "venue" ? item.venue : item.artist,
    }));
  }

  async function submitBookingAccountApplication(item: BookingShow) {
    if (!canEditModule("booking")) {
      setMessage({ type: "error", text: "No tenes permiso para aplicar saldos de Booking." });
      return;
    }
    const amount = parseMoneyInput(bookingAccountForm.amount);
    if (amount <= 0) {
      setMessage({ type: "error", text: "CargÃ¡ un importe para aplicar al saldo." });
      return;
    }
    setBookingLoading(true);
    setMessage(null);
    const proofRefs = bookingAccountForm.proofRefs
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const response = await fetch(`/api/booking/${item.id}/account`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        application_date: bookingAccountForm.applicationDate,
        target_balance: bookingAccountForm.targetBalance,
        application_type: bookingAccountForm.applicationType,
        amount,
        payment_method: bookingAccountForm.paymentMethod,
        counterparty: bookingAccountForm.counterparty.trim() || null,
        linked_show_id: bookingAccountForm.linkedShowId ? Number(bookingAccountForm.linkedShowId) : null,
        proof_refs: proofRefs,
        notes: bookingAccountForm.notes || null,
      }),
    });
    setBookingLoading(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ error: "No se pudo aplicar el saldo." }));
      setMessage({ type: "error", text: payload.error || "No se pudo aplicar el saldo." });
      return;
    }
    const data = await response.json();
    setBookingItems((current) => current.map((show) => {
      if (show.id === data.item.id) return data.item;
      if (data.linked_item && show.id === data.linked_item.id) return data.linked_item;
      return show;
    }));
    setBookingAccountShowId(null);
    setBookingAccountForm(initialBookingAccountApplicationForm());
    setMessage({ type: "ok", text: `Saldo aplicado en show #${item.id}.` });
  }

  async function submitBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    if (bookingEditingId ? !canEditModule("booking") : !canCreateModule("booking")) {
      setMessage({ type: "error", text: bookingEditingId ? "No tenes permiso para editar shows." : "No tenes permiso para cargar shows." });
      return;
    }
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
        booking_event_id: bookingEditingId ? null : bookingAgendaEventId,
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
        venue_shortfall_policy: bookingForm.venuePaymentIssue ? bookingForm.venueShortfallPolicy : "deuda_boliche",
        venue_payment_notes: bookingForm.venuePaymentIssue ? bookingForm.venuePaymentNotes || null : null,
        cachet_amount: bookingForm.venuePaymentIssue && bookingForm.venueShortfallPolicy === "ajustar_cachet" ? venueCollected : contractedCachet,
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
        direct_commissions: bookingForm.directCommissions
          .map((commission) => ({
            concept: commission.concept.trim() || "Comision directa",
            recipient: commission.recipient.trim() || null,
            destination: commission.destination,
            amount: parseAmountInput(commission.amount, bookingFxRate),
            notes: commission.notes || null,
          }))
          .filter((commission) => commission.amount > 0),
        pre_split_adjustments: bookingForm.preSplitAdjustments
          .map((adjustment) => ({
            concept: adjustment.concept.trim(),
            destination: adjustment.destination,
            amount: parseAmountInput(adjustment.amount, bookingFxRate),
            recovery_auto_apply: adjustment.destination === "producer" && adjustment.recoveryAutoApply,
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
    loadBookingAgendaCandidates();
    setMessage({ type: "ok", text: bookingEditingId ? "Show actualizado correctamente." : "Show cargado correctamente." });
    setBookingLoading(false);
  }

  async function deleteBookingShow(item: BookingShow) {
    if (!canApproveModule("booking")) {
      setMessage({ type: "error", text: "No tenes permiso para eliminar shows." });
      return;
    }
    const confirmed = window.confirm(`Eliminar show #${item.id} - ${item.artist} / ${item.venue}?`);
    if (!confirmed) return;
    setBookingLoading(true);
    setMessage(null);
    const response = await fetch(`/api/booking?id=${item.id}`, { method: "DELETE" });
    setBookingLoading(false);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ error: "No se pudo eliminar el show." }));
      setMessage({ type: "error", text: payload.error || "No se pudo eliminar el show." });
      return;
    }
    if (bookingEditingId === item.id) resetBookingForm();
    setBookingItems((current) => current.filter((show) => show.id !== item.id));
    setMessage({ type: "ok", text: `Show #${item.id} eliminado.` });
  }

  function submitRoyalties(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (royaltyReportOutput === "executive_pdf") {
      generateExecutivePdf();
      return;
    }
    generateExcel();
  }

  function openView(nextView: View) {
    setView(nextView);
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");
  }

  function openBookingWorkspace() {
    setBookingWorkspaceMode(canAccessBookingMode("individual") ? "individual" : "shared");
    setBookingSurface("dashboard");
    openView("booking");
  }

  function openBookingSettlements(mode: BookingWorkspaceMode) {
    if (!canAccessBookingMode(mode)) return;
    setBookingWorkspaceMode(mode);
    setBookingSurface("settlement");
    setMessage(null);
  }

  async function openLinkedAgendaSettlement(item: BookingAgendaEvent) {
    if (item.caserio_event_id) {
      openView("caserio");
      setMessage({ type: "ok", text: `Evento Caserio #${item.caserio_event_id} vinculado desde Agenda.` });
      return;
    }

    if (item.booking_mode === "individual" && item.booking_show_id) {
      openBookingSettlements("individual");
      setBookingLoading(true);
      const response = await fetch(`/api/booking/${item.booking_show_id}`, { cache: "no-store" });
      const data = await response.json().catch(() => ({}));
      setBookingLoading(false);
      if (!response.ok) {
        setMessage({ type: "error", text: data.error || "No se pudo abrir la liquidación vinculada." });
        return;
      }
      const show = data.item as BookingShow;
      setBookingItems((current) => current.some((entry) => entry.id === show.id)
        ? current.map((entry) => entry.id === show.id ? show : entry)
        : [show, ...current]);
      if (canEditModule("booking")) {
        editBookingShow(show);
      } else {
        setBookingSearch(String(show.id));
        setMessage({ type: "ok", text: `Liquidación #${show.id} abierta en modo consulta.` });
      }
      return;
    }

    if (item.booking_mode === "shared" && item.composite_event_id) {
      openBookingSettlements("shared");
      setCompositeBookingLoading(true);
      const response = await fetch(`/api/booking/composite-events/${item.composite_event_id}`, { cache: "no-store" });
      const data = await response.json().catch(() => ({}));
      setCompositeBookingLoading(false);
      if (!response.ok) {
        setMessage({ type: "error", text: data.error || "No se pudo abrir la liquidación compartida vinculada." });
        return;
      }
      const composite = data.item as BookingCompositeEvent;
      setCompositeBookingEvents((current) => current.some((entry) => entry.id === composite.id)
        ? current.map((entry) => entry.id === composite.id ? composite : entry)
        : [composite, ...current]);
      if (canEditModule("composite_booking")) {
        editCompositeBookingEvent(composite);
      } else {
        setMessage({ type: "ok", text: `Liquidación compartida #${composite.id} abierta en modo consulta.` });
      }
      return;
    }

    setMessage({ type: "error", text: "La entrada figura vinculada, pero no tiene una liquidación identificable." });
  }

  function startAgendaSettlement(item: BookingAgendaEvent) {
    const sameCurrencyDeposits = (item.deposits || []).filter((deposit) => deposit.currency === item.currency);
    const unassignedDeposits = sameCurrencyDeposits.filter((deposit) => !["indyana", "artista"].includes(deposit.received_by));
    if (item.booking_mode === "individual") {
      if (!canAccessBookingMode("individual")) return;
      const artist = item.artists[0]?.artist || "";
      setBookingEditingId(null);
      setBookingAgendaEventId(item.id);
      setBookingForm({
        artist,
        showDate: item.event_date,
        venue: item.venue,
        city: item.city || "",
        tourManager: item.tour_manager || "",
        seller: item.seller || "",
        status: item.operational_status === "realizado" ? "realizado" : "pendiente",
        currency: item.currency,
        fxRate: item.fx_rate ? amountToInput(item.fx_rate) : "",
        cachetAmount: amountToInput(item.contracted_cachet_amount),
        venuePaymentIssue: false,
        venueCollectedAmount: amountToInput(item.contracted_cachet_amount),
        venueShortfallPolicy: "deuda_boliche",
        venuePaymentNotes: "",
        showExpenses: [],
        cashMovements: sameCurrencyDeposits
          .filter((deposit) => deposit.received_by === "indyana" || deposit.received_by === "artista")
          .map((deposit) => ({
            uid: `agenda-deposit-${deposit.id}-${Date.now()}`,
            recipient: deposit.received_by === "artista" ? "artist" : "producer",
            concept: "Seña registrada en Agenda",
            amount: amountToInput(deposit.amount),
            paymentMethod: deposit.payment_method,
            paidBy: deposit.counterparty || "",
            notes: `Agenda #${item.id}${deposit.notes ? ` · ${deposit.notes}` : ""}`,
          })),
        preSplitAdjustments: [],
        directCommissions: [],
        externalShares: [],
        artistPaidAmount: "",
        producerReceivedAmount: "",
        artistPercent: "70",
        producerPercent: "30",
        bookingCommissionExempt: false,
        bookingCommissionNotes: "",
        artistAdjustments: [],
        receiptRefs: sameCurrencyDeposits.flatMap((deposit) => deposit.proof_refs || []).join("\n"),
        notes: [
          `Precarga de Agenda #${item.id}.`,
          item.notes || "",
          unassignedDeposits.length ? `${unassignedDeposits.length} seña(s) requieren asignar su efecto económico al liquidar.` : "",
        ].filter(Boolean).join("\n"),
      });
      openBookingSettlements("individual");
      return;
    }

    if (!canAccessBookingMode("shared")) return;
    const receivedByIndyana = sameCurrencyDeposits
      .filter((deposit) => deposit.received_by === "indyana")
      .reduce((total, deposit) => total + deposit.amount, 0);
    setCompositeBookingEditingId(null);
    setCompositeBookingAgendaEventId(item.id);
    setCompositeBookingForm({
      eventDate: item.event_date,
      venue: item.venue,
      city: item.city || "",
      responsible: item.tour_manager || "",
      grossAmount: amountToInput(item.contracted_cachet_amount),
      currency: item.currency,
      fxRate: item.fx_rate ? amountToInput(item.fx_rate) : "",
      status: "borrador",
      receivedAmount: receivedByIndyana ? amountToInput(receivedByIndyana) : "",
      receiptRefs: sameCurrencyDeposits.flatMap((deposit) => deposit.proof_refs || []).join("\n"),
      notes: [`Precarga de Agenda #${item.id}.`, item.notes || ""].filter(Boolean).join("\n"),
      expenses: [],
      lines: item.artists.map((artist) => ({
        ...newCompositeBookingLine("artista_vpo"),
        description: `${artist.artist} - ${item.venue}`,
        artist: artist.artist,
      })),
    });
    openBookingSettlements("shared");
  }

  function renderBookingAgendaPrefill(mode: BookingWorkspaceMode) {
    const candidates = bookingAgendaCandidates.filter((item) => item.booking_mode === mode);
    const selected = candidates.find((item) => String(item.id) === bookingAgendaCandidateId);
    return (
      <div className="booking-agenda-prefill">
        <div>
          <strong>Continuar un show de Agenda</strong>
          <small>{bookingAgendaCandidatesLoading ? "Buscando shows pendientes..." : `${candidates.length} show${candidates.length === 1 ? "" : "s"} sin liquidar`}</small>
        </div>
        <select
          aria-label="Show pendiente de Agenda"
          value={bookingAgendaCandidateId}
          onChange={(event) => setBookingAgendaCandidateId(event.target.value)}
          disabled={bookingAgendaCandidatesLoading || candidates.length === 0}
        >
          <option value="">Elegir show pendiente</option>
          {candidates.map((item) => (
            <option key={item.id} value={item.id}>
              {item.event_date} · {item.artists.map((artist) => artist.artist).join(" + ")} · {item.venue}
            </option>
          ))}
        </select>
        <button type="button" onClick={() => selected && startAgendaSettlement(selected)} disabled={!selected}>
          Usar precarga
        </button>
      </div>
    );
  }

  function selectBookingMode(mode: BookingWorkspaceMode) {
    if (!canAccessBookingMode(mode)) return;
    setBookingWorkspaceMode(mode);
    setMessage(null);
  }

  if (checkingSession) {
    return (
      <div className="login">
        <section className="panel">
          <div className="login-brand">
            <Image className="login-logo" src="/vpo-logo.png" alt="VPO Corp" width={2539} height={1298} priority />
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
            <Image className="login-logo" src="/vpo-logo.png" alt="VPO Corp" width={2539} height={1298} priority />
          </div>
          <p className="login-copy">Centro de control · acceso interno</p>
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

  if (currentUser?.mustChangePassword) {
    return (
      <div className="login">
        <form className="panel" onSubmit={changeOwnPassword}>
          <div className="login-brand">
            <Image className="login-logo" src="/vpo-logo.png" alt="VPO Corp" width={2539} height={1298} priority />
          </div>
          <p className="login-copy">Tenes que cambiar la contrasena default antes de ingresar.</p>
          {message && <div className={`message ${message.type === "error" ? "error" : ""}`}>{message.text}</div>}
          <label htmlFor="current_password">Contrasena actual</label>
          <input
            id="current_password"
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
          <label htmlFor="new_password">Nueva contrasena</label>
          <input
            id="new_password"
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
          <label htmlFor="new_password_confirm">Confirmar nueva contrasena</label>
          <input
            id="new_password_confirm"
            type="password"
            value={newPasswordConfirm}
            onChange={(event) => setNewPasswordConfirm(event.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
          <button type="submit" disabled={loading}>{loading ? "Guardando..." : "Cambiar contrasena"}</button>
          <button type="button" onClick={logout}>Salir</button>
        </form>
      </div>
    );
  }

  const sourceMonitorPendingTotal = (sourceMonitor?.items || []).reduce((sum, item) => sum + item.unprocessed_raw_count, 0);
  const sourceMonitorIgnoredTotal = (sourceMonitor?.items || []).reduce((sum, item) => sum + (item.ignored_raw_count || 0), 0);
  const sourceMonitorRawTotal = (sourceMonitor?.items || []).reduce((sum, item) => sum + item.raw_files, 0);
  const sourceMonitorLoadedTotal = (sourceMonitor?.items || []).reduce((sum, item) => sum + item.files_in_mart, 0);
  const canPublishMarts = Boolean(currentUser?.canEdit)
    && sourceMonitorPendingTotal === 0
    && !sourceMonitorPublishing
    && !sourceMonitorProcessingId
    && !sourceMonitorLoading;
  const publishDisabledReason = !currentUser?.canEdit
    ? "Necesitas entrar con usuario editor/admin."
    : sourceMonitorLoading
      ? "Primero termina la revision de directorios."
      : sourceMonitorProcessingId
        ? "Hay un procesamiento en curso."
        : sourceMonitorPendingTotal > 0
          ? "Hay archivos pendientes reales. Procesalos y revisa los importes antes de publicar."
          : "Publica los marts validados a Google Cloud Storage.";
  const distributorConfigSources = Object.keys(distributorConfig?.summary.sources || {}).sort((a, b) => a.localeCompare(b));
  const distributorConfigAccounts = (distributorConfig?.accounts || [])
    .filter((account) => !distributorConfigSource || account.source === distributorConfigSource);
  const selectedDistributorAccount = distributorConfigAccounts.find((account) => account.policy_id === distributorConfigAccountId)
    || distributorConfigAccounts[0]
    || null;
  const selectedDistributorAdjustmentPct = selectedDistributorAccount
    ? parseDistributorAdjustment(distributorAdjustmentDrafts[selectedDistributorAccount.policy_id] ?? String(selectedDistributorAccount.report_net_adjustment_pct || 0))
    : 0;
  const selectedDistributorRealAmount = selectedDistributorAccount?.account_impact_stats?.amount_usd || 0;
  const selectedDistributorAdjustedAmount = Number.isFinite(selectedDistributorAdjustmentPct)
    ? selectedDistributorRealAmount * (1 - selectedDistributorAdjustmentPct / 100)
    : selectedDistributorRealAmount;
  const selectedDistributorRulePreview = selectedDistributorAccount?.rule_preview || null;
  const selectedDictionaryEntries = selectedDistributorAccount?.statement_dictionary || [];
  const selectedReportImpacts = (distributorConfig?.report_templates || []).filter((template) => {
    const text = JSON.stringify(template).toLowerCase();
    return selectedDistributorAccount
      ? text.includes(selectedDistributorAccount.source.toLowerCase())
        || text.includes(selectedDistributorAccount.account.toLowerCase())
        || template.report_family === "statement"
      : false;
  });

  const financeMovementPreviewLines: FinanceMovementLineForm[] = financeMovementForm.multipleConcepts
    ? financeMovementForm.conceptLines
    : [{
      uid: "single",
      concept: financeMovementForm.concept,
      counterparty: financeMovementForm.counterparty,
      paidBy: financeMovementForm.paidBy,
      paidByEmployeeId: financeMovementForm.paidByEmployeeId,
      amount: financeMovementForm.amount,
      paidAmount: financeMovementForm.paidAmount,
      dueDate: financeMovementForm.dueDate,
      paymentStatus: financeMovementForm.paymentStatus,
      currency: financeMovementForm.currency,
      fxRate: financeMovementForm.fxRate,
    }];
  const financeMovementPreviewTotals = financeMovementPreviewLines.reduce((totals, line) => {
    const currency = isUsdAmountInput(line.amount) ? "USD" : line.currency;
    const amount = parseMoneyInput(stripUsdPrefix(line.amount));
    const paidAmount = line.paidAmount.trim()
      ? parseMoneyInput(stripUsdPrefix(line.paidAmount))
      : amount;
    const fxRate = parseMoneyInput(line.fxRate);
    const amountArs = currency === "USD" ? amount * fxRate : amount;
    const paidArs = currency === "USD" ? paidAmount * fxRate : paidAmount;
    return {
      amountArs: totals.amountArs + amountArs,
      paidArs: totals.paidArs + paidArs,
    };
  }, { amountArs: 0, paidArs: 0 });
  const financeMovementAmountArs = financeMovementPreviewTotals.amountArs;
  const financeMovementPaidArs = financeMovementPreviewTotals.paidArs;
  const financeMovementPendingArs = Math.max(financeMovementAmountArs - financeMovementPaidArs, 0);
  const financeAllocationPreviewTotals = financeMovementForm.allocationLines.reduce((totals, line) => {
    const amount = parseMoneyInput(stripUsdPrefix(line.amount));
    const currency = isUsdAmountInput(line.amount) ? "USD" : line.currency;
    const fxRate = parseMoneyInput(line.fxRate);
    const amountArs = currency === "USD" ? amount * fxRate : amount;
    const indyanaCostArs = line.allocationType === "indyana_cost" ? amountArs : 0;
    const thirdPartyReceivableArs = line.allocationType === "third_party_receivable" ? amountArs : 0;
    return {
      amountArs: totals.amountArs + amountArs,
      indyanaCostArs: totals.indyanaCostArs + indyanaCostArs,
      thirdPartyReceivableArs: totals.thirdPartyReceivableArs + thirdPartyReceivableArs,
    };
  }, { amountArs: 0, indyanaCostArs: 0, thirdPartyReceivableArs: 0 });
  const financeAllocationDifferenceArs = financeMovementForm.economicDistributionEnabled
    ? financeAllocationPreviewTotals.amountArs - financeMovementAmountArs
    : 0;
  const financeMovementSelectedEmployee = financeEmployeeOptions.find(
    (employee) => employee.display_name === financeMovementForm.counterparty,
  );
  const financeMovementIsEmployeeReimbursementFlow = financeMovementForm.movementType === "pago"
    && financeMovementForm.category === "employee_reimbursement";
  const financeMovementSelectedEmployeePendingReimbursements = (financeMovements?.employee_reimbursements?.items || [])
    .filter((item) => item.employee_name === financeMovementForm.counterparty && (item.balance_ars || item.amount_ars || 0) > 0.01);
  const financeMovementAccountApplicationTotalArs = financeMovementForm.accountApplications.reduce((total, application) => (
    total + parseMoneyInput(application.amountArs)
  ), 0);
  const financeMovementRecoverablePct = parseMoneyInput(financeMovementForm.recoverablePercent);
  const financeMovementArtistPct = parseMoneyInput(financeMovementForm.artistPercent);
  const financeMovementProducerPct = parseMoneyInput(financeMovementForm.producerPercent);
  const financeMovementRecoverableBase = financeMovementForm.recoverable
    ? financeMovementAmountArs * financeMovementRecoverablePct / 100
    : 0;
  const financeMovementArtistEconomicCost = financeMovementRecoverableBase * financeMovementArtistPct / 100;
  const financeMovementProducerEconomicCost = financeMovementRecoverableBase * financeMovementProducerPct / 100;
  const financeMovementCashRecovery = financeMovementForm.recoverable
    ? financeMovementRecoverableBase
    : 0;
  const financeRecoveryMethodHelp: Record<FinanceMovementForm["recoveryMethod"], string> = {
    none: "Elegilo si el gasto no se recupera o todavia no esta definido.",
    before_split: "Se descuenta antes del split del show: Indyana recupera caja, pero el costo economico se reparte por el split.",
    after_split: "Se descuenta despues del split, normalmente del pago del artista.",
    direct_account: "Genera saldo de cuenta corriente contra el artista o tercero.",
    royalties: "Se recupera contra regalias digitales futuras.",
    manual: "Caso especial que se va a aplicar con un movimiento o ajuste especifico.",
  };
  const financeMovementIsBookingAccountFlow = financeMovementForm.movementType === "pago"
    && financeMovementForm.businessArea === "booking"
    && financeMovementForm.category === "cuenta_booking";
  const financeMovementDocumentType = financeMovementForm.category === "sena_show"
    ? "show_deposit_receipt"
    : financeMovementForm.category === "collection_receipt"
      ? "collection_receipt"
      : "payment_order";
  const financeMovementDocumentTitle = financeMovementDocumentType === "show_deposit_receipt"
    ? "Recibo"
    : financeMovementDocumentType === "collection_receipt"
      ? "Comprobante de cobro"
      : "Orden de pago";
  const financeMovementDocumentDefaultConcept = financeMovementDocumentType === "show_deposit_receipt"
    ? "Seña de show"
    : financeMovementDocumentType === "collection_receipt"
      ? "Comprobante de cobro"
      : "Orden de pago";
  const financeMovementDocumentCounterpartyLabel = financeMovementDocumentType === "payment_order"
    ? "A quien se paga"
    : "De quien se recibe";
  const financeMovementDocumentAmountLabel = financeMovementDocumentType === "payment_order"
    ? "Importe pagado"
    : "Importe recibido";
  const financeMovementIsShowDepositDocumentFlow = financeMovementForm.movementType === "pago"
    && financeMovementForm.businessArea === "booking"
    && financeMovementForm.category === "sena_show";
  const financeMovementIsFinancialDocumentFlow = financeMovementForm.movementType === "pago"
    && ["sena_show", "payment_order", "collection_receipt"].includes(financeMovementForm.category);
  const financeMovementIsExpenseDocumentFlow = financeMovementForm.movementType === "gasto"
    && financeMovementForm.generateDocumentPdf
    && !financeMovementForm.multipleConcepts;
  const financeMovementUsesDocumentDetail = financeMovementIsFinancialDocumentFlow || financeMovementIsExpenseDocumentFlow;
  const financeMovementReadyForDetails = Boolean(financeMovementForm.businessArea && financeMovementForm.category);
  const payrollPermission = currentModulePermission("payroll_compensation");
  const financeMovementCanUseOffice = currentUser?.role === "admin" || Boolean(payrollPermission?.can_access);
  const financeMovementCanCreatePayroll = currentUser?.role === "admin" || Boolean(payrollPermission?.can_create);
  const financeMovementCanEditPayroll = currentUser?.role === "admin" || Boolean(payrollPermission?.can_edit);
  const financeMovementRequiresArtist = ["marketing", "label", "digitales", "booking"].includes(financeMovementForm.businessArea)
    && !financeMovementIsEmployeeReimbursementFlow;
  const financeMovementBookingWaitingForType = financeMovementForm.businessArea === "booking" && !financeMovementForm.category;
  const financeMovementShowTopArtistSelector = financeMovementRequiresArtist
    && !financeMovementIsShowDepositDocumentFlow
    && !financeMovementBookingWaitingForType;
  const financeMovementIsOfficeArea = financeMovementForm.businessArea === "estructura";
  const financeMovementNeedsEmployee = financeMovementIsEmployeeReimbursementFlow
    || (financeMovementIsOfficeArea && ["salario", "comision_interna"].includes(financeMovementForm.category));
  const financeMovementShowConceptFields = financeMovementReadyForDetails
    && !financeMovementIsBookingAccountFlow
    && !financeMovementIsFinancialDocumentFlow
    && !financeMovementIsEmployeeReimbursementFlow;
  const financeMovementShowTreatment = financeMovementShowConceptFields
    && !financeMovementIsOfficeArea
    && financeMovementForm.movementType !== "ingreso"
    && financeMovementForm.movementType !== "pago";
  const financeMovementAreaLabel = "Area";
  const financeMovementCategoryLabel = financeMovementForm.movementType === "pago"
    ? "Tipo de pago/cobro"
    : financeMovementIsOfficeArea ? "Categoria oficina" : "Categoria";
  const financeMovementBaseCanSave = financeMovementEditingId
    ? canEditModule("finance_movements")
    : canCreateModule("finance_movements");
  const financeMovementCanSave = financeMovementBaseCanSave && (
    !financeMovementNeedsEmployee
      || financeMovementIsEmployeeReimbursementFlow
      || (financeMovementEditingId ? financeMovementCanEditPayroll : financeMovementCanCreatePayroll)
  );
  const financeMovementAreaOptions: [FinanceBusinessArea, string][] = [
    ["marketing", "Marketing"],
    ["label", "Label"],
    ["digitales", "Digitales"],
    ["booking", "Booking"],
    ...(financeMovementCanUseOffice ? [["estructura", "Oficina"] as [FinanceBusinessArea, string]] : []),
  ];
  const financeMovementPermission = currentModulePermission("finance_movements");
  const financeMovementAllowedArtistNames = financeMovementPermission && permissionUsesArtistScope(financeMovementPermission) && !permissionHasAllArtists(financeMovementPermission)
    ? new Set(permissionArtistNames(financeMovementPermission).map(artistScopeKey))
    : null;
  const financeMovementArtistOptions = Array.from(new Set([
    ...(financeMovements?.artists || []),
    ...bookingArtists,
  ]))
    .filter((artist) => artist && artist !== "VPO Corp / estructura" && artist !== "Sin artista asignado")
    .filter((artist) => !financeMovementAllowedArtistNames || financeMovementAllowedArtistNames.has(artistScopeKey(artist)))
    .sort((a, b) => a.localeCompare(b));
  const financeMovementCategoryOptions = (() => {
    if (financeMovementForm.movementType === "ajuste") {
      return [
        ["ajuste_admin", "Ajuste administrativo"],
        ["correccion", "Correccion"],
        ["reclasificacion", "Reclasificacion"],
        ["cierre", "Cierre / regularizacion"],
        ["otro", "Otro ajuste"],
      ];
    }
    if (financeMovementForm.movementType === "pago") {
      const documentOptions: string[][] = [
        ["payment_order", "Orden de pago"],
        ["collection_receipt", "Comprobante de cobro"],
      ];
      if (financeMovementForm.businessArea === "booking") {
        return [
          ["cuenta_booking", "Cuenta booking"],
          ["sena_show", "Seña de show / recibo"],
          ["employee_reimbursement", "Reintegro a empleado"],
          ...documentOptions,
          ["recuperable_abierto", "Recuperable abierto"],
          ["proveedor_pendiente", "Proveedor pendiente"],
          ["adelanto_prestamo", "Adelanto / prestamo"],
          ["sin_aplicar", "Sin aplicar todavia"],
        ];
      }
      return [
        ["employee_reimbursement", "Reintegro a empleado"],
        ...documentOptions,
        ["recuperable_abierto", "Recuperable abierto"],
        ["proveedor_pendiente", "Proveedor pendiente"],
        ["adelanto_prestamo", "Adelanto / prestamo"],
        ["sin_aplicar", "Sin aplicar todavia"],
      ];
    }
    const optionsByArea: Record<FinanceBusinessArea, string[][]> = {
      booking: [
        ["movilidad", "Movilidad / viaticos"],
        ["produccion_show", "Produccion"],
        ["dj_set", "DJ set / contenido booking"],
        ["comision_booking", "Comision booking"],
        ["staff_tecnico", "Staff / tecnico"],
        ["otro_booking", "Otro booking"],
      ],
      label: [
        ["videoclip", "Videoclip"],
        ["produccion_musical", "Produccion musical"],
        ["mix_master", "Mix & master"],
        ["estreno", "Estreno"],
        ["arte_diseno", "Arte / diseno"],
        ["fotografia_contenido", "Fotografia / contenido"],
        ["estudio", "Estudio"],
        ["otro_label", "Otro label"],
      ],
      management: [
        ["imagen_branding", "Imagen / branding"],
        ["vestuario_styling", "Vestuario / styling"],
        ["fotos", "Fotos"],
        ["coaching", "Coaching / entrenamiento"],
        ["logistica_artista", "Logistica artista"],
        ["otro_management", "Otro management"],
      ],
      digitales: [
        ["distribucion", "Distribucion"],
        ["metadata_catalogo", "Metadata / catalogo"],
        ["herramientas_digitales", "Herramientas digitales"],
        ["reclamos_soporte", "Reclamos / soporte"],
        ["otro_digital", "Otro digital"],
      ],
      marketing: [
        ["pauta", "Pauta"],
        ["prensa", "Prensa"],
        ["influencers", "Influencers"],
        ["activacion", "Activacion"],
        ["diseno_contenido", "Diseno / contenido"],
        ["otro_marketing", "Otro marketing"],
      ],
      estructura: [
        ["salario", "Sueldo"],
        ["comision_interna", "Comision interna"],
        ["oficina", "Oficina"],
        ["sistema", "Sistema"],
        ["impuesto", "Impuesto"],
        ["alquiler", "Alquiler"],
        ["servicio", "Servicio"],
        ["honorarios", "Honorarios"],
        ["otro_estructura", "Otro estructura"],
      ],
      administracion: [
        ["honorarios", "Honorarios"],
        ["impuesto", "Impuesto"],
        ["banco", "Banco / financiero"],
        ["proveedor", "Proveedor"],
        ["otro_administracion", "Otro administracion"],
      ],
      general: [
        ["general", "General"],
        ["otro", "Otro"],
      ],
    };
    return optionsByArea[(financeMovementForm.businessArea || "general") as FinanceBusinessArea] || optionsByArea.general;
  })();
  const financeProjectOptions = (financeMovements?.projects || []).filter((project) => (
    (!financeMovementForm.artist || !project.artist || artistScopeKey(project.artist) === artistScopeKey(financeMovementForm.artist))
    && (!financeMovementForm.businessArea || project.business_area === financeMovementForm.businessArea || !project.business_area)
  ));
  const financeMovementProjectSelectValue = financeMovementProjectMode === "new"
    ? "__new__"
    : !financeMovementForm.projectName
    ? ""
    : financeProjectOptions.some((project) => project.name === financeMovementForm.projectName)
      ? financeMovementForm.projectName
      : "__new__";
  const financeMovementProjectIsNew = financeMovementProjectMode === "new" || financeMovementProjectSelectValue === "__new__";
  const financeMovementProjectOptions = financeMovements?.project_options || [];
  const artistFinanceProjectOptions = Array.from(new Set([
    ...(artistFinance?.finance_project_summary || []).map((project) => project.project_name),
    ...(artistFinance?.finance_movements || []).map((item) => item.project_name || "(sin proyecto)"),
  ])).filter(Boolean).sort();
  const filteredArtistFinanceProjects = (artistFinance?.finance_project_summary || []).filter((project) => (
    !artistFinanceProjectFilter || project.project_name === artistFinanceProjectFilter
  )).sort((a, b) => {
    const dateA = a.last_date || a.first_date || "";
    const dateB = b.last_date || b.first_date || "";
    return dateB.localeCompare(dateA) || a.project_name.localeCompare(b.project_name);
  });
  const filteredArtistFinanceMovements = (artistFinance?.finance_movements || []).filter((item) => (
    !artistFinanceProjectFilter || (item.project_name || "(sin proyecto)") === artistFinanceProjectFilter
  ));
  const filteredArtistFinanceRecoveries = (artistFinance?.recovery_applications || []).filter((item) => (
    !artistFinanceProjectFilter || (item.project_name || "(sin proyecto)") === artistFinanceProjectFilter
  ));
  const artistFinanceLedgerSummary = artistFinance?.finance_ledger.summary;
  const artistFinanceBookingSummary = artistFinance?.summary.booking;
  const artistFinanceAccountNet = artistFinanceLedgerSummary?.account_current_net_ars || 0;
  const artistFinanceVenueDebt = artistFinanceLedgerSummary?.venue_receivable_ars || 0;
  const artistFinancePendingCriteria = artistFinance?.summary.finance_staging.recoverable_pending_criteria_ars || 0;
  const artistFinanceDefinedRecoverableOpen = artistFinance?.summary.finance_staging.recoverable_defined_open_ars ?? Math.max((artistFinanceLedgerSummary?.recoverable_open_ars || 0) - artistFinancePendingCriteria, 0);
  const artistFinanceProjectRows = artistFinance?.summary.finance_staging.rows || 0;
  const artistFinanceSelectedLabel = artistFinance?.selected_artist || "Todos";
  const artistFinanceStatus = (() => {
    if (Math.abs(artistFinanceAccountNet) > 0.01) {
      return {
        tone: artistFinanceAccountNet > 0 ? "warn" : "attention",
        title: artistFinanceAccountNet > 0 ? "Nos deben" : "Le debemos",
        body: artistFinanceAccountNet > 0
          ? `${artistFinanceSelectedLabel} tiene saldo abierto a favor de Indyana.`
          : `Indyana tiene saldo abierto a favor de ${artistFinanceSelectedLabel}.`,
      };
    }
    if (artistFinancePendingCriteria > 0.01) {
      return {
        tone: "attention",
        title: "Pendiente de criterio",
        body: "Hay gastos cargados que todavia necesitan decision de negocio antes de tratarlos como recuperables o inversion final.",
      };
    }
    if (artistFinanceDefinedRecoverableOpen > 0.01) {
      return {
        tone: "warn",
        title: "Hay recuperables",
        body: "La cuenta corriente esta al dia, pero quedan proyectos con dinero por recuperar.",
      };
    }
    return {
      tone: "ok",
      title: "Al dia",
      body: "No hay saldos abiertos visibles para este filtro.",
    };
  })();
  const artistFinanceAccountEntries = (artistFinance?.finance_ledger.entries || []).filter((item) => (
    Math.abs(item.account_delta_ars || 0) > 0.01 || Math.abs(item.venue_receivable_ars || 0) > 0.01
  ));
  const bookingParentMovementLabels: Record<BookingParentMovementType, string> = {
    cobro_deuda_booking: "Cobro de deuda booking",
    pago_saldo_artista: "Pago saldo artista",
    compensacion_booking: "Compensacion booking",
    pago_deuda_boliche: "Pago deuda boliche",
    ajuste_booking: "Ajuste booking",
  };
  const bookingParentMovementHelp: Record<BookingParentMovementType, string> = {
    cobro_deuda_booking: "Entra plata real a Indyana para saldar shows donde nos deben.",
    pago_saldo_artista: "Sale plata real de Indyana para saldar shows donde debemos al artista.",
    compensacion_booking: "No entra ni sale plata nueva; se cruza un saldo contra otro.",
    pago_deuda_boliche: "El cliente o boliche paga una deuda pendiente de cachet.",
    ajuste_booking: "Decision administrativa observada. No usar como camino normal.",
  };
  function artistFinanceOpenAmountForMovement(item: ArtistFinanceOpenBalance, movementType: BookingParentMovementType) {
    const bookingNet = bookingCurrentAccountNet(item.indyana_balance || 0, item.artist_balance || 0);
    if (movementType === "cobro_deuda_booking") return Math.max(bookingNet, 0);
    if (movementType === "pago_saldo_artista") return Math.max(-bookingNet, 0);
    if (movementType === "pago_deuda_boliche") return Math.max(item.venue_balance || 0, 0);
    if (movementType === "compensacion_booking") return Math.abs(bookingNet);
    return Math.max(Math.abs(bookingNet), Math.max(item.venue_balance || 0, 0));
  }

  function artistFinanceTargetForMovement(item: ArtistFinanceOpenBalance, movementType: BookingParentMovementType): BookingAccountTarget {
    const artistBalance = item.artist_balance || 0;
    const producerBalance = item.indyana_balance || 0;
    const venueBalance = item.venue_balance || 0;
    if (movementType === "pago_deuda_boliche") return "venue";
    if (movementType === "cobro_deuda_booking") {
      if (artistBalance < -0.01) return "artist";
      if (producerBalance > 0.01) return "producer";
      return "artist";
    }
    if (movementType === "pago_saldo_artista") {
      if (artistBalance > 0.01) return "artist";
      if (producerBalance < -0.01) return "producer";
      return "artist";
    }
    if (movementType === "ajuste_booking" && venueBalance > 0.01 && Math.abs(artistBalance) <= 0.01 && Math.abs(producerBalance) <= 0.01) {
      return "venue";
    }
    if (Math.abs(artistBalance) > 0.01) return "artist";
    if (Math.abs(producerBalance) > 0.01) return "producer";
    return "venue";
  }

  const artistFinanceBookingMovementAmount = parseMoneyInput(artistFinanceBookingMovementDraft.amount);
  const artistFinanceBookingMovementRows = (artistFinance?.open_booking_balances || [])
    .map((item) => ({
      item,
      openAmount: artistFinanceOpenAmountForMovement(item, artistFinanceBookingMovementDraft.movementType),
      appliedAmount: parseMoneyInput(artistFinanceBookingMovementDraft.applications[item.id] || ""),
    }))
    .filter((row) => row.openAmount > 0.01)
    .sort((a, b) => (a.item.show_date || "").localeCompare(b.item.show_date || "") || a.item.id - b.item.id);
  const artistFinanceBookingMovementApplied = artistFinanceBookingMovementRows.reduce((total, row) => total + row.appliedAmount, 0);
  const artistFinanceBookingMovementRemaining = artistFinanceBookingMovementAmount - artistFinanceBookingMovementApplied;
  const artistFinanceBookingMovementOverApplied = artistFinanceBookingMovementRows.some((row) => row.appliedAmount > row.openAmount + 0.01);
  const artistFinanceBookingBlockRows = (artistFinance?.open_booking_balances || [])
    .map((item) => ({
      item,
      netAmount: bookingCurrentAccountNet(item.indyana_balance || 0, item.artist_balance || 0),
      selected: parseMoneyInput(artistFinanceBookingMovementDraft.applications[item.id] || "") > 0.01,
    }))
    .filter((row) => Math.abs(row.netAmount) > 0.01 || Math.abs(row.item.venue_balance || 0) > 0.01)
    .sort((a, b) => (a.item.show_date || "").localeCompare(b.item.show_date || "") || a.item.id - b.item.id);
  const artistFinanceBookingBlockSelectedRows = artistFinanceBookingBlockRows.filter((row) => row.selected);
  const artistFinanceBookingBlockArtistBalance = artistFinanceBookingBlockSelectedRows.reduce((total, row) => total + (row.item.artist_balance || 0), 0);
  const artistFinanceBookingBlockProducerBalance = artistFinanceBookingBlockSelectedRows.reduce((total, row) => total + (row.item.indyana_balance || 0), 0);
  const artistFinanceBookingBlockVenueBalance = artistFinanceBookingBlockSelectedRows.reduce((total, row) => total + (row.item.venue_balance || 0), 0);
  const artistFinanceBookingBlockNet = bookingCurrentAccountNet(artistFinanceBookingBlockProducerBalance, artistFinanceBookingBlockArtistBalance);
  const artistFinanceBookingBlockExpectedAmount = Math.abs(artistFinanceBookingBlockNet);
  const artistFinanceBookingBlockAmountMatches = Math.abs(artistFinanceBookingMovementAmount - artistFinanceBookingBlockExpectedAmount) <= 0.01;
  const artistFinanceBookingMovementCanSave = Boolean(artistFinanceArtist)
    && canEditModule("booking")
    && !artistFinanceLoading
    && artistFinanceBookingMovementAmount > 0.01
    && artistFinanceBookingMovementApplied > 0.01
    && artistFinanceBookingMovementRemaining >= -0.01
    && !artistFinanceBookingMovementOverApplied;

  function updateArtistFinanceBookingMovementField<K extends keyof BookingParentMovementDraft>(key: K, value: BookingParentMovementDraft[K]) {
    setArtistFinanceBookingMovementDraft((current) => ({ ...current, [key]: value }));
  }

  function updateArtistFinanceBookingMovementApplication(showId: number, value: string) {
    setArtistFinanceBookingMovementDraft((current) => ({
      ...current,
      applications: {
        ...current.applications,
        [showId]: value,
      },
    }));
  }

  function resetArtistFinanceBookingMovementDraft() {
    setArtistFinanceBookingMovementDraft(initialBookingParentMovementDraft());
  }

  function suggestArtistFinanceBookingMovementApplications() {
    let remaining = artistFinanceBookingMovementAmount;
    const nextApplications: Record<number, string> = {};
    for (const row of artistFinanceBookingMovementRows) {
      if (remaining <= 0.01) break;
      const applied = Math.min(row.openAmount, remaining);
      nextApplications[row.item.id] = amountToInput(applied);
      remaining -= applied;
    }
    setArtistFinanceBookingMovementDraft((current) => ({
      ...current,
      applications: nextApplications,
    }));
  }

  function selectArtistFinanceBookingBlockRows() {
    const nextApplications: Record<number, string> = {};
    for (const row of artistFinanceBookingBlockRows) {
      nextApplications[row.item.id] = amountToInput(Math.abs(row.netAmount));
    }
    const producerBalance = artistFinanceBookingBlockRows.reduce((total, row) => total + (row.item.indyana_balance || 0), 0);
    const artistBalance = artistFinanceBookingBlockRows.reduce((total, row) => total + (row.item.artist_balance || 0), 0);
    const netAmount = bookingCurrentAccountNet(producerBalance, artistBalance);
    setArtistFinanceBookingMovementDraft((current) => ({
      ...current,
      amount: amountToInput(Math.abs(netAmount)),
      applications: nextApplications,
    }));
  }

  async function submitArtistFinanceBookingMovement() {
    if (!artistFinanceArtist) {
      setMessage({ type: "error", text: "Elegir un artista antes de guardar el movimiento." });
      return;
    }
    if (!canEditModule("booking")) {
      setMessage({ type: "error", text: "No tenes permiso para registrar movimientos de Booking." });
      return;
    }
    if (artistFinanceBookingMovementAmount <= 0.01) {
      setMessage({ type: "error", text: "Cargar el importe total del movimiento." });
      return;
    }
    if (artistFinanceBookingMovementApplied <= 0.01) {
      setMessage({ type: "error", text: "Aplicar el movimiento a por lo menos un show." });
      return;
    }
    if (artistFinanceBookingMovementRemaining < -0.01) {
      setMessage({ type: "error", text: "La suma aplicada supera el importe del movimiento." });
      return;
    }
    if (artistFinanceBookingMovementOverApplied) {
      setMessage({ type: "error", text: "Hay un show con importe aplicado mayor al saldo abierto." });
      return;
    }
    const applications = artistFinanceBookingMovementRows
      .filter((row) => row.appliedAmount > 0.01)
      .map((row) => ({
        show_id: row.item.id,
        target_balance: artistFinanceTargetForMovement(row.item, artistFinanceBookingMovementDraft.movementType),
        amount: row.appliedAmount,
      }));
    const proofRefs = artistFinanceBookingMovementDraft.proofRefs
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    setArtistFinanceLoading(true);
    setMessage(null);
    const response = await fetch("/api/booking/account-movements", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        movement_date: artistFinanceBookingMovementDraft.movementDate,
        artist: artistFinanceArtist,
        movement_type: artistFinanceBookingMovementDraft.movementType,
        amount: artistFinanceBookingMovementAmount,
        payment_method: artistFinanceBookingMovementDraft.paymentMethod,
        counterparty: artistFinanceBookingMovementDraft.counterparty.trim() || null,
        proof_refs: proofRefs,
        notes: artistFinanceBookingMovementDraft.notes.trim() || null,
        applications,
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ error: "No se pudo guardar el movimiento." }));
      setArtistFinanceLoading(false);
      setMessage({ type: "error", text: payload.error || "No se pudo guardar el movimiento." });
      return;
    }
    const data = await response.json();
    resetArtistFinanceBookingMovementDraft();
    setArtistFinanceBookingMovementOpen(false);
    await loadArtistFinance();
    const unapplied = data.item?.unapplied_amount || 0;
    setMessage({
      type: "ok",
      text: unapplied > 0.01
        ? `Movimiento guardado. Quedaron ${ars(unapplied)} sin aplicar.`
        : "Movimiento guardado y aplicado a los shows seleccionados.",
    });
  }

  async function submitArtistFinanceBookingBlockSettlement() {
    if (!artistFinanceArtist) {
      setMessage({ type: "error", text: "Elegir un artista antes de cerrar el bloque." });
      return;
    }
    if (!canEditModule("booking")) {
      setMessage({ type: "error", text: "No tenes permiso para cerrar bloques de Booking." });
      return;
    }
    if (artistFinanceBookingBlockSelectedRows.length === 0) {
      setMessage({ type: "error", text: "Seleccionar los shows que forman parte del bloque." });
      return;
    }
    if (Math.abs(artistFinanceBookingBlockVenueBalance) > 0.01) {
      setMessage({ type: "error", text: "El bloque tiene deuda de boliche. Cerrala por separado antes de saldar el artista." });
      return;
    }
    if (artistFinanceBookingBlockExpectedAmount <= 0.01) {
      setMessage({ type: "error", text: "El bloque seleccionado ya esta saldado." });
      return;
    }
    if (!artistFinanceBookingBlockAmountMatches) {
      setMessage({
        type: "error",
        text: `El importe debe coincidir con el neto del bloque: ${ars(artistFinanceBookingBlockExpectedAmount)}.`,
      });
      return;
    }
    const proofRefs = artistFinanceBookingMovementDraft.proofRefs
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    setArtistFinanceLoading(true);
    setMessage(null);
    const response = await fetch("/api/booking/account-block-settlements", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        settlement_date: artistFinanceBookingMovementDraft.movementDate,
        artist: artistFinanceArtist,
        amount: artistFinanceBookingMovementAmount,
        payment_method: artistFinanceBookingMovementDraft.paymentMethod,
        counterparty: artistFinanceBookingMovementDraft.counterparty.trim() || null,
        proof_refs: proofRefs,
        notes: artistFinanceBookingMovementDraft.notes.trim() || null,
        show_ids: artistFinanceBookingBlockSelectedRows.map((row) => row.item.id),
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ error: "No se pudo cerrar el bloque." }));
      setArtistFinanceLoading(false);
      setMessage({ type: "error", text: payload.error || "No se pudo cerrar el bloque." });
      return;
    }
    resetArtistFinanceBookingMovementDraft();
    setArtistFinanceBookingMovementOpen(false);
    await loadArtistFinance();
    setMessage({ type: "ok", text: "Bloque cerrado: el sistema compenso saldos cruzados y aplico el pago/cobro real." });
  }

  function renderRoyaltiesRankTable(title: string, rows: RoyaltiesDashboardRank[], emptyText = "Sin datos para este filtro.") {
    return (
      <div className="royalties-rank-card">
        <div className="royalties-card-title">
          <h2>{title}</h2>
          <span>{rows.length ? `${rows.length} items` : "sin datos"}</span>
        </div>
        {royaltiesDashboardLoading && <div className="royalties-empty">Cargando...</div>}
        {!royaltiesDashboardLoading && rows.length === 0 && <div className="royalties-empty">{emptyText}</div>}
        <div className="royalties-rank-list">
          {rows.map((row, idx) => (
            <div className="royalties-rank-row" key={`${title}-${row.name}-${idx}`}>
              <div className="royalties-rank-main">
                <span className="royalties-rank-index">{idx + 1}</span>
                <strong>{row.name || "-"}</strong>
                <small>{Math.round(row.units || 0).toLocaleString("es-AR")} unidades</small>
              </div>
              <div className="royalties-rank-value">
                <strong>{moneyCents(row.amount_usd || 0)}</strong>
                <span>{(row.percentage || 0).toLocaleString("es-AR", { maximumFractionDigits: 2 })}%</span>
              </div>
              <div className="royalties-rank-bar" aria-hidden="true">
                <span style={{ width: `${Math.max(2, Math.min(100, row.percentage || 0))}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={`shell ${view === "menu" ? "home-shell" : ""}`}>
      {view !== "menu" && <header className="topbar">
        <div className="brand" aria-label="VPO Corp">
          <Image className="topbar-logo" src="/vpo-logo.png" alt="VPO Corp" width={2539} height={1298} priority />
        </div>
        <div className="top-actions">
          {currentUser && (
            <span className="session-pill">{currentUser.username} · {currentUser.role}</span>
          )}
          <button type="button" onClick={() => openView("menu")}>Menu</button>
          <button type="button" onClick={logout}>Salir</button>
        </div>
      </header>}

      <main className={view === "menu" ? "home-main" : view === "booking" && bookingSurface === "dashboard" ? "booking-main" : undefined}>
        {message && <div className={`message ${message.type === "error" ? "error" : ""}`}>{message.text}</div>}

        {view === "menu" && (
          <VpoHome
            username={currentUser?.username || "usuario"}
            role={currentUser?.role || "viewer"}
            canShow={(targetView) => canShowMenuView(targetView as View)}
            onOpen={(targetView) => targetView === "booking" ? openBookingWorkspace() : openView(targetView as View)}
            onLogout={logout}
          />
        )}

        {view === "statement" && (
          <section className="panel">
            <h1>Reporte por statement</h1>
            <p>Genera el reporte historico por statement usando los marts nuevos publicados.</p>
            <label htmlFor="statement_report_version">Tipo de reporte</label>
            <select
              id="statement_report_version"
              value={statementReportVersion}
              onChange={(event) => setStatementReportVersion(event.target.value)}
            >
              <option value="legacy">Reporte viejo</option>
              <option value="new">Reporte nuevo</option>
            </select>
            <p className="field-help">
              El nuevo excluye ONErpm MAWZ y usa las variantes post Motorcito / La Nueva Sangre.
            </p>
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
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={statementIncludeZeros}
                onChange={(event) => setStatementIncludeZeros(event.target.checked)}
              />
              Incluir artistas exactamente en cero
            </label>
            <p className="field-help">
              Si esta desmarcado y el minimo es 0, muestra cualquier total mayor a cero, aunque sea 0.01.
            </p>
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

              <label>Formato</label>
              <div className="report-format-switch" role="group" aria-label="Formato del reporte">
                <button
                  type="button"
                  className={royaltyReportOutput === "excel" ? "active" : ""}
                  onClick={() => setRoyaltyReportOutput("excel")}
                >
                  <FileSpreadsheet size={18} aria-hidden="true" />
                  Excel detallado
                </button>
                <button
                  type="button"
                  className={royaltyReportOutput === "executive_pdf" ? "active" : ""}
                  onClick={() => setRoyaltyReportOutput("executive_pdf")}
                >
                  <FileText size={18} aria-hidden="true" />
                  PDF ejecutivo
                </button>
              </div>

              <label htmlFor="keywords">Palabras clave</label>
              <input
                id="keywords"
                value={keywords}
                onChange={(event) => setKeywords(event.target.value)}
                placeholder={royaltyReportOutput === "executive_pdf" ? "Opcional: artista, tema o ISRC" : "gusty dj, juli savioli"}
                required={royaltyReportOutput === "excel"}
              />

              <PeriodControl
                id="royalty_period"
                label="Periodo"
                profile="monthly_report"
                selection={selectionFromMonths(startMonth, endMonth)}
                onChange={(selection) => applyResolvedPeriod(selection, "monthly_report", setStartMonth, setEndMonth)}
                helperText="Un mes solo incluye ese mes completo. Un rango incluye ambos meses completos."
              />

              <label htmlFor="period_basis">Criterio de periodo</label>
              <select id="period_basis" value={periodBasis} onChange={(event) => setPeriodBasis(event.target.value)}>
                <option value="transaction_month">Performance / mes de consumo</option>
                <option value="statement_period">Liquidacion / mes de statement</option>
              </select>

              {royaltyReportOutput === "executive_pdf" && (
                <div className="report-scope-grid">
                  <div>
                    <label htmlFor="royalty_report_source">Distribuidora</label>
                    <select
                      id="royalty_report_source"
                      value={royaltyReportSource}
                      onChange={(event) => {
                        setRoyaltyReportSource(event.target.value);
                        setRoyaltyReportAccount("");
                      }}
                    >
                      <option value="">Todas</option>
                      {(royaltyReportOptions?.sources || []).map((source) => (
                        <option value={source} key={source}>{source.toUpperCase()}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="royalty_report_account">Cuenta</label>
                    <select
                      id="royalty_report_account"
                      value={royaltyReportAccount}
                      disabled={!royaltyReportSource}
                      onChange={(event) => setRoyaltyReportAccount(event.target.value)}
                    >
                      <option value="">Todas</option>
                      {royaltyReportAccountOptions.map((item) => (
                        <option value={item.account} key={`${item.source}:${item.account}`}>{item.display_name}</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {royaltyReportOutput === "excel" && (
                <>
                  <label htmlFor="mode">Coincidencia</label>
                  <select id="mode" value={mode} onChange={(event) => setMode(event.target.value)}>
                    <option value="any">Cualquier palabra</option>
                    <option value="all">Todas las palabras</option>
                  </select>

                  <label htmlFor="raw_limit">Filas raw maximas</label>
                  <input id="raw_limit" type="number" min="0" max="50000" value={rawLimit} onChange={(event) => setRawLimit(event.target.value)} />
                </>
              )}

              <button type="submit" disabled={loading || googleLoading}>
                {loading ? "Generando..." : royaltyReportOutput === "executive_pdf" ? "Descargar PDF" : "Descargar Excel"}
              </button>
            </form>

            <div>
              {royaltyReportOutput === "excel" && (
                <section className="panel">
                  <h2>Google Sheets</h2>
                  <p>Crea el mismo reporte como spreadsheet editable en Google Drive.</p>
                  <button type="button" disabled={loading || googleLoading} onClick={createGoogleSheet}>
                    {googleLoading ? "Creando..." : "Crear Google Sheet"}
                  </button>
                </section>
              )}

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

        {view === "custom-reports" && (
          <section className="panel">
            <div className="section-heading">
              <div>
                <h1>Reportes Personalizados</h1>
                <p>Scripts especiales conectados a los marts nuevos. Cada uno conserva su configuracion editable.</p>
              </div>
              <button type="button" onClick={loadCustomReportOptions}>
                Actualizar opciones
              </button>
            </div>

            <div className="custom-script-menu">
              {(customReportOptions?.templates || []).map((template, index) => (
                <button
                  type="button"
                  className={`custom-script-card ${template.key === customReportTemplateKey ? "active" : ""}`}
                  key={template.key}
                  onClick={() => selectCustomReportTemplate(template.key)}
                >
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <strong>{template.title}</strong>
                  <small>{template.enabled === false ? "Pendiente de definir" : "Listo para generar"}</small>
                </button>
              ))}
              {!customReportOptions && <p className="field-help">Cargando scripts disponibles...</p>}
            </div>

            <form onSubmit={generateCustomReport}>
              {customReportOptions?.templates.find((template) => template.key === customReportTemplateKey)?.description && (
                <p className="field-help script-description">
                  {customReportOptions.templates.find((template) => template.key === customReportTemplateKey)?.description}
                </p>
              )}

              <label htmlFor="custom_report_title">Nombre del reporte</label>
              <input
                id="custom_report_title"
                value={customReportTitle}
                onChange={(event) => setCustomReportTitle(event.target.value)}
              />

              {customReportSupportsStartMonth() ? (
                <PeriodControl
                  id="custom_report_period"
                  label="Statement"
                  profile="custom_report"
                  selection={selectionFromMonths(customReportStartMonth, customReportEndMonth)}
                  onChange={(selection) => applyResolvedPeriod(selection, "custom_report", setCustomReportStartMonth, setCustomReportEndMonth)}
                  helperText="Un mes solo incluye ese statement completo."
                />
              ) : (
                <PeriodControl
                  id="custom_report_until"
                  label="Acumulado hasta"
                  profile="custom_report"
                  variant="until"
                  selection={selectionFromUntil(customReportEndMonth)}
                  onChange={(selection) => {
                    const period = resolvePeriod(selection, "custom_report");
                    setCustomReportStartMonth("");
                    setCustomReportEndMonth(period.endMonth || "");
                  }}
                  helperText="Este template es acumulado: se informa hasta el statement elegido."
                />
              )}

              {(currentCustomReportTemplate()?.options || []).length > 0 && (
                <div className="custom-report-options">
                  {(currentCustomReportTemplate()?.options || []).map((option) => (
                    <label className="checkbox-field custom-report-option" key={option.key}>
                      <input
                        type="checkbox"
                        checked={Boolean(customReportFlags[option.key])}
                        onChange={(event) => setCustomReportFlag(option.key, event.target.checked)}
                      />
                      <span>
                        <strong>{option.label}</strong>
                        {option.description && <small>{option.description}</small>}
                      </span>
                    </label>
                  ))}
                </div>
              )}

              {customReportRequiresTerms() && (
                <>
                  <label htmlFor="custom_terms">Listado editable</label>
                  <textarea
                    id="custom_terms"
                    className="custom-report-terms"
                    value={customReportTerms}
                    onChange={(event) => setCustomReportTerms(event.target.value)}
                  />
                  <p className="field-help">
                    Una busqueda por linea. Usa <strong>Tema</strong> para buscar solo por nombre, o <strong>Tema | Artista</strong> para exigir ambos.
                  </p>
                </>
              )}

              {customReportSupportsSources() && (
                <>
                  <div className="section-heading compact-heading">
                    <div>
                      <h2>Distribuidoras y cuentas</h2>
                      <p>Por defecto quedan todas seleccionadas. Podes desmarcar una distribuidora completa o solo una cuenta.</p>
                    </div>
                    <div className="inline-actions">
                      <button type="button" className="inline-action" onClick={selectAllCustomReportSources}>Todas</button>
                      <button type="button" className="inline-action" onClick={clearCustomReportSources}>Ninguna</button>
                    </div>
                  </div>

                  <div className="source-account-grid">
                    {(customReportOptions?.sources || customReportSources).map((source) => (
                      <div className="source-account-card" key={source}>
                        <label className="checkbox-field source-checkbox source-parent-checkbox">
                          <input
                            type="checkbox"
                            checked={customReportSourceFullySelected(source)}
                            onChange={() => toggleCustomReportSource(source)}
                          />
                          {source}
                        </label>
                        <div className="source-account-list">
                          {customReportAccountsForSource(source).map((item) => {
                            const key = customReportSourceAccountKey(item);
                            return (
                              <label className="checkbox-field source-checkbox source-child-checkbox" key={key}>
                                <input
                                  type="checkbox"
                                  checked={customReportSourceAccounts.includes(key)}
                                  onChange={() => toggleCustomReportSourceAccount(key)}
                                />
                                {item.account}
                              </label>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                    {!customReportOptions && <p className="field-help">Cargando distribuidoras disponibles...</p>}
                  </div>
                </>
              )}

              <button
                type="submit"
                disabled={customReportLoading || customReportOptions?.templates.find((template) => template.key === customReportTemplateKey)?.enabled === false}
              >
                {customReportLoading
                  ? "Generando..."
                  : customReportOptions?.templates.find((template) => template.key === customReportTemplateKey)?.enabled === false
                    ? "Script pendiente"
                    : "Descargar Excel"}
              </button>
              {lastFile && <p className="filename">{lastFile}</p>}
            </form>
          </section>
        )}

        {view === "participation" && (
          <section className="panel">
            <div className="section-heading">
              <div>
                <h1>Participacion en distribuidoras</h1>
                <p>
                  Ingresos reportables por distribuidora, aplicando la capa de negocio de statements.
                  {" "}Ultima actualizacion: {participation?.updated_at || "sin cargar"}
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
                  <option value="last_year">Ultimo ano</option>
                  <option value="all_history">Historico</option>
                  <option value="custom">Rango</option>
                </select>
              </div>

              {participationPreset === "custom" && (
                <PeriodControl
                  id="participation_period"
                  label="Rango custom"
                  profile="preset_or_range"
                  selection={selectionFromMonths(participationStartMonth, participationEndMonth)}
                  minMonth={participation?.available_start_month || undefined}
                  onChange={(selection) => applyResolvedPeriod(selection, "preset_or_range", setParticipationStartMonth, setParticipationEndMonth)}
                />
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

            {!!participation?.account_items?.length && (
              <div className="table-scroll compact-table">
                <table className="summary-table">
                  <thead>
                    <tr>
                      <th>Distribuidora</th>
                      <th>Cuenta</th>
                      <th>USD reportable</th>
                      <th>Participacion</th>
                    </tr>
                  </thead>
                  <tbody>
                    {participation.account_items.map((item) => (
                      <tr key={`${item.source}-${item.account}`}>
                        <td>{item.source}</td>
                        <td>{item.account}</td>
                        <td>{money(item.amount_usd)}</td>
                        <td>{pct(item.percentage)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {view === "royalties-dashboard" && (
          <section className="panel wide-panel royalties-dashboard-panel">
            <div className="royalties-dashboard-hero">
              <div>
                <span className="royalties-eyebrow">Royalty Intelligence</span>
                <h1>Dashboard Regalias</h1>
                <p>Generacion reportable multi-distribuidora: aplica catalogo activo/inactivo, policies de distribuidoras y ajustes de reporte configurados.</p>
              </div>
              <div className="royalties-hero-actions">
                <span>
                  {royaltiesDashboard?.report_personalization.enabled ? "Ajuste VPO activo" : "Ajuste VPO desactivado"}
                  {royaltiesDashboard?.report_personalization.policy_version
                    ? ` · v${royaltiesDashboard.report_personalization.policy_version}`
                    : ""}
                </span>
                <span>{royaltiesDashboard?.totals.first_month || "-"} / {royaltiesDashboard?.totals.last_month || "-"}</span>
                <button type="button" onClick={loadRoyaltiesDashboard} disabled={royaltiesDashboardLoading}>
                  {royaltiesDashboardLoading ? "Cargando..." : "Actualizar"}
                </button>
              </div>
            </div>

            <div className="royalties-filterbar">
              <div>
                <label htmlFor="royalties_dashboard_keyword">Artista / tema / ISRC</label>
                <input
                  id="royalties_dashboard_keyword"
                  value={royaltiesDashboardKeyword}
                  onChange={(event) => setRoyaltiesDashboardKeyword(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      loadRoyaltiesDashboard();
                    }
                  }}
                  placeholder="Ej: Gusty, Raka Taka, QZ..."
                />
              </div>
              <div>
                <label htmlFor="royalties_dashboard_source">Distribuidora</label>
                <select
                  id="royalties_dashboard_source"
                  value={royaltiesDashboardSource}
                  onChange={(event) => {
                    setRoyaltiesDashboardSource(event.target.value);
                    setRoyaltiesDashboardAccount("");
                  }}
                >
                  <option value="">Todas</option>
                  {royaltiesDashboard?.options.sources.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="royalties_dashboard_account">Cuenta</label>
                <select
                  id="royalties_dashboard_account"
                  value={royaltiesDashboardAccount}
                  onChange={(event) => setRoyaltiesDashboardAccount(event.target.value)}
                >
                  <option value="">Todas</option>
                  {royaltiesDashboardAccountOptions.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="royalties_dashboard_basis">Base temporal</label>
                <select
                  id="royalties_dashboard_basis"
                  value={royaltiesDashboardPeriodBasis}
                  onChange={(event) => setRoyaltiesDashboardPeriodBasis(event.target.value as "statement_period" | "transaction_month")}
                >
                  <option value="statement_period">Statement</option>
                  <option value="transaction_month">Consumo</option>
                </select>
              </div>
              <PeriodControl
                id="royalties_dashboard_period"
                label="Periodo"
                profile="dashboard_period"
                selection={royaltiesDashboardPeriod}
                presets={["last_6_months", "last_12_months", "all"]}
                onChange={setRoyaltiesDashboardPeriod}
                helperText="Todo carga el historico disponible. Statement y consumo pueden diferir por rango."
              />
              <button type="button" onClick={loadRoyaltiesDashboard} disabled={royaltiesDashboardLoading}>
                Buscar
              </button>
            </div>

            <div className="royalties-tabs" role="tablist" aria-label="Vistas dashboard regalias">
              <button
                type="button"
                className={royaltiesDashboardTab === "overview" ? "active" : ""}
                onClick={() => setRoyaltiesDashboardTab("overview")}
              >
                Overview
              </button>
              <button
                type="button"
                className={royaltiesDashboardTab === "youtube" ? "active" : ""}
                onClick={() => setRoyaltiesDashboardTab("youtube")}
              >
                YouTube
              </button>
            </div>

            <div className="royalties-kpi-grid">
              <div className="royalties-kpi primary">
                <span>Ingreso reportable</span>
                <strong>{moneyCents(royaltiesDashboard?.totals.amount_usd || 0)}</strong>
              </div>
              <div className="royalties-kpi">
                <span>Unidades</span>
                <strong>{Math.round(royaltiesDashboard?.totals.units || 0).toLocaleString("es-AR")}</strong>
              </div>
              <div className="royalties-kpi">
                <span>Temas</span>
                <strong>{(royaltiesDashboard?.totals.titles || 0).toLocaleString("es-AR")}</strong>
              </div>
              <div className="royalties-kpi">
                <span>Artistas</span>
                <strong>{(royaltiesDashboard?.totals.artists || 0).toLocaleString("es-AR")}</strong>
              </div>
              <div className="royalties-kpi">
                <span>Distribuidoras</span>
                <strong>{royaltiesDashboard?.totals.sources || 0}</strong>
              </div>
              <div className="royalties-kpi">
                <span>Rango</span>
                <strong>{royaltiesDashboard?.totals.first_month || "-"} / {royaltiesDashboard?.totals.last_month || "-"}</strong>
              </div>
            </div>

            <div className="royalties-meta-strip">
              <strong>Criterio</strong>
              <span>{royaltiesDashboardPeriodBasis === "statement_period" ? "Statement" : "Consumo"}</span>
              <strong>Fuente</strong>
              <span>{royaltiesDashboard?.options.first_month || "-"} a {royaltiesDashboard?.options.last_month || "-"}</span>
              <strong>Reglas</strong>
              <span>Catalogo + policies + ajuste de reporte si esta activado</span>
            </div>

            <div className="royalties-section-title">
              <div>
                <h2>Meses por distribuidora</h2>
                <p>Cada fila es una distribuidora/cuenta. Las columnas muestran el rango elegido.</p>
              </div>
            </div>
            <div className="royalties-table-shell">
              <table className="summary-table digital-income-matrix royalties-matrix-table">
                <thead>
                  <tr>
                    <th>Distribuidora / cuenta</th>
                    {(royaltiesDashboard?.period_months || []).map((month) => (
                      <th key={month}>{month}</th>
                    ))}
                    <th>Total</th>
                    <th>Temas</th>
                  </tr>
                </thead>
                <tbody>
                  {royaltiesDashboardLoading && (
                    <tr>
                      <td colSpan={(royaltiesDashboard?.period_months.length || 0) + 3}>Cargando dashboard...</td>
                    </tr>
                  )}
                  {!royaltiesDashboardLoading && royaltiesDashboard?.matrix.length === 0 && (
                    <tr>
                      <td colSpan={(royaltiesDashboard?.period_months.length || 0) + 3}>Sin datos para este filtro.</td>
                    </tr>
                  )}
                  {royaltiesDashboard?.matrix.map((item) => (
                    <tr key={`${item.source}-${item.account}`}>
                      <td>
                        <strong>{item.source}</strong>
                        <span className="cell-note">{item.account}</span>
                      </td>
                      {royaltiesDashboard.period_months.map((month) => (
                        <td key={month}>{moneyCents(item.months[month] || 0)}</td>
                      ))}
                      <td><strong>{moneyCents(item.amount_usd || 0)}</strong></td>
                      <td>{item.titles.toLocaleString("es-AR")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {royaltiesDashboardTab === "overview" && (
              <div className="royalties-rank-grid">
                {renderRoyaltiesRankTable("Top Revenue by Product", royaltiesDashboard?.rankings.title || [])}
                {renderRoyaltiesRankTable("Top Revenue by Artist", royaltiesDashboard?.rankings.artist || [])}
                {renderRoyaltiesRankTable("Top Revenue by DSP", royaltiesDashboard?.rankings.dsp || [])}
                {renderRoyaltiesRankTable("Top Revenue by Store", royaltiesDashboard?.rankings.store || [])}
                {renderRoyaltiesRankTable("Ingresos por monetizacion", royaltiesDashboard?.rankings.monetization || [])}
                {renderRoyaltiesRankTable("Ingresos por origen", royaltiesDashboard?.rankings.content_origin || [])}
                {renderRoyaltiesRankTable("Ingresos por plan", royaltiesDashboard?.rankings.plan || [])}
                {renderRoyaltiesRankTable("Sales per Territory", royaltiesDashboard?.rankings.territory || [])}
                {renderRoyaltiesRankTable("Top Revenue by Label", royaltiesDashboard?.rankings.label || [])}
              </div>
            )}

            {royaltiesDashboardTab === "youtube" && (
              <>
                <div className="royalties-kpi-grid youtube-kpis">
                  <div className="royalties-kpi primary">
                    <span>YouTube net revenue</span>
                    <strong>{moneyCents(royaltiesDashboard?.youtube.totals.amount_usd || 0)}</strong>
                  </div>
                  <div className="royalties-kpi">
                    <span>Monetized units</span>
                    <strong>{Math.round(royaltiesDashboard?.youtube.totals.units || 0).toLocaleString("es-AR")}</strong>
                  </div>
                  <div className="royalties-kpi">
                    <span>Videos / assets</span>
                    <strong>{(royaltiesDashboard?.youtube.totals.titles || 0).toLocaleString("es-AR")}</strong>
                  </div>
                  <div className="royalties-kpi">
                    <span>Artistas</span>
                    <strong>{(royaltiesDashboard?.youtube.totals.artists || 0).toLocaleString("es-AR")}</strong>
                  </div>
                </div>
                <div className="royalties-rank-grid">
                  {renderRoyaltiesRankTable("Ingresos por monetizacion", royaltiesDashboard?.youtube.monetization || [])}
                  {renderRoyaltiesRankTable("Ingresos por origen", royaltiesDashboard?.youtube.content_origin || [])}
                  {renderRoyaltiesRankTable("Ingresos por plan", royaltiesDashboard?.youtube.plan || [])}
                  {renderRoyaltiesRankTable("Revenue by Territory", royaltiesDashboard?.youtube.territory || [])}
                  {renderRoyaltiesRankTable("Top YouTube Assets", royaltiesDashboard?.youtube.title || [])}
                </div>
              </>
            )}
          </section>
        )}

        {view === "digital-income" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Ingresos Digitales</h1>
                <p>Lectura directa de los statements: ingresos reales informados por las distribuidoras, sin aplicar reglas de negocio, splits, comisiones, contratos ni estado del catalogo.</p>
              </div>
              <button type="button" onClick={loadDigitalIncome} disabled={digitalIncomeLoading}>
                {digitalIncomeLoading ? "Cargando..." : "Actualizar"}
              </button>
            </div>

            <div className="period-controls catalog-controls">
              <div>
                <label htmlFor="digital_income_artist">Artista / keyword</label>
                <input
                  id="digital_income_artist"
                  value={digitalIncomeArtistKeyword}
                  onChange={(event) => setDigitalIncomeArtistKeyword(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      loadDigitalIncome();
                    }
                  }}
                  placeholder="Ej: Gusty, Aneley, Candu"
                />
              </div>
              <div>
                <label htmlFor="digital_income_source">Distribuidora</label>
                <select
                  id="digital_income_source"
                  value={digitalIncomeSource}
                  onChange={(event) => {
                    setDigitalIncomeSource(event.target.value);
                    setDigitalIncomeAccount("");
                  }}
                >
                  <option value="">Todas</option>
                  {digitalIncome?.options.sources.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="digital_income_account">Subcompañía</label>
                <select
                  id="digital_income_account"
                  value={digitalIncomeAccount}
                  onChange={(event) => setDigitalIncomeAccount(event.target.value)}
                >
                  <option value="">Todas</option>
                  {digitalIncomeAccountOptions.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>
              <PeriodControl
                id="digital_income_period"
                label="Periodo"
                profile="dashboard_period"
                selection={digitalIncomePeriod}
                presets={["last_6_months", "last_12_months", "all"]}
                onChange={setDigitalIncomePeriod}
                helperText="Por defecto muestra ultimos 6 meses. Todo carga el historico disponible."
              />
              <button type="button" onClick={loadDigitalIncome} disabled={digitalIncomeLoading}>
                Buscar
              </button>
            </div>

            <div className="control-dashboard">
              <div>
                <span>Total USD</span>
                <strong>{moneyCents(digitalIncome?.totals.total_usd || 0)}</strong>
              </div>
              <div>
                <span>Filas</span>
                <strong>{(digitalIncome?.total || 0).toLocaleString("es-AR")}</strong>
              </div>
              <div>
                <span>Meses</span>
                <strong>{digitalIncome?.totals.months || 0}</strong>
              </div>
              <div>
                <span>Distribuidoras</span>
                <strong>{digitalIncome?.totals.sources || 0}</strong>
              </div>
              <div>
                <span>Subcompañías</span>
                <strong>{digitalIncome?.totals.accounts || 0}</strong>
              </div>
              <div>
                <span>Rango</span>
                <strong>{digitalIncome?.totals.first_month || "-"} / {digitalIncome?.totals.last_month || "-"}</strong>
              </div>
            </div>

            <div className="period-meta">
              <strong>Vista</strong>
              <span>Ingresos reales agrupados por distribuidora/cuenta</span>
              <strong>Fuente</strong>
              <span>{digitalIncome?.options.first_month || "-"} a {digitalIncome?.options.last_month || "-"}</span>
              <strong>Reglas</strong>
              <span>Sin comisiones internas ni capa de negocio</span>
            </div>

            <div className="section-heading compact-heading">
              <div>
                <h2>Últimos meses por distribuidora</h2>
                <p>
                  Cada fila es una distribuidora/subcompañía. Las columnas muestran los meses del rango aplicado
                  {digitalIncomeArtistKeyword.trim() ? ` para la búsqueda "${digitalIncomeArtistKeyword.trim()}".` : "."}
                </p>
              </div>
            </div>

            <div className="summary-table-wrap">
              <table className="summary-table digital-income-matrix">
                <thead>
                  <tr>
                    <th>Distribuidora / cuenta</th>
                    {(digitalIncome?.matrix_months || []).map((month) => (
                      <th key={month}>{month}</th>
                    ))}
                    <th>Total</th>
                    <th>Artistas</th>
                  </tr>
                </thead>
                <tbody>
                  {digitalIncomeLoading && (
                    <tr>
                      <td colSpan={(digitalIncome?.matrix_months.length || 0) + 3}>Cargando ingresos...</td>
                    </tr>
                  )}
                  {!digitalIncomeLoading && digitalIncome?.matrix.length === 0 && (
                    <tr>
                      <td colSpan={(digitalIncome?.matrix_months.length || 0) + 3}>Sin datos para este filtro.</td>
                    </tr>
                  )}
                  {digitalIncome?.matrix.map((item) => (
                    <tr key={`${item.source}-${item.account}`}>
                      <td>
                        <strong>{item.source}</strong>
                        <span className="cell-note">{item.account}</span>
                        {item.has_share_in_out && <span className="cell-note">Incluye Share In/Out</span>}
                      </td>
                      {digitalIncome.matrix_months.map((month) => (
                        <td key={month}>{moneyCents(item.months[month] || 0)}</td>
                      ))}
                      <td><strong>{moneyCents(item.total_usd || 0)}</strong></td>
                      <td>{item.artists.toLocaleString("es-AR")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="section-heading compact-heading">
              <div>
                <h2>Detalle de respaldo</h2>
                <p>
                  Mostrando {digitalIncome?.items.length || 0} de {(digitalIncome?.total || 0).toLocaleString("es-AR")} grupos artista/mes.
                  {(digitalIncome?.total || 0) > (digitalIncome?.items.length || 0) ? " Ajusta los filtros para ver un recorte mas chico." : ""}
                </p>
              </div>
            </div>

            <div className="summary-table-wrap">
              <table className="summary-table">
                <thead>
                  <tr>
                    <th>Mes statement</th>
                    <th>Distribuidora</th>
                    <th>Subcompañía</th>
                    <th>Artista statement</th>
                    <th>Tema / referencia</th>
                    <th>Ingreso USD</th>
                    <th>Ingreso EUR</th>
                    <th>Share In/Out</th>
                  </tr>
                </thead>
                <tbody>
                  {digitalIncomeLoading && (
                    <tr>
                      <td colSpan={8}>Cargando ingresos...</td>
                    </tr>
                  )}
                  {!digitalIncomeLoading && digitalIncome?.items.length === 0 && (
                    <tr>
                      <td colSpan={8}>Sin filas para este filtro.</td>
                    </tr>
                  )}
                  {digitalIncome?.items.map((item, idx) => (
                    <tr key={`${item.statement_period}-${item.source}-${item.account}-${item.artist}-${idx}`}>
                      <td>{item.statement_period}</td>
                      <td>{item.source}</td>
                      <td>{item.account}</td>
                      <td>{item.artist || "-"}</td>
                      <td>{item.title || "-"}</td>
                      <td>{moneyCents(item.total_usd || 0)}</td>
                      <td>{item.total_eur ? eurCents(item.total_eur) : "-"}</td>
                      <td>
                        <span className={`status-pill ${item.has_share_in_out ? "warning" : "inactive"}`}>
                          {item.has_share_in_out ? "Si" : "No"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {view === "source-monitor" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Control de distribuidoras</h1>
                <p>Monitoreo operativo de descargas. Inactivo solo apaga alertas: no excluye datos historicos de reportes.</p>
              </div>
              <button type="button" onClick={loadSourceMonitor} disabled={sourceMonitorLoading}>
                {sourceMonitorLoading ? "Revisando..." : "Revisar todos"}
              </button>
            </div>

            {!currentUser?.canEdit && (
              <p className="field-help danger-text">
                Estas ingresado como viewer. Para procesar o cambiar alertas, entra con un usuario editor/admin.
              </p>
            )}

            <div className="control-dashboard">
              <div>
                <span>Fuentes</span>
                <strong>{sourceMonitor?.summary.total ?? 0}</strong>
              </div>
              <div>
                <span>Raw detectados</span>
                <strong>{sourceMonitorRawTotal}</strong>
              </div>
              <div>
                <span>Cargados</span>
                <strong>{sourceMonitorLoadedTotal}</strong>
              </div>
              <div className={sourceMonitorPendingTotal > 0 ? "warn" : ""}>
                <span>Pendientes reales</span>
                <strong>{sourceMonitorPendingTotal}</strong>
              </div>
              <div>
                <span>Ignorados validos</span>
                <strong>{sourceMonitorIgnoredTotal}</strong>
              </div>
              <div className={(sourceMonitor?.summary.alerts || 0) > 0 ? "danger" : ""}>
                <span>Alertas</span>
                <strong>{sourceMonitor?.summary.alerts ?? 0}</strong>
              </div>
              <div>
                <span>OK</span>
                <strong>{sourceMonitor?.summary.status_counts?.ok ?? 0}</strong>
              </div>
              <div>
                <span>Inactivas</span>
                <strong>{sourceMonitor?.summary.status_counts?.inactive ?? 0}</strong>
              </div>
            </div>

            {sourceMonitorLastProcess && (
              <div className="process-summary">
                <div className="section-heading">
                  <div>
                    <h2>Resumen procesado</h2>
                    <p>{sourceMonitorLastProcess.display_name} - {sourceMonitorLastProcess.processed_at}</p>
                  </div>
                  <div className="mini-total">
                    <span>Total USD</span>
                    <strong>{money(sourceMonitorLastProcess.total_amount_usd)}</strong>
                  </div>
                </div>
                <div className="period-meta">
                  <strong>Antes</strong>
                  <span>{sourceMonitorLastProcess.last_statement_before || "-"}</span>
                  <strong>Despues</strong>
                  <span>{sourceMonitorLastProcess.last_statement_after || "-"}</span>
                  <strong>Pendientes</strong>
                  <span>{sourceMonitorLastProcess.pending_files_after.length}</span>
                </div>
                <div className="muted">
                  Archivos: {sourceMonitorLastProcess.pending_files_before.length ? sourceMonitorLastProcess.pending_files_before.join(", ") : "sin archivos pendientes detectados"}
                </div>
                {sourceMonitorLastProcess.summary.length > 0 && (
                  <table className="summary-table compact-table">
                    <thead>
                      <tr>
                        <th>Statement</th>
                        <th>Filas</th>
                        <th>Archivos</th>
                        <th>USD</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sourceMonitorLastProcess.summary.map((row) => (
                        <tr key={row.statement_period}>
                          <td>{row.statement_period}</td>
                          <td>{row.rows.toLocaleString("es-AR")}</td>
                          <td>{row.files}</td>
                          <td>{money(row.amount_usd)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            <div className="summary-table-wrap">
              <table className="summary-table source-monitor-table">
                <thead>
                  <tr>
                    <th>Distribuidora</th>
                    <th>Estado carga</th>
                    <th>Archivos</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {(sourceMonitor?.items || []).map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.display_name}</strong>
                        <div className="muted">{item.source} / {item.account}</div>
                        <div className="muted">{item.input_path || "sin carpeta configurada"}</div>
                      </td>
                      <td>
                        <div><strong>Statement:</strong> {item.last_statement_period || "-"}</div>
                        <div className="muted">
                          {item.statement_age_months === null ? "sin edad" : `${item.statement_age_months} mes(es) atras`} / tolerancia {item.max_age_months}
                        </div>
                        <div className="muted">Filas mart: {item.rows_in_mart.toLocaleString("es-AR")}</div>
                      </td>
                      <td>
                        <div className="file-count-grid">
                          <span><strong>Raw</strong>{item.raw_files}</span>
                          <span><strong>Mart</strong>{item.files_in_mart}</span>
                          <span className={item.unprocessed_raw_count > 0 ? "warn-text" : ""}><strong>Pend.</strong>{item.unprocessed_raw_count}</span>
                          <span><strong>Ign.</strong>{item.ignored_raw_count || 0}</span>
                        </div>
                        {sourceMonitorInventoryLabel(item.raw_inventory_summary) && (
                          <div className="muted truncate-text" title={sourceMonitorInventoryLabel(item.raw_inventory_summary)}>
                            {sourceMonitorInventoryLabel(item.raw_inventory_summary)}
                          </div>
                        )}
                        {(item.ignored_raw_count || 0) > 0 && (
                          <div
                            className="muted truncate-text"
                            title={(item.ignored_raw_files || []).map((raw) => `${raw.file_name}: ${raw.reason}`).join("\n")}
                          >
                            Ignorados con regla: {item.ignored_raw_count}
                          </div>
                        )}
                        <div className="muted truncate-text" title={item.latest_raw_file || ""}>Ultimo raw: {item.latest_raw_file || "sin archivos"}</div>
                      </td>
                      <td>
                        <span className={`status-pill ${item.status}`}>{item.status}</span>
                        <div className={item.alert ? "danger-text" : "muted"}>{item.reason}</div>
                        {item.notes && <div className="muted">{item.notes}</div>}
                      </td>
                      <td>
                        <div className="stack-actions">
                          {item.portal_url && <a className="button secondary" href={item.portal_url} target="_blank" rel="noreferrer">Portal</a>}
                          <button
                            type="button"
                            disabled={sourceMonitorLoading}
                            title="Vuelve a comparar la carpeta input_raw contra lo procesado localmente."
                            onClick={loadSourceMonitor}
                          >
                            {sourceMonitorLoading ? "Revisando..." : "Revisar directorio"}
                          </button>
                          <button
                            type="button"
                            disabled={sourceMonitorLoading || !currentUser?.canEdit}
                            title={!currentUser?.canEdit ? "Necesitas entrar con usuario editor/admin." : "Marca que ya revisaste esta distribuidora."}
                            onClick={() => updateSourceMonitorItem(item.id, { last_manual_review_at: new Date().toISOString(), alert_silenced: false })}
                          >
                            Marcar revisada
                          </button>
                          <button
                            type="button"
                            disabled={sourceMonitorProcessingId !== "" || !currentUser?.canEdit || item.unprocessed_raw_count === 0}
                            title={!currentUser?.canEdit ? "Necesitas entrar con usuario editor/admin." : sourceMonitorProcessingId !== "" ? "Hay un procesamiento en curso." : item.unprocessed_raw_count === 0 ? "No hay archivos nuevos pendientes para procesar." : "Ejecuta el ingest nuevo local para esta distribuidora."}
                            onClick={() => processSourceMonitorItem(item.id)}
                          >
                            {sourceMonitorProcessingId === item.id ? "Procesando..." : item.unprocessed_raw_count === 0 ? "Sin pendientes" : "Procesar nuevos"}
                          </button>
                          <button
                            type="button"
                            disabled={sourceMonitorLoading || !currentUser?.canEdit}
                            title={!currentUser?.canEdit ? "Necesitas entrar con usuario editor/admin." : item.alert_silenced ? "Vuelve a activar la alerta para esta distribuidora." : "Oculta la alerta actual sin desactivar la data historica."}
                            onClick={() => updateSourceMonitorItem(item.id, { alert_silenced: !item.alert_silenced })}
                          >
                            {item.alert_silenced ? "Reactivar alerta" : "Silenciar alerta"}
                          </button>
                          <button
                            type="button"
                            disabled={sourceMonitorLoading || !currentUser?.canEdit}
                            title={!currentUser?.canEdit ? "Necesitas entrar con usuario editor/admin." : item.monitoring_active ? "Deja de monitorear alertas nuevas, sin excluir lo ya cargado." : "Reactiva el monitoreo de alertas."}
                            onClick={() => updateSourceMonitorItem(item.id, { monitoring_active: !item.monitoring_active, alert_silenced: item.monitoring_active ? true : false })}
                          >
                            {item.monitoring_active ? "No monitorear" : "Monitorear"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="cloud-publish-box">
              <div>
                <h2>Publicacion cloud</h2>
                <p>
                  Este paso debe hacerse despues de revisar los resumenes locales. Publicar cloud actualiza la web online con los datos analiticos validados.
                </p>
              </div>
              <button
                type="button"
                disabled={!canPublishMarts}
                title={publishDisabledReason}
                onClick={publishSourceMonitorMarts}
              >
                {sourceMonitorPublishing ? "Publicando..." : "Publicar datos analiticos"}
              </button>
              <p className="field-help">
                Flujo correcto: revisar carpetas, procesar pendientes reales, validar importes y catalogo local, y recien ahi publicar.
                {sourceMonitorPendingTotal > 0 ? ` Hay ${sourceMonitorPendingTotal} archivo(s) pendiente(s) real(es).` : " No hay pendientes reales detectados."}
              </p>
              {sourceMonitorPublishJob && sourceMonitorPublishJob.status !== "completed" && (
                <div className="publish-result">
                  <strong>Publicacion en curso</strong>
                  <span>Estado: {sourceMonitorPublishJob.status} / {sourceMonitorPublishJob.stage}</span>
                  <span>Job: {sourceMonitorPublishJob.job_id}</span>
                </div>
              )}
              {sourceMonitorLastPublish && (
                <div className="publish-result">
                  <strong>Ultima publicacion: {sourceMonitorLastPublish.published_at}</strong>
                  <span>{sourceMonitorLastPublish.bucket}/{sourceMonitorLastPublish.prefix}</span>
                  <span>
                    {sourceMonitorLastPublish.uploaded.map((file) => `${file.file_name} (${file.size_mb.toFixed(1)} MB)`).join(" · ")}
                  </span>
                </div>
              )}
            </div>
          </section>
        )}

        {view === "catalog" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Catalogo General</h1>
                <p>Base maestra deduplicada desde statements. Los cambios de activo/inactivo no modifican los crudos.</p>
              </div>
              <div className="button-row">
                <button type="button" onClick={() => loadCatalog(0)} disabled={catalogLoading}>
                  {catalogLoading ? "Cargando..." : "Actualizar"}
                </button>
              </div>
            </div>

            <div className="period-controls catalog-controls">
              <div>
                <label htmlFor="catalog_source">Distribuidora</label>
                <select
                  id="catalog_source"
                  value={catalogSource}
                  onChange={(event) => setCatalogSource(event.target.value)}
                >
                  <option value="">Todas</option>
                  {catalogData?.options.sources.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="catalog_account">Cuenta</label>
                <select
                  id="catalog_account"
                  value={catalogAccount}
                  onChange={(event) => setCatalogAccount(event.target.value)}
                >
                  <option value="">Todas</option>
                  {catalogData?.options.accounts.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="catalog_artist">Artista</label>
                <select
                  id="catalog_artist"
                  value={catalogArtist}
                  onChange={(event) => setCatalogArtist(event.target.value)}
                >
                  <option value="">Todos</option>
                  {catalogData?.options.artists.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="catalog_keyword">Palabra clave</label>
                <input
                  id="catalog_keyword"
                  value={catalogKeyword}
                  onChange={(event) => setCatalogKeyword(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      loadCatalog(0);
                    }
                  }}
                  placeholder="tema, artista o ISRC"
                />
              </div>
              <div>
                <label htmlFor="catalog_label">Label</label>
                <select
                  id="catalog_label"
                  value={catalogLabel}
                  onChange={(event) => setCatalogLabel(event.target.value)}
                >
                  <option value="">Todos</option>
                  <option value="__missing__">No identificadas</option>
                  {catalogData?.options.labels.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>
              <PeriodControl
                id="catalog_period"
                label="Actividad"
                profile="activity_window"
                selection={catalogPeriod}
                onChange={setCatalogPeriod}
                minMonth={catalogData?.options.first_month || undefined}
                maxMonth={catalogData?.options.last_month || undefined}
                helperText="Filtra obras con actividad en el mes o rango elegido."
              />
              <div>
                <label htmlFor="catalog_status">Estado</label>
                <select
                  id="catalog_status"
                  value={catalogStatus}
                  onChange={(event) => setCatalogStatus(event.target.value as "active" | "inactive" | "all")}
                >
                  <option value="active">Activos</option>
                  <option value="inactive">Inactivos</option>
                  <option value="all">Todos</option>
                </select>
              </div>
              <button type="button" onClick={() => loadCatalog(0)} disabled={catalogLoading}>
                Buscar
              </button>
            </div>

            <div className="control-dashboard">
              <div>
                <span>Items</span>
                <strong>{catalogData?.total.toLocaleString("es-AR") || 0}</strong>
              </div>
              <div>
                <span>Total USD</span>
                <strong>{money(catalogData?.totals.amount_usd || 0)}</strong>
              </div>
              <div>
                <span>Unidades</span>
                <strong>{Math.round(catalogData?.totals.units || 0).toLocaleString("es-AR")}</strong>
              </div>
              <div>
                <span>Rango fuente</span>
                <strong>{catalogData?.options.first_month || "-"} / {catalogData?.options.last_month || "-"}</strong>
              </div>
            </div>

            <div className="catalog-pagination">
              <span>
                Mostrando {catalogData ? catalogData.offset + 1 : 0}
                {" - "}
                {catalogData ? Math.min(catalogData.offset + catalogData.items.length, catalogData.total) : 0}
                {" de "}
                {catalogData?.total || 0}
              </span>
              <div className="button-row">
                <button
                  type="button"
                  className="secondary"
                  disabled={catalogLoading || catalogOffset === 0}
                  onClick={() => loadCatalog(Math.max(0, catalogOffset - catalogLimit))}
                >
                  Anterior
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={catalogLoading || !catalogData || catalogOffset + catalogLimit >= catalogData.total}
                  onClick={() => loadCatalog(catalogOffset + catalogLimit)}
                >
                  Siguiente
                </button>
              </div>
            </div>

            <div className="summary-table-wrap catalog-table-wrap">
              <table className="summary-table catalog-table">
                <thead>
                  <tr>
                    <th>Estado</th>
                    <th>Tema</th>
                    <th>Artista</th>
                    <th>ISRC / ID</th>
                    <th>Distribuidoras</th>
                    <th>Fechas</th>
                    <th>USD</th>
                    <th>Release</th>
                    <th>Label</th>
                    <th>Accion</th>
                  </tr>
                </thead>
                <tbody>
                  {catalogLoading && (
                    <tr>
                      <td colSpan={10}>Cargando catalogo...</td>
                    </tr>
                  )}
                  {!catalogLoading && catalogData?.items.length === 0 && (
                    <tr>
                      <td colSpan={10}>Sin items para este filtro.</td>
                    </tr>
                  )}
                  {catalogData?.items.map((item) => (
                    <tr key={item.catalog_key} className={item.include_in_reports === false ? "inactive-row" : ""}>
                      <td>
                        <span className={`status-pill ${item.include_in_reports !== false ? "ok" : "inactive"}`}>
                          {item.include_in_reports !== false ? "entra en reportes" : "fuera de reportes"}
                        </span>
                        {item.catalog_business_status && <span className="cell-note">{item.catalog_business_status}</span>}
                        {item.status_notes && <span className="cell-note">{item.status_notes}</span>}
                      </td>
                      <td>
                        <strong>{item.track_title || "Sin titulo"}</strong>
                        {item.title_variants && item.title_variants !== item.track_title && (
                          <span className="cell-note truncate-text" title={item.title_variants}>Variantes: {item.title_variants}</span>
                        )}
                      </td>
                      <td>
                        {item.artist_statement || "Sin artista"}
                        {item.artist_variants && item.artist_variants !== item.artist_statement && (
                          <span className="cell-note truncate-text" title={item.artist_variants}>Variantes: {item.artist_variants}</span>
                        )}
                      </td>
                      <td>
                        <strong>{item.asset_isrc || item.track_id || "-"}</strong>
                        <span className="cell-note">{item.catalog_key}</span>
                      </td>
                      <td>
                        <strong>{item.sources || "-"}</strong>
                        <span className="cell-note">{item.accounts || "-"}</span>
                        {item.content_types && <span className="cell-note">{item.content_types}</span>}
                      </td>
                      <td>
                        <strong>{item.first_transaction_month || "-"} / {item.last_transaction_month || "-"}</strong>
                      </td>
                      <td>{money(item.amount_usd || 0)}</td>
                      <td>
                        {item.external_release_date || "-"}
                        {item.external_match_url && (
                          <a className="cell-note" href={item.external_match_url} target="_blank" rel="noreferrer">metadata</a>
                        )}
                      </td>
                      <td>
                        {catalogLabelEditKey === item.catalog_key ? (
                          <div className="inline-edit">
                            <input
                              value={catalogLabelDraft}
                              onChange={(event) => setCatalogLabelDraft(event.target.value)}
                              onKeyDown={(event) => {
                                if (event.key === "Enter") {
                                  event.preventDefault();
                                  updateCatalogLabel(item);
                                }
                                if (event.key === "Escape") {
                                  setCatalogLabelEditKey("");
                                  setCatalogLabelDraft("");
                                }
                              }}
                              autoFocus
                            />
                            <button
                              type="button"
                              className="secondary"
                              disabled={catalogLabelSaving === item.catalog_key}
                              onClick={() => updateCatalogLabel(item)}
                            >
                              Guardar
                            </button>
                            <button
                              type="button"
                              className="secondary"
                              disabled={catalogLabelSaving === item.catalog_key}
                              onClick={() => {
                                setCatalogLabelEditKey("");
                                setCatalogLabelDraft("");
                              }}
                            >
                              Cancelar
                            </button>
                          </div>
                        ) : currentUser?.canEdit ? (
                          <button
                            type="button"
                            className="metadata-edit-chip"
                            onClick={() => {
                              setCatalogLabelEditKey(item.catalog_key);
                              setCatalogLabelDraft(item.label_normalized || item.label_normalized_auto || item.external_label || "");
                            }}
                          >
                            {item.label_normalized || "-"}
                          </button>
                        ) : (
                          <strong>{item.label_normalized || "-"}</strong>
                        )}
                        {item.label_normalized_override && <span className="cell-note">manual</span>}
                        {item.external_label && item.external_label !== item.label_normalized && (
                          <span className="cell-note truncate-text" title={item.external_label}>Original: {item.external_label}</span>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="secondary"
                          disabled={!currentUser?.canEdit}
                          title={!currentUser?.canEdit ? "Necesitas usuario editor/admin." : item.active ? "Marcar este item como inactivo." : "Reactivar este item."}
                          onClick={() => updateCatalogStatus(item, !item.active)}
                        >
                          {item.active ? "Inactivar" : "Activar"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {view === "distributor-config" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Configurador distribuidoras</h1>
                <p>Politicas de negocio para catalogo, statements, caja y reportes.</p>
              </div>
              <button type="button" onClick={loadDistributorConfig} disabled={distributorConfigLoading}>
                {distributorConfigLoading ? "Cargando..." : "Actualizar"}
              </button>
            </div>

            <div className="control-dashboard">
              <div>
                <span>Cuentas</span>
                <strong>{distributorConfig?.summary.accounts || 0}</strong>
              </div>
              <div>
                <span>Diccionario</span>
                <strong>{distributorConfig?.summary.dictionary_entries || 0}</strong>
              </div>
              <div>
                <span>Fechas corte</span>
                <strong>{distributorConfig?.summary.contract_cutoffs || 0}</strong>
              </div>
              <div>
                <span>Templates</span>
                <strong>{distributorConfig?.summary.report_templates || 0}</strong>
              </div>
              <div>
                <span>Modo</span>
                <strong>{distributorConfig?.mode || "seed"}</strong>
              </div>
            </div>

            <div className="period-controls catalog-controls">
              <div>
                <label htmlFor="distributor_config_source">Distribuidora</label>
                <select
                  id="distributor_config_source"
                  value={distributorConfigSource}
                  onChange={(event) => {
                    setDistributorConfigSource(event.target.value);
                    setDistributorConfigAccountId("");
                  }}
                >
                  <option value="">Todas</option>
                  {distributorConfigSources.map((source) => (
                    <option key={source} value={source}>{source}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="distributor_config_account">Cuenta</label>
                <select
                  id="distributor_config_account"
                  value={selectedDistributorAccount?.policy_id || ""}
                  onChange={(event) => setDistributorConfigAccountId(event.target.value)}
                >
                  {distributorConfigAccounts.map((account) => (
                    <option key={account.policy_id} value={account.policy_id}>
                      {account.display_name}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                className="secondary"
                disabled={!selectedDistributorAccount}
                onClick={() => {
                  if (!selectedDistributorAccount) return;
                  setCatalogSource(selectedDistributorAccount.source);
                  setCatalogAccount(selectedDistributorAccount.account);
                  setCatalogStatus("all");
                  setView("catalog");
                }}
              >
                Ver obras en catalogo
              </button>
            </div>

            {!distributorConfig && !distributorConfigLoading && (
              <p className="field-help">Sin configuracion cargada todavia.</p>
            )}

            {selectedDistributorAccount && (
              <>
                <section className="subpanel">
                  <div className="subpanel-title">
                    <div>
                      <h2>Personalizacion de reportes</h2>
                      <p>Ajusta el neto ya informado por la distribuidora. No modifica el dato real ni los marts.</p>
                    </div>
                    <label className="inline-check">
                      <input
                        type="checkbox"
                        checked={distributorPersonalizationEnabled}
                        onChange={(event) => setDistributorPersonalizationEnabled(event.target.checked)}
                        disabled={!currentUser?.canEdit || distributorPersonalizationSaving}
                      />
                      Aplicar en reportes
                    </label>
                  </div>
                  <div className="policy-summary">
                    <div>
                      <span>Neto real de cuenta</span>
                      <strong>{money(selectedDistributorRealAmount)}</strong>
                    </div>
                    <div>
                      <span>Ajuste VPO</span>
                      <input
                        id={`distributor_adjustment_${selectedDistributorAccount.policy_id}`}
                        inputMode="decimal"
                        value={distributorAdjustmentDrafts[selectedDistributorAccount.policy_id] ?? String(selectedDistributorAccount.report_net_adjustment_pct || 0)}
                        onChange={(event) => updateDistributorAdjustment(selectedDistributorAccount.policy_id, event.target.value)}
                        disabled={!currentUser?.canEdit || distributorPersonalizationSaving}
                        aria-label="Porcentaje de ajuste del neto para reportes"
                      />
                      <small>% sobre neto</small>
                    </div>
                    <div>
                      <span>Neto personalizado</span>
                      <strong>{money(selectedDistributorAdjustedAmount)}</strong>
                    </div>
                    <div>
                      <span>Estado</span>
                      <strong>{distributorPersonalizationEnabled ? "Activo" : "Inactivo"}</strong>
                    </div>
                  </div>
                  <div className="button-row">
                    <button
                      type="button"
                      onClick={saveDistributorPersonalization}
                      disabled={!currentUser?.canEdit || distributorPersonalizationSaving || !distributorConfig}
                    >
                      {distributorPersonalizationSaving ? "Guardando..." : "Guardar porcentajes"}
                    </button>
                  </div>
                  <p className="field-help">
                    Si esta apagado, los reportes usan el neto real. Si esta prendido, cada cuenta usa su porcentaje configurado.
                  </p>
                </section>

                <div className="grid">
                  <section className="subpanel">
                    <div className="subpanel-title">
                      <div>
                        <h2>Decision de cuenta</h2>
                        <p>{selectedDistributorAccount.source} / {selectedDistributorAccount.account}</p>
                      </div>
                      <span className={`status-pill ${cashModeClass(selectedDistributorAccount.cash_view_enabled)}`}>
                        {accountCashLabel(selectedDistributorAccount)}
                      </span>
                    </div>
                    <div className="policy-summary">
                      <div>
                        <span>Tipo</span>
                        <strong>{selectedDistributorAccount.account_type}</strong>
                      </div>
                      <div>
                        <span>Ownership</span>
                        <strong>{selectedDistributorAccount.ownership_default}</strong>
                      </div>
                      <div>
                        <span>Base temporal</span>
                        <strong>{flagLabel(selectedDistributorAccount.default_time_basis)}</strong>
                      </div>
                      <div>
                        <span>Monitoreo</span>
                        <strong>{flagLabel(selectedDistributorAccount.monitoring_active)}</strong>
                      </div>
                    </div>
                    <div className="policy-flags">
                      <span>Catalogo: {flagLabel(selectedDistributorAccount.catalog_view_enabled)}</span>
                      <span>Statement: {flagLabel(selectedDistributorAccount.statement_view_enabled)}</span>
                      <span>{accountCashLabel(selectedDistributorAccount)}</span>
                    </div>
                    {selectedDistributorAccount.cash_view_description && (
                      <p className="field-help">{selectedDistributorAccount.cash_view_description}</p>
                    )}
                    <p className="field-help">{selectedDistributorAccount.notes}</p>
                  </section>

                  <section className="subpanel">
                    <div className="subpanel-title">
                      <div>
                        <h2>Regla contractual</h2>
                        <p>Criterio humano para separar catalogo propio, ajeno o pendiente de revision.</p>
                      </div>
                    </div>
                    {selectedDistributorAccount.contract_cutoff ? (
                      <>
                        <div className="policy-summary">
                          <div>
                            <span>Entidad</span>
                            <strong>{selectedDistributorAccount.contract_cutoff.business_entity}</strong>
                          </div>
                          <div>
                            <span>Fecha real</span>
                            <strong>{selectedDistributorAccount.contract_cutoff.contract_start_date || "No cargada"}</strong>
                          </div>
                          <div>
                            <span>Mes de corte</span>
                            <strong>{selectedDistributorAccount.contract_cutoff.contract_start_month || "-"}</strong>
                          </div>
                          <div>
                            <span>Base de decision</span>
                            <strong>{flagLabel(selectedDistributorAccount.contract_cutoff.cutoff_basis)}</strong>
                          </div>
                          <div>
                            <span>Estado fecha</span>
                            <strong>{flagLabel(selectedDistributorAccount.contract_cutoff.date_status)}</strong>
                          </div>
                          <div>
                            <span>Confianza</span>
                            <strong>{flagLabel(selectedDistributorAccount.contract_cutoff.confidence)}</strong>
                          </div>
                        </div>
                        <div className="rule-flow">
                          <div>
                            <span>Contenido anterior</span>
                            <strong>{flagLabel(selectedDistributorAccount.contract_cutoff.old_content_policy)}</strong>
                          </div>
                          <div>
                            <span>Contenido nuevo</span>
                            <strong>{flagLabel(selectedDistributorAccount.contract_cutoff.new_content_policy)}</strong>
                          </div>
                          <div>
                            <span>Contenido dudoso</span>
                            <strong>{flagLabel(selectedDistributorAccount.contract_cutoff.unknown_content_policy)}</strong>
                          </div>
                        </div>
                        <p className="field-help">
                          Evidencia: {selectedDistributorAccount.contract_cutoff.evidence_terms.join(", ")}
                          {" "}({selectedDistributorAccount.contract_cutoff.evidence_first_transaction_month || "-"} transaction / {selectedDistributorAccount.contract_cutoff.evidence_first_statement_period || "-"} statement).
                        </p>
                        <p className="field-help">{selectedDistributorAccount.contract_cutoff.notes}</p>
                      </>
                    ) : (
                      <p className="field-help">Esta cuenta no tiene fecha contractual configurada.</p>
                    )}
                  </section>
                </div>

                <section className="subpanel">
                  <div className="subpanel-title">
                    <div>
                      <h2>Impacto de esta seleccion</h2>
                      <p>Numeros directos de {selectedDistributorAccount.source} / {selectedDistributorAccount.account}, sin sumar otras cuentas relacionadas.</p>
                    </div>
                  </div>
                  <div className="control-dashboard compact-dashboard">
                    <div>
                      <span>Obras</span>
                      <strong>{selectedDistributorAccount.account_impact_stats?.works || 0}</strong>
                    </div>
                    <div>
                      <span>Filas song level</span>
                      <strong>{selectedDistributorAccount.account_impact_stats?.rows || 0}</strong>
                    </div>
                    <div>
                      <span>Generacion directa de cuenta</span>
                      <strong>{money(selectedDistributorAccount.account_impact_stats?.amount_usd || 0)}</strong>
                    </div>
                    <div>
                      <span>Unidades</span>
                      <strong>{Math.round(selectedDistributorAccount.account_impact_stats?.units || 0).toLocaleString("es-AR")}</strong>
                    </div>
                  </div>
                  <p className="field-help">
                    Periodo observado: {selectedDistributorAccount.account_impact_stats?.first_transaction_month || "-"}
                    {" "}a {selectedDistributorAccount.account_impact_stats?.last_transaction_month || "-"}.
                    {" "}Esta es la lectura directa de la cuenta seleccionada.
                  </p>
                  <div className="summary-table-wrap">
                    <table className="summary-table compact-table policy-table">
                      <thead>
                        <tr>
                          <th>Hoja / tipo</th>
                          <th>Obras</th>
                          <th>Filas</th>
                          <th>Generacion</th>
                          <th>Periodo</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(selectedDistributorAccount.account_impact_stats?.sheet_breakdown || []).map((sheet) => (
                          <tr key={sheet.source_sheet}>
                            <td><strong>{sheet.source_sheet}</strong></td>
                            <td>{sheet.works}</td>
                            <td>{sheet.rows}</td>
                            <td>{money(sheet.amount_usd)}</td>
                            <td>{sheet.first_transaction_month || "-"} a {sheet.last_transaction_month || "-"}</td>
                          </tr>
                        ))}
                        {(selectedDistributorAccount.account_impact_stats?.sheet_breakdown || []).length === 0 && (
                          <tr>
                            <td colSpan={5}>Sin datos directos para esta cuenta.</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>

                {selectedDistributorRulePreview?.enabled && (
                  <section className="subpanel">
                    <div className="subpanel-title">
                      <div>
                        <h2>Decision final de negocio</h2>
                        <p>Combina regla contractual y catalogo. Esta es la foto que deberia leer un reporte.</p>
                      </div>
                    </div>
                    <div className="control-dashboard compact-dashboard">
                      {(selectedDistributorRulePreview.final_summary || selectedDistributorRulePreview.summary).map((item) => (
                        <div key={item.status} className={item.status === "manual_review" || item.status === "excluded_by_catalog" ? "warn" : ""}>
                          <span>{finalDecisionLabel(item.status)}</span>
                          <strong>{money(item.amount_usd)}</strong>
                          <small>{item.works} obra(s) / {item.rows} fila(s)</small>
                        </div>
                      ))}
                    </div>
                    <div className="decision-rule-list">
                      <div>
                        <span>Regla contractual</span>
                        <strong>
                          Corte {selectedDistributorRulePreview.contract_start_date || selectedDistributorRulePreview.contract_start_month || "-"}
                        </strong>
                        <small>{flagLabel(selectedDistributorRulePreview.cutoff_basis)}</small>
                      </div>
                      <div>
                        <span>Regla de catalogo</span>
                        <strong>Catalogo inactivo excluye siempre</strong>
                        <small>Si una obra esta fuera de reportes, pisa la inclusion contractual.</small>
                      </div>
                      <div>
                        <span>Resultado</span>
                        <strong>Reportable final</strong>
                        <small>Esta lectura sigue siendo read-only; no modifica reportes ni marts.</small>
                      </div>
                    </div>
                    <div className="subpanel-title mini-title">
                      <div>
                        <h3>Alertas que requieren mirada</h3>
                        <p>Solo aparecen conflictos o casos incompletos. La lista completa queda plegada.</p>
                      </div>
                    </div>
                    {(selectedDistributorRulePreview.alerts || []).length > 0 ? (
                      <div className="summary-table-wrap">
                        <table className="summary-table rule-alert-table">
                          <thead>
                            <tr>
                              <th>Estado final</th>
                              <th>Obra</th>
                              <th>Regla</th>
                              <th>Catalogo</th>
                              <th>Generacion</th>
                              <th>Motivo</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(selectedDistributorRulePreview.alerts || []).map((item, index) => (
                              <tr key={`alert-${item.final_status || item.status}-${item.asset_isrc || item.track_title}-${index}`}>
                                <td>
                                  <span className={`status-pill ${finalDecisionClass(item.final_status || item.status)}`}>
                                    {finalDecisionLabel(item.final_status || item.status)}
                                  </span>
                                </td>
                                <td>
                                  <strong>{item.track_title || "-"}</strong>
                                  <span className="cell-note">{item.artist || "-"}</span>
                                  {item.asset_isrc && <span className="cell-note">{item.asset_isrc}</span>}
                                </td>
                                <td>{ruleStatusLabel(item.rule_status || item.status)} / {item.decision_basis || "-"}</td>
                                <td>
                                  {item.catalog_key || "Sin match"}
                                  <span className="cell-note">
                                    activo: {item.catalog_active === false ? "no" : item.catalog_active === true ? "si" : "-"}
                                    {" "}reportes: {item.catalog_include_in_reports === false ? "no" : item.catalog_include_in_reports === true ? "si" : "-"}
                                  </span>
                                </td>
                                <td>{money(item.amount_usd)}</td>
                                <td>{item.final_reason || item.reason}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="field-help ok-help">Sin alertas: la regla contractual y el catalogo no muestran conflictos en esta cuenta.</p>
                    )}
                    <details className="audit-details">
                      <summary>Ver auditoria completa ({selectedDistributorRulePreview.items.length} principales por importe)</summary>
                      <div className="summary-table-wrap">
                        <table className="summary-table rule-preview-table">
                          <thead>
                            <tr>
                              <th>Final</th>
                              <th>Regla</th>
                              <th>Obra</th>
                              <th>Hoja</th>
                              <th>Base</th>
                              <th>Release</th>
                              <th>Generacion</th>
                              <th>Motivo</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedDistributorRulePreview.items.map((item, index) => (
                              <tr key={`${item.final_status || item.status}-${item.asset_isrc || item.track_title}-${index}`}>
                                <td>
                                  <span className={`status-pill ${finalDecisionClass(item.final_status || item.status)}`}>
                                    {finalDecisionLabel(item.final_status || item.status)}
                                  </span>
                                </td>
                                <td>
                                  <span className={`status-pill ${ruleStatusClass(item.rule_status || item.status)}`}>
                                    {ruleStatusLabel(item.rule_status || item.status)}
                                  </span>
                                </td>
                                <td>
                                  <strong>{item.track_title || "-"}</strong>
                                  <span className="cell-note">{item.artist || "-"}</span>
                                  {item.asset_isrc && <span className="cell-note">{item.asset_isrc}</span>}
                                  {item.catalog_key && <span className="cell-note">{item.catalog_key}</span>}
                                </td>
                                <td>{item.source_sheet}</td>
                                <td>{item.decision_basis || "-"}</td>
                                <td>
                                  {item.external_release_date || "-"}
                                  {item.external_label && <span className="cell-note">{item.external_label}</span>}
                                </td>
                                <td>{money(item.amount_usd)}</td>
                                <td>{item.final_reason || item.reason}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  </section>
                )}

                <section className="subpanel">
                  <div className="subpanel-title">
                    <div>
                      <h2>Generacion total de obras relacionadas</h2>
                      <p>Vista ampliada de catalogo: obras donde aparece esta cuenta, aunque tambien generen en otras fuentes.</p>
                    </div>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => {
                        setCatalogSource(selectedDistributorAccount.source);
                        setCatalogAccount(selectedDistributorAccount.account);
                        setCatalogStatus("all");
                        setView("catalog");
                      }}
                    >
                      Abrir catalogo filtrado
                    </button>
                  </div>
                  <div className="control-dashboard compact-dashboard">
                    <div><span>Obras relacionadas</span><strong>{selectedDistributorAccount.catalog_stats?.works || 0}</strong></div>
                    <div><span>Activas</span><strong>{selectedDistributorAccount.catalog_stats?.active || 0}</strong></div>
                    <div className={(selectedDistributorAccount.catalog_stats?.inactive || 0) > 0 ? "warn" : ""}><span>Inactivas</span><strong>{selectedDistributorAccount.catalog_stats?.inactive || 0}</strong></div>
                    <div><span>Release date</span><strong>{selectedDistributorAccount.catalog_stats?.release_dates || 0}</strong></div>
                    <div className={(selectedDistributorAccount.catalog_stats?.missing_release_dates || 0) > 0 ? "warn" : ""}><span>Sin release</span><strong>{selectedDistributorAccount.catalog_stats?.missing_release_dates || 0}</strong></div>
                    <div><span>Label</span><strong>{selectedDistributorAccount.catalog_stats?.labels || 0}</strong></div>
                    <div><span>Total obras relacionadas</span><strong>{money(selectedDistributorAccount.catalog_stats?.amount_usd || 0)}</strong></div>
                  </div>
                  <p className="field-help">
                    Periodo observado: {selectedDistributorAccount.catalog_stats?.first_transaction_month || "-"}
                    {" "}a {selectedDistributorAccount.catalog_stats?.last_transaction_month || "-"}.
                    {" "}Estos numeros pueden incluir otras cuentas/fuentes relacionadas a las mismas obras.
                  </p>
                  {Math.abs((selectedDistributorAccount.catalog_stats?.amount_usd || 0) - (selectedDistributorAccount.account_impact_stats?.amount_usd || 0)) > 0.01 && (
                    <p className="field-help compact-note">
                      La diferencia contra la cuenta directa es {money((selectedDistributorAccount.catalog_stats?.amount_usd || 0) - (selectedDistributorAccount.account_impact_stats?.amount_usd || 0))}
                      {" "}porque algunas obras tambien aparecen en otras fuentes o cuentas.
                    </p>
                  )}
                </section>

                <section className="subpanel">
                  <div className="subpanel-title">
                    <div>
                      <h2>Reglas por hoja</h2>
                      <p>Que entra a catalogo, reportes y caja para cada hoja original.</p>
                    </div>
                  </div>
                  <div className="summary-table-wrap">
                    <table className="summary-table compact-table policy-table">
                      <thead>
                        <tr>
                          <th>Hoja / tipo</th>
                          <th>Catalogo</th>
                          <th>Statement</th>
                          <th>Caja</th>
                          <th>Base</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(selectedDistributorAccount.sheet_rules).map(([sheet, rules]) => (
                          <tr key={sheet}>
                            <td><strong>{sheet}</strong></td>
                            <td>{flagLabel(rules.catalog_view)}</td>
                            <td>{flagLabel(rules.statement_view)}</td>
                            <td>
                              <span className={`status-pill ${cashModeClass(rules.cash_view)}`}>
                                {flagLabel(rules.cash_view)}
                              </span>
                            </td>
                            <td>{flagLabel(rules.revenue_basis)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="subpanel">
                  <div className="subpanel-title">
                    <div>
                      <h2>Diccionario del statement</h2>
                      <p>Explicacion humana de cada hoja original, columnas usadas y riesgos conocidos.</p>
                    </div>
                  </div>
                  <div className="summary-table-wrap dictionary-wrap">
                    <table className="summary-table">
                      <thead>
                        <tr>
                          <th>Hoja / archivo</th>
                          <th>Significado</th>
                          <th>Tipo</th>
                          <th>Columnas clave</th>
                          <th>Decision</th>
                          <th>Riesgos</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedDictionaryEntries.map((entry) => (
                          <tr key={`${entry.source}-${entry.account}-${entry.raw_sheet_or_file_type}`}>
                            <td>
                              <strong>{entry.raw_sheet_or_file_type}</strong>
                              <span className="cell-note">{entry.human_name}</span>
                            </td>
                            <td>{entry.human_description}</td>
                            <td>{entry.business_meaning}</td>
                            <td>
                              <div><strong>Importe:</strong> {entry.amount_column || "-"}</div>
                              <div><strong>Periodo:</strong> {entry.period_column || "-"}</div>
                              <div><strong>ID:</strong> {entry.identifier_columns.join(", ") || "-"}</div>
                            </td>
                            <td>
                              <div>Catalogo: {flagLabel(entry.default_catalog_view)}</div>
                              <div>Statement: {flagLabel(entry.default_statement_view)}</div>
                              <div>Caja: {flagLabel(entry.default_cash_view)}</div>
                              <span className="cell-note">{entry.decision_reason}</span>
                            </td>
                            <td>{entry.known_risks}</td>
                          </tr>
                        ))}
                        {selectedDictionaryEntries.length === 0 && (
                          <tr>
                            <td colSpan={6}>Sin diccionario asociado a esta cuenta.</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="subpanel">
                  <h2>Impacto en reportes</h2>
                  <p className="field-help">Panel secundario solo lectura. Sirve para entender donde podria impactar esta cuenta; no configura reglas.</p>
                  <div className="summary-table-wrap">
                    <table className="summary-table compact-table">
                      <thead>
                        <tr>
                          <th>Template</th>
                          <th>Familia</th>
                          <th>Periodo</th>
                          <th>Catalogo</th>
                          <th>Politica cuenta</th>
                          <th>Notas</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedReportImpacts.map((template) => (
                          <tr key={template.template_key}>
                            <td><strong>{template.title}</strong></td>
                            <td>{template.report_family}</td>
                            <td>{template.time_basis}</td>
                            <td>{flagLabel(template.uses_catalog_status)}</td>
                            <td>{flagLabel(template.uses_account_policy)}</td>
                            <td>{template.notes}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </>
            )}
          </section>
        )}

        {view === "booking-summary" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Resumen booking</h1>
                <p>Ingreso Indyana por artista y mes, comisiones aplicables y neto real de booking.</p>
              </div>
              <div className="button-row">
                <button type="button" className="secondary" onClick={openBookingWorkspace}>Volver a Booking</button>
                <button type="button" onClick={loadBookingSummary} disabled={bookingSummaryLoading}>
                  {bookingSummaryLoading ? "Actualizando..." : "Actualizar"}
                </button>
              </div>
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
                <span>Comisiones</span>
                <strong>{ars(bookingSummary?.totals.commission_total || 0)}</strong>
              </div>
              <div>
                <span>Neto Indyana</span>
                <strong>{ars(bookingSummary?.totals.indyana_net_total || 0)}</strong>
              </div>
            </div>

            <p className="field-help">
              Las comisiones se calculan show por show segun reglas activas. Un show excluido de comision general no genera deuda, salvo que una regla particular indique que esa persona cobra igual.
            </p>

            <div className="summary-table-wrap">
              <table className="summary-table">
                <thead>
                  <tr>
                    <th>Artista</th>
                    <th>Shows</th>
                    <th>Indyana</th>
                    <th>Comisiones</th>
                    <th>Neto Indyana</th>
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
                      <td>{ars(item.commission_total || 0)}</td>
                      <td><strong>{ars(item.indyana_net_total ?? item.indyana_total)}</strong></td>
                      {bookingSummary.months.map((month) => {
                        const monthItem = item.months[month];
                        return (
                          <td key={`${item.artist}-${month}`}>
                            {monthItem ? (
                              <>
                                <strong>{ars(monthItem.indyana_total)}</strong>
                                {(monthItem.commission_total || 0) > 0 && (
                                  <span className="cell-note amount-warn">Neto {ars(monthItem.indyana_net_total)}</span>
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

        {view === "commissions" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Comisiones</h1>
                <p>Configura porcentajes por empleado y revisa la liquidacion segun las reglas aplicables de booking.</p>
              </div>
              <button
                type="button"
                onClick={saveCommissionRules}
                disabled={
                  !commissionsEmployee
                  || !selectedCommissionPermission?.can_access
                  || !canEditModule("booking_commissions")
                  || !commissionDirtyEmployees[commissionsEmployee]
                  || commissionRulesMissingPriority.length > 0
                  || commissionRulesLoading
                  || commissionRulesSaving
                }
              >
                {commissionRulesSaving ? "Guardando..." : "Guardar configuracion"}
              </button>
            </div>
            {commissionsEmployee && commissionRulesMissingPriority.length > 0 && (
              <p className="field-help amount-warn">
                Elegi orden de cobro para: {commissionRulesMissingPriority.map((rule) => rule.artist).join(", ")}.
              </p>
            )}

            <div className="row three">
              <div>
                <label htmlFor="commission_employee">Empleado</label>
                <select
                  id="commission_employee"
                  value={commissionsEmployee}
                  disabled={commissionEmployeesLoading}
                  onChange={(event) => {
                    setCommissionsEmployee(event.target.value);
                    setCommissionSettlementSearch("");
                  }}
                >
                  <option value="">{commissionEmployeesLoading ? "Cargando empleados..." : "Seleccionar empleado"}</option>
                  {commissionEmployeeRecords
                    .filter((employee) => employee.active)
                    .map((employee) => (
                    <option key={employee.id} value={String(employee.id)}>{employee.display_name}</option>
                  ))}
                </select>
                <p className="field-help">
                  La lista viene de empleados activos. Los artistas salen del permiso del modulo Comisiones.
                </p>
              </div>
              <PeriodControl
                id="commission_period"
                label="Periodo"
                profile="commission_period"
                selection={selectionFromMonths(commissionStartMonth, commissionEndMonth)}
                onChange={(selection) => applyResolvedPeriod(selection, "commission_period", setCommissionStartMonth, setCommissionEndMonth)}
                helperText="Un mes solo muestra ese mes. Todo muestra todos los meses."
              />
            </div>

            <div className="finance-tabs" role="tablist" aria-label="Vistas de comisiones">
              <button
                type="button"
                className={commissionsTab === "settlement" ? "active" : ""}
                onClick={() => setCommissionsTab("settlement")}
              >
                Liquidacion
              </button>
              <button
                type="button"
                className={commissionsTab === "config" ? "active" : ""}
                onClick={() => setCommissionsTab("config")}
              >
                Configuracion
              </button>
            </div>

            {commissionsTab === "settlement" && (
              <>
                {!selectedCommissionEmployee && (
                  <p className="field-help">Selecciona un empleado para ver su liquidacion de comisiones.</p>
                )}
                {selectedCommissionEmployee && !selectedCommissionPermission?.can_access && (
                  <p className="field-help amount-warn">
                    Este empleado no tiene acceso al modulo Comisiones. Configuralo primero en ABM Empleados.
                  </p>
                )}
                {selectedCommissionEmployee && selectedCommissionPermission?.can_access && commissionSummaryLoading && (
                  <p className="field-help">Cargando liquidacion de comisiones...</p>
                )}
                {selectedCommissionEmployee && selectedCommissionPermission?.can_access && commissionAvailableArtists.length === 0 && (
                  <p className="field-help">El empleado tiene acceso a Comisiones, pero no tiene artistas asignados.</p>
                )}
                {selectedCommissionEmployee && selectedCommissionPermission?.can_access && (
                  <>
                <div className="control-dashboard compact-dashboard">
                  <div>
                    <span>Empleado</span>
                    <strong>{selectedCommissionEmployee.display_name}</strong>
                  </div>
                  <div>
                    <span>Periodo</span>
                    <strong>{commissionPeriodLabel}</strong>
                  </div>
                  <div>
                    <span>Shows incluidos</span>
                    <strong>{commissionTotals.shows}</strong>
                  </div>
                  <div>
                    <span>Indyana total</span>
                    <strong>{ars(commissionTotals.indyanaTotal)}</strong>
                  </div>
                  <div>
                    <span>Base empleado</span>
                    <strong>{ars(commissionTotals.baseAmount)}</strong>
                  </div>
                  <div className={commissionTotals.nonCommissionable > 0 ? "warn" : ""}>
                    <span>Excluido general</span>
                    <strong>{ars(commissionTotals.nonCommissionable)}</strong>
                  </div>
                  <div>
                    <span>Comision calculada</span>
                    <strong>{ars(commissionTotals.commissionAmount)}</strong>
                  </div>
                </div>

                <div className="row">
                  <div>
                    <label htmlFor="commission_settlement_search">Buscar en liquidacion</label>
                    <input
                      id="commission_settlement_search"
                      value={commissionSettlementSearch}
                      onChange={(event) => setCommissionSettlementSearch(event.target.value)}
                      placeholder="Gusty DJ, 2026-06, nota..."
                    />
                    <p className="field-help">
                      Mostrando {visibleCommissionSettlementRows.length} de {commissionSettlementRows.length} filas.
                    </p>
                  </div>
                  <div className="actions-panel">
                    <button
                      type="button"
                      onClick={printCommissionSettlement}
                      disabled={!selectedCommissionEmployee || !selectedCommissionPermission?.can_access || commissionSummaryLoading}
                    >
                      Imprimir PDF
                    </button>
                    <p className="field-help">
                      Abre un informe listo para imprimir o guardar como PDF.
                    </p>
                  </div>
                </div>

                <div className="summary-table-wrap">
                  <table className="summary-table">
                    <thead>
                      <tr>
                        <th>Mes</th>
                        <th>Artista</th>
                        <th>Shows</th>
                        <th>Indyana total</th>
                        <th>Base empleado</th>
                        <th>Excluido general</th>
                        <th>Orden</th>
                        <th>% empleado</th>
                        <th>Comision</th>
                        <th>Notas</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleCommissionSettlementRows.map((item) => (
                        <tr key={`${item.month}-${item.artist}`}>
                          <td>{item.month}</td>
                          <td><strong>{item.artist}</strong></td>
                          <td>{item.shows}</td>
                          <td>{ars(item.indyanaTotal)}</td>
                          <td>{ars(item.baseAmount)}</td>
                          <td className={item.nonCommissionable > 0 ? "amount-warn" : ""}>{ars(item.nonCommissionable)}</td>
                          <td>{item.priorityOrder || "-"}</td>
                          <td>{pct(item.percent)}</td>
                          <td><strong>{ars(item.commissionAmount)}</strong></td>
                          <td>
                            {item.notes}
                            <span className="cell-note">{item.ruleNotes}</span>
                          </td>
                        </tr>
                      ))}
                      {visibleCommissionSettlementRows.length === 0 && (
                        <tr>
                          <td colSpan={9}>Sin movimientos para los artistas asignados.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                  </>
                )}
              </>
            )}

            {commissionsTab === "config" && (
              <>
                {!selectedCommissionEmployee && (
                  <p className="field-help">Selecciona un empleado para configurar sus porcentajes por artista.</p>
                )}
                {selectedCommissionEmployee && !selectedCommissionPermission?.can_access && (
                  <p className="field-help amount-warn">
                    Para configurar comisiones, primero activa el modulo Comisiones para este empleado en ABM Empleados.
                  </p>
                )}
                {selectedCommissionEmployee && selectedCommissionPermission?.can_access && (
                  <>
                <div className="control-dashboard compact-dashboard">
                  <div>
                    <span>Reglas activas</span>
                    <strong>{commissionRulesForEmployee.filter((item) => item.active && Number(item.percent || 0) > 0).length}</strong>
                  </div>
                  <div>
                    <span>Base default</span>
                    <strong>Indyana aplicable</strong>
                  </div>
                  <div>
                    <span>Vigencia</span>
                    <strong>Por mes</strong>
                  </div>
                  <div>
                    <span>Persistencia</span>
                    <strong>{commissionDirtyEmployees[commissionsEmployee] ? "Cambios sin guardar" : "Base operacional"}</strong>
                  </div>
                </div>
                {commissionRulesLoading && (
                  <p className="field-help">Cargando reglas guardadas...</p>
                )}

                <div className="summary-table-wrap">
                  <table className="summary-table commission-config-table">
                    <thead>
                      <tr>
                        <th>Artista</th>
                        <th>% comision</th>
                        <th>Orden</th>
                        <th>Base de calculo</th>
                        <th>Booking ya pagado</th>
                        <th>Desde</th>
                        <th>Hasta</th>
                        <th>Activo</th>
                        <th>Notas</th>
                      </tr>
                    </thead>
                    <tbody>
                      {commissionRulesForEmployee.map((item) => (
                        <tr key={`${item.employee}-${item.artist}`}>
                          <td><strong>{item.artist}</strong></td>
                          <td>
                            <input
                              type="number"
                              min="0"
                              max="100"
                              step="0.1"
                              value={item.percent}
                              disabled={!canEditModule("booking_commissions") || commissionRulesLoading || commissionRulesSaving}
                              onChange={(event) => updateCommissionRuleDraft(item.artist, { percent: Number(event.target.value || 0) })}
                            />
                          </td>
                          <td>
                            <select
                              value={item.priorityOrder || ""}
                              disabled={!canEditModule("booking_commissions") || commissionRulesLoading || commissionRulesSaving || Number(item.percent || 0) <= 0 || !item.active}
                              onChange={(event) => updateCommissionRuleDraft(item.artist, { priorityOrder: event.target.value ? Number(event.target.value) : null })}
                            >
                              <option value="">Elegir</option>
                              {commissionPriorityOptions(item.artist, item.priorityOrder).length === 0 && (
                                <option value={item.priorityOrder || ""}>Sin orden disponible</option>
                              )}
                              {commissionPriorityOptions(item.artist, item.priorityOrder).map((order) => (
                                <option key={`${item.artist}_priority_${order}`} value={order}>Orden {order}</option>
                              ))}
                            </select>
                            <span className="cell-note">Cobra antes el orden menor.</span>
                          </td>
                          <td>
                            <select
                              value={item.base}
                              disabled={!canEditModule("booking_commissions") || commissionRulesLoading || commissionRulesSaving}
                              onChange={(event) => updateCommissionRuleDraft(item.artist, { base: event.target.value as CommissionRuleDraftState["base"] })}
                            >
                              <option value="commissionable">Ingreso Indyana aplicable</option>
                              <option value="total">Ingreso Indyana total de shows aplicables</option>
                            </select>
                          </td>
                          <td>
                            <label className="inline-check">
                              <input
                                type="checkbox"
                                checked={item.includeBookingFeePaidShows}
                                disabled={!canEditModule("booking_commissions") || commissionRulesLoading || commissionRulesSaving}
                                onChange={(event) => updateCommissionRuleDraft(item.artist, { includeBookingFeePaidShows: event.target.checked })}
                              />
                              Cobra igual
                            </label>
                            <span className="cell-note">Si el show excluye comision general.</span>
                          </td>
                          <td>
                            <input
                              type="month"
                              value={item.startMonth}
                              disabled={!canEditModule("booking_commissions") || commissionRulesLoading || commissionRulesSaving}
                              onChange={(event) => updateCommissionRuleDraft(item.artist, { startMonth: event.target.value })}
                            />
                          </td>
                          <td>
                            <input
                              type="month"
                              value={item.endMonth}
                              disabled={!canEditModule("booking_commissions") || commissionRulesLoading || commissionRulesSaving}
                              onChange={(event) => updateCommissionRuleDraft(item.artist, { endMonth: event.target.value })}
                            />
                          </td>
                          <td>
                            <label className="inline-check">
                              <input
                                type="checkbox"
                                checked={item.active}
                                disabled={!canEditModule("booking_commissions") || commissionRulesLoading || commissionRulesSaving}
                                onChange={(event) => updateCommissionRuleDraft(item.artist, { active: event.target.checked })}
                              />
                              Si
                            </label>
                          </td>
                          <td>
                            <input
                              type="text"
                              value={item.notes}
                              disabled={!canEditModule("booking_commissions") || commissionRulesLoading || commissionRulesSaving}
                              onChange={(event) => updateCommissionRuleDraft(item.artist, { notes: event.target.value })}
                            />
                          </td>
                        </tr>
                      ))}
                      {commissionRulesForEmployee.length === 0 && (
                        <tr>
                          <td colSpan={9}>Sin artistas asignados para este empleado.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                <p className="field-help">
                  Las reglas viven por empleado y artista, sin modificar los shows. Si un show excluye comision general, solo cobra quien tenga habilitada la excepcion.
                </p>
                {!canEditModule("booking_commissions") && (
                  <p className="field-help amount-warn">Tu usuario puede ver Comisiones, pero no editar reglas.</p>
                )}
                  </>
                )}
              </>
            )}
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
                <button type="button" className="secondary" onClick={openBookingWorkspace}>Volver a Booking</button>
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
                <span>Aplica comision general</span>
                <strong>{ars(bookingArtistSummary?.totals.commissionable_income || 0)}</strong>
              </div>
              <div className={(bookingArtistSummary?.totals.non_commissionable_income || 0) > 0 ? "warn" : ""}>
                <span>Excluye comision general</span>
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
                    <th>Aplica general</th>
                    <th>Excluye general</th>
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
                        <strong>{item.is_commissionable ? "Aplica general" : "Excluye general"}</strong>
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

        {view === "artist-finance" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Finanzas Artista</h1>
                <p>Vista operativa: saldos de shows, cuenta corriente, inversiones, proyectos y recuperables en lenguaje de negocio.</p>
              </div>
              <div className="button-row">
                <button type="button" onClick={() => loadArtistFinance()} disabled={artistFinanceLoading}>
                  {artistFinanceLoading ? "Actualizando..." : "Actualizar"}
                </button>
              </div>
            </div>

            <div className="row">
              <div>
                <label htmlFor="artist_finance_artist">Artista</label>
                <select
                  id="artist_finance_artist"
                  value={artistFinanceArtist}
                  onChange={(event) => {
                    setArtistFinanceArtist(event.target.value);
                    setArtistFinanceProjectFilter("");
                    setArtistFinanceBookingMovementOpen(false);
                    resetArtistFinanceBookingMovementDraft();
                  }}
                >
                  <option value="">Todos</option>
                  {artistFinance?.artists.map((artist) => (
                    <option key={artist} value={artist}>{artist}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className={`finance-status-card ${artistFinanceStatus.tone}`}>
              <span>Estado financiero</span>
              <strong>{artistFinanceStatus.title}</strong>
              <p>{artistFinanceStatus.body}</p>
            </div>

            <div className="finance-kpi-grid finance-kpi-grid-wide">
              <div className="finance-kpi primary">
                <span>Cuenta corriente</span>
                <strong>{ars(artistFinanceAccountNet)}</strong>
                <small>{artistFinanceAccountNet >= 0 ? "a favor de Indyana" : "a favor del artista"}</small>
              </div>
              <div className="finance-kpi">
                <span>Booking pendiente</span>
                <strong>{ars(artistFinanceBookingSummary?.booking_current_balance_indyana || 0)}</strong>
                <small>shows con saldo abierto</small>
              </div>
              <div className="finance-kpi">
                <span>Invertido / pagado</span>
                <strong>{ars(artistFinanceLedgerSummary?.investment_ars || 0)}</strong>
                <small>{artistFinanceProjectRows} movimientos</small>
              </div>
              <div className="finance-kpi">
                <span>Por recuperar definido</span>
                <strong>{ars(artistFinanceDefinedRecoverableOpen)}</strong>
                <small>recuperado {ars(artistFinanceLedgerSummary?.recovered_amount_ars || 0)}</small>
              </div>
              <div className="finance-kpi">
                <span>Pendiente de criterio</span>
                <strong>{ars(artistFinancePendingCriteria)}</strong>
                <small>requiere decision</small>
              </div>
              <div className="finance-kpi">
                <span>Proveedores pendientes</span>
                <strong>{ars(artistFinance?.summary.finance_staging.pending_amount_ars || 0)}</strong>
                <small>compromisos no pagados</small>
              </div>
            </div>

            <div className="finance-tabs" role="tablist" aria-label="Vistas de finanzas del artista">
              <button type="button" className={artistFinanceView === "summary" ? "active" : ""} onClick={() => setArtistFinanceView("summary")}>Resumen</button>
              <button type="button" className={artistFinanceView === "booking" ? "active" : ""} onClick={() => setArtistFinanceView("booking")}>Booking</button>
              <button type="button" className={artistFinanceView === "projects" ? "active" : ""} onClick={() => setArtistFinanceView("projects")}>Proyectos</button>
              <button type="button" className={artistFinanceView === "account" ? "active" : ""} onClick={() => setArtistFinanceView("account")}>Cuenta corriente</button>
              <button type="button" className={artistFinanceView === "technical" ? "active" : ""} onClick={() => setArtistFinanceView("technical")}>Detalle tecnico</button>
            </div>

            {(artistFinanceView === "projects" || artistFinanceView === "technical") && (
              <div className="row finance-filter-row">
                <div>
                  <label htmlFor="artist_finance_project">Proyecto</label>
                  <select id="artist_finance_project" value={artistFinanceProjectFilter} onChange={(event) => setArtistFinanceProjectFilter(event.target.value)}>
                    <option value="">Todos los proyectos</option>
                    {artistFinanceProjectOptions.map((project) => (
                      <option key={project} value={project}>{project}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {artistFinanceView === "summary" && (
              <>
                <h2>Resumen claro</h2>
                <div className="finance-story-grid">
                  <div>
                    <h3>Cuenta corriente</h3>
                    {Math.abs(artistFinanceAccountNet) > 0.01 ? (
                      <p>
                        {artistFinanceAccountNet > 0
                          ? `${artistFinanceSelectedLabel} debe ${ars(artistFinanceAccountNet)} a Indyana.`
                          : `Indyana debe ${ars(Math.abs(artistFinanceAccountNet))} a ${artistFinanceSelectedLabel}.`}
                      </p>
                    ) : (
                      <p>Sin saldo abierto entre artista/manager e Indyana para este filtro.</p>
                    )}
                  </div>
                  <div>
                    <h3>Booking</h3>
                    <p>
                      {artistFinanceBookingSummary?.shows || 0} shows cargados. Indyana objetivo:
                      {" "}{ars(artistFinanceBookingSummary?.indyana_target || 0)}. Recibido:
                      {" "}{ars(artistFinanceBookingSummary?.indyana_received || 0)}.
                    </p>
                    {artistFinanceVenueDebt > 0.01 && (
                      <p className="field-help danger-text">Hay deuda de boliche por {ars(artistFinanceVenueDebt)}.</p>
                    )}
                  </div>
                  <div>
                    <h3>Proyectos</h3>
                    <p>
                      Indyana tiene {ars(artistFinanceLedgerSummary?.investment_ars || 0)} pagados/cargados en proyectos.
                      {" "}Quedan {ars(artistFinanceDefinedRecoverableOpen)} por recuperar con criterio definido.
                    </p>
                  </div>
                  <div>
                    <h3>Pendiente de control</h3>
                    <p>
                      {artistFinancePendingCriteria > 0.01
                        ? `${ars(artistFinancePendingCriteria)} necesitan criterio antes de contarlos como recuperables reales.`
                        : "No hay recuperables pendientes de criterio para este filtro."}
                    </p>
                  </div>
                </div>
                <div className="finance-next-actions">
                  <strong>Lectura recomendada</strong>
                  <span>Usa Booking para revisar shows y saldos de shows.</span>
                  <span>Usa Proyectos para inversiones, gastos recuperables y proveedores.</span>
                  <span>Usa Cuenta corriente solo para ver quien debe dinero a quien.</span>
                </div>
              </>
            )}

            {artistFinanceView === "booking" && (
              <>
                <h2>Cuenta corriente booking abierta</h2>
                <div className="finance-subgrid">
                  <div className="metric-card">
                    <span>Deben a Indyana</span>
                    <strong>{ars(artistFinance?.summary.booking.indyana_balance || 0)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Indyana debe artista</span>
                    <strong>{ars(artistFinance?.summary.booking.artist_balance || 0)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Deuda boliche</span>
                    <strong>{ars(artistFinance?.summary.booking.venue_balance || 0)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Shows</span>
                    <strong>{artistFinance?.summary.booking.shows || 0}</strong>
                  </div>
                </div>
                <div className="booking-parent-movement-card">
                  <div className="section-heading compact-heading">
                    <div>
                      <h3>Registrar movimiento de cuenta booking</h3>
                      <p>Cobros, pagos o compensaciones que se aplican a uno o varios shows sin reescribir la liquidacion original.</p>
                    </div>
                    <div className="button-row">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => setArtistFinanceBookingMovementOpen((current) => !current)}
                      >
                        {artistFinanceBookingMovementOpen ? "Ocultar" : "Registrar movimiento"}
                      </button>
                    </div>
                  </div>
                  {artistFinanceBookingMovementOpen && (
                    <div className="booking-parent-movement-form">
                      <p className="field-help">El movimiento queda guardado como comprobante padre y cada aplicacion impacta en la cuenta booking del show seleccionado.</p>
                      {!artistFinanceArtist && (
                        <p className="field-help danger-text">Elegir un artista antes de registrar un movimiento de cuenta booking.</p>
                      )}
                      <div className="row">
                        <div>
                          <label htmlFor="booking_parent_date">Fecha</label>
                          <input
                            id="booking_parent_date"
                            type="date"
                            value={artistFinanceBookingMovementDraft.movementDate}
                            onChange={(event) => updateArtistFinanceBookingMovementField("movementDate", event.target.value)}
                          />
                        </div>
                        <div>
                          <label htmlFor="booking_parent_type">Tipo</label>
                          <select
                            id="booking_parent_type"
                            value={artistFinanceBookingMovementDraft.movementType}
                            onChange={(event) => setArtistFinanceBookingMovementDraft((current) => ({
                              ...current,
                              movementType: event.target.value as BookingParentMovementType,
                              paymentMethod: event.target.value === "compensacion_booking" ? "compensacion" : current.paymentMethod,
                              applications: {},
                            }))}
                          >
                            {Object.entries(bookingParentMovementLabels).map(([key, label]) => (
                              <option key={key} value={key}>{label}</option>
                            ))}
                          </select>
                          <p className="field-help">{bookingParentMovementHelp[artistFinanceBookingMovementDraft.movementType]}</p>
                        </div>
                        <div>
                          <label htmlFor="booking_parent_amount">Importe total</label>
                          <input
                            id="booking_parent_amount"
                            inputMode="decimal"
                            value={artistFinanceBookingMovementDraft.amount}
                            onChange={(event) => updateArtistFinanceBookingMovementField("amount", event.target.value)}
                            placeholder="$ 0"
                          />
                        </div>
                        <div>
                          <label htmlFor="booking_parent_method">Metodo</label>
                          <select
                            id="booking_parent_method"
                            value={artistFinanceBookingMovementDraft.paymentMethod}
                            onChange={(event) => updateArtistFinanceBookingMovementField("paymentMethod", event.target.value as BookingParentMovementDraft["paymentMethod"])}
                          >
                            <option value="transferencia">Transferencia</option>
                            <option value="efectivo">Efectivo</option>
                            <option value="compensacion">Compensacion</option>
                            <option value="ajuste">Ajuste</option>
                            <option value="otro">Otro</option>
                          </select>
                        </div>
                      </div>
                      <div className="row">
                        <div>
                          <label htmlFor="booking_parent_counterparty">Contraparte</label>
                          <input
                            id="booking_parent_counterparty"
                            value={artistFinanceBookingMovementDraft.counterparty}
                            onChange={(event) => updateArtistFinanceBookingMovementField("counterparty", event.target.value)}
                            placeholder={artistFinanceSelectedLabel}
                          />
                        </div>
                        <div>
                          <label htmlFor="booking_parent_proofs">Comprobante / refs</label>
                          <textarea
                            id="booking_parent_proofs"
                            value={artistFinanceBookingMovementDraft.proofRefs}
                            onChange={(event) => updateArtistFinanceBookingMovementField("proofRefs", event.target.value)}
                            placeholder="Uno por linea"
                          />
                        </div>
                        <div>
                          <label htmlFor="booking_parent_notes">Notas</label>
                          <textarea
                            id="booking_parent_notes"
                            value={artistFinanceBookingMovementDraft.notes}
                            onChange={(event) => updateArtistFinanceBookingMovementField("notes", event.target.value)}
                            placeholder="Ej: pago recibido para saldar shows pendientes"
                          />
                        </div>
                      </div>
                      <div className="booking-parent-summary">
                        <div>
                          <span>Cierre de bloque</span>
                          <strong>{artistFinanceBookingBlockSelectedRows.length} show(s)</strong>
                        </div>
                        <div className={artistFinanceBookingBlockNet < -0.01 ? "warn" : artistFinanceBookingBlockNet > 0.01 ? "danger" : ""}>
                          <span>Neto bloque seleccionado</span>
                          <strong>
                            {Math.abs(artistFinanceBookingBlockNet) <= 0.01
                              ? "$ 0"
                              : `${artistFinanceBookingBlockNet < 0 ? "Indyana paga " : "Indyana cobra "}${ars(Math.abs(artistFinanceBookingBlockNet))}`}
                          </strong>
                        </div>
                        <div className={artistFinanceBookingBlockAmountMatches || artistFinanceBookingBlockSelectedRows.length === 0 ? "" : "danger"}>
                          <span>Control importe</span>
                          <strong>{artistFinanceBookingBlockSelectedRows.length === 0 ? "Seleccionar" : artistFinanceBookingBlockAmountMatches ? "OK" : "No coincide"}</strong>
                        </div>
                        <div className={Math.abs(artistFinanceBookingBlockVenueBalance) > 0.01 ? "danger" : ""}>
                          <span>Deuda boliche</span>
                          <strong>{ars(Math.abs(artistFinanceBookingBlockVenueBalance))}</strong>
                        </div>
                      </div>
                      <div className="button-row">
                        <button
                          type="button"
                          className="secondary"
                          onClick={selectArtistFinanceBookingBlockRows}
                          disabled={artistFinanceBookingBlockRows.length === 0}
                        >
                          Seleccionar bloque visible
                        </button>
                        <button
                          type="button"
                          onClick={submitArtistFinanceBookingBlockSettlement}
                          disabled={
                            artistFinanceBookingBlockSelectedRows.length === 0
                            || artistFinanceBookingBlockExpectedAmount <= 0.01
                            || !artistFinanceBookingBlockAmountMatches
                            || Math.abs(artistFinanceBookingBlockVenueBalance) > 0.01
                            || !canEditModule("booking")
                          }
                        >
                          Cerrar bloque seleccionado
                        </button>
                      </div>
                      <p className="field-help">
                        Para liquidaciones con shows cruzados, usa Cerrar bloque seleccionado. El sistema compensa automaticamente los shows donde el artista cobro de mas contra los shows donde cobro de menos, y aplica solo el pago/cobro neto real.
                      </p>
                      <div className="summary-table-wrap compact-table">
                        <table className="summary-table">
                          <thead>
                            <tr>
                              <th>Bloque</th>
                              <th>Fecha</th>
                              <th>Show</th>
                              <th>Saldo neto show</th>
                            </tr>
                          </thead>
                          <tbody>
                            {artistFinanceBookingBlockRows.length === 0 && (
                              <tr><td colSpan={4}>Sin saldos abiertos para cerrar por bloque.</td></tr>
                            )}
                            {artistFinanceBookingBlockRows.map((row) => (
                              <tr key={`booking-block-${row.item.id}`}>
                                <td>
                                  <input
                                    type="checkbox"
                                    checked={row.selected}
                                    onChange={(event) => {
                                      updateArtistFinanceBookingMovementApplication(
                                        row.item.id,
                                        event.target.checked ? amountToInput(Math.abs(row.netAmount)) : "",
                                      );
                                    }}
                                  />
                                </td>
                                <td>{row.item.show_date}</td>
                                <td>
                                  <strong>{row.item.venue}</strong>
                                  <span className="cell-note">Show #{row.item.id}</span>
                                </td>
                                <td>
                                  {Math.abs(row.netAmount) <= 0.01
                                    ? "$ 0"
                                    : `${row.netAmount < 0 ? "Indyana debe " : "Deben a Indyana "}${ars(Math.abs(row.netAmount))}`}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <div className="booking-parent-summary">
                        <div>
                          <span>Importe movimiento</span>
                          <strong>{ars(artistFinanceBookingMovementAmount)}</strong>
                        </div>
                        <div>
                          <span>Aplicado a shows</span>
                          <strong>{ars(artistFinanceBookingMovementApplied)}</strong>
                        </div>
                        <div className={artistFinanceBookingMovementRemaining < -0.01 ? "danger" : artistFinanceBookingMovementRemaining > 0.01 ? "warn" : ""}>
                          <span>{artistFinanceBookingMovementRemaining >= 0 ? "Sin aplicar" : "Excedido"}</span>
                          <strong>{ars(Math.abs(artistFinanceBookingMovementRemaining))}</strong>
                        </div>
                        <div className={artistFinanceBookingMovementOverApplied ? "danger" : ""}>
                          <span>Control</span>
                          <strong>{artistFinanceBookingMovementOverApplied ? "Revisar" : "OK"}</strong>
                        </div>
                      </div>
                      <div className="button-row">
                        <button
                          type="button"
                          className="secondary"
                          onClick={suggestArtistFinanceBookingMovementApplications}
                          disabled={artistFinanceBookingMovementAmount <= 0 || artistFinanceBookingMovementRows.length === 0}
                        >
                          Sugerir por fecha
                        </button>
                        <button type="button" className="secondary" onClick={resetArtistFinanceBookingMovementDraft}>Limpiar</button>
                        <button
                          type="button"
                          onClick={submitArtistFinanceBookingMovement}
                          disabled={!artistFinanceBookingMovementCanSave}
                        >
                          Guardar movimiento
                        </button>
                      </div>
                      <div className="summary-table-wrap compact-table">
                        <table className="summary-table">
                          <thead>
                            <tr>
                              <th>Usar</th>
                              <th>Fecha</th>
                              <th>Show</th>
                              <th>Saldo elegible</th>
                              <th>Aplicar</th>
                              <th>Resultado</th>
                            </tr>
                          </thead>
                          <tbody>
                            {artistFinanceBookingMovementRows.length === 0 && (
                              <tr><td colSpan={6}>Sin saldos compatibles con este tipo de movimiento.</td></tr>
                            )}
                            {artistFinanceBookingMovementRows.map(({ item, openAmount, appliedAmount }) => {
                              const result = appliedAmount <= 0.01
                                ? "sin aplicar"
                                : appliedAmount > openAmount + 0.01
                                  ? "excede saldo"
                                  : Math.abs(openAmount - appliedAmount) <= 0.01
                                    ? "cerraria"
                                    : `quedaria ${ars(openAmount - appliedAmount)}`;
                              return (
                                <tr key={`booking-parent-${item.id}`} className={appliedAmount > openAmount + 0.01 ? "danger-row" : ""}>
                                  <td>
                                    <input
                                      type="checkbox"
                                      checked={appliedAmount > 0.01}
                                      onChange={(event) => {
                                        if (!event.target.checked) {
                                          updateArtistFinanceBookingMovementApplication(item.id, "");
                                          return;
                                        }
                                        const remaining = Math.max(artistFinanceBookingMovementAmount - artistFinanceBookingMovementApplied, 0);
                                        updateArtistFinanceBookingMovementApplication(item.id, amountToInput(Math.min(openAmount, remaining > 0 ? remaining : openAmount)));
                                      }}
                                    />
                                  </td>
                                  <td>{item.show_date}</td>
                                  <td>
                                    <strong>{item.venue}</strong>
                                    <span className="cell-note">Show #{item.id}</span>
                                  </td>
                                  <td>{ars(openAmount)}</td>
                                  <td>
                                    <input
                                      inputMode="decimal"
                                      value={artistFinanceBookingMovementDraft.applications[item.id] || ""}
                                      onChange={(event) => updateArtistFinanceBookingMovementApplication(item.id, event.target.value)}
                                      placeholder="$ 0"
                                    />
                                  </td>
                                  <td>{result}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
                <div className="summary-table-wrap">
                  <table className="summary-table">
                    <thead>
                      <tr>
                        <th>Fecha</th>
                        <th>Artista</th>
                        <th>Venue</th>
                        <th>Deben a Indyana</th>
                        <th>Indyana debe artista</th>
                        <th>Deuda boliche</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {!artistFinance && (
                        <tr><td colSpan={7}>Cargando finanzas...</td></tr>
                      )}
                      {artistFinance?.open_booking_balances.length === 0 && (
                        <tr><td colSpan={7}>Sin saldos abiertos para este filtro.</td></tr>
                      )}
                      {artistFinance?.open_booking_balances.map((item) => (
                        <tr key={item.id}>
                          <td>{item.show_date}</td>
                          <td>{item.artist}</td>
                          <td>
                            <strong>{item.venue}</strong>
                            {item.notes && <span className="cell-note">{item.notes}</span>}
                          </td>
                          <td>{ars(item.indyana_balance)}</td>
                          <td>{ars(item.artist_balance)}</td>
                          <td>{ars(item.venue_balance)}</td>
                          <td>
                            <span>{item.settlement_status || item.status}</span>
                            <span className="cell-note">Show #{item.id}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {artistFinanceView === "projects" && (
              <>
                <h2>Proyectos e inversiones</h2>
                <p className="field-help">Ordenado por ultima fecha. Aca van inversiones, gastos, recuperables y pendientes de proveedor; no es cuenta corriente salvo que el movimiento lo indique.</p>
                <div className="summary-table-wrap compact-table">
                  <table className="summary-table">
                    <thead>
                      <tr>
                        <th>Proyecto</th>
                        <th>Area</th>
                        <th>Fechas</th>
                        <th>Movs</th>
                        <th>Total</th>
                        <th>Pagado</th>
                        <th>Pendiente proveedor</th>
                        <th>Por recuperar definido</th>
                        <th>Pendiente criterio</th>
                        <th>Recuperado</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredArtistFinanceProjects.length === 0 && (
                        <tr><td colSpan={11}>Sin proyectos financieros para este filtro.</td></tr>
                      )}
                      {filteredArtistFinanceProjects.map((project) => (
                        <tr key={`${project.project_name}-${project.business_area}`}>
                          <td><strong>{project.project_name}</strong></td>
                          <td>{project.business_area}</td>
                          <td>
                            <span>{project.first_date || "-"}</span>
                            {project.last_date && project.last_date !== project.first_date && (
                              <span className="cell-note">hasta {project.last_date}</span>
                            )}
                          </td>
                          <td>{project.rows}</td>
                          <td>{ars(project.amount_ars)}</td>
                          <td>{ars(project.paid_amount_ars)}</td>
                          <td className={project.pending_amount_ars > 0 ? "amount-warn" : ""}>{ars(project.pending_amount_ars)}</td>
                          <td className={(project.recoverable_defined_open_ars || 0) > 0 ? "amount-warn" : ""}>{ars(project.recoverable_defined_open_ars || 0)}</td>
                          <td className={(project.recoverable_pending_criteria_open_ars || 0) > 0 ? "amount-warn" : ""}>{ars(project.recoverable_pending_criteria_open_ars || 0)}</td>
                          <td>{ars(project.recovered_amount_ars || 0)}</td>
                          <td>
                            {(project.pending_amount_ars || 0) > 0
                              ? "Proveedor pendiente"
                              : (project.recoverable_pending_criteria_open_ars || 0) > 0
                                ? "Definir criterio"
                                : (project.recoverable_defined_open_ars || 0) > 0
                                  ? "Recupero abierto"
                                  : "Controlado"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {artistFinanceView === "account" && (
              <>
                <h2>Cuenta corriente</h2>
                <p className="field-help">Solo muestra saldos vivos: quien debe a quien. Las inversiones y gastos de proyecto viven en Proyectos.</p>
                <div className="finance-subgrid">
                  <div className="metric-card">
                    <span>Saldo neto</span>
                    <strong>{ars(artistFinanceAccountNet)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Nos deben</span>
                    <strong>{ars(artistFinanceLedgerSummary?.artist_owes_indyana_ars || 0)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Debemos</span>
                    <strong>{ars(artistFinanceLedgerSummary?.indyana_owes_artist_ars || 0)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Deuda boliche</span>
                    <strong>{ars(artistFinanceVenueDebt)}</strong>
                  </div>
                </div>
                <div className="summary-table-wrap compact-table">
                  <table className="summary-table">
                    <thead>
                      <tr>
                        <th>Fecha</th>
                        <th>Origen</th>
                        <th>Concepto</th>
                        <th>Nos deben</th>
                        <th>Debemos</th>
                        <th>Deuda boliche</th>
                        <th>Estado</th>
                        <th>Notas</th>
                      </tr>
                    </thead>
                    <tbody>
                      {artistFinanceAccountEntries.length === 0 && (
                        <tr><td colSpan={8}>Sin saldos de cuenta corriente para este filtro.</td></tr>
                      )}
                      {artistFinanceAccountEntries.map((item) => (
                        <tr key={item.id}>
                          <td>{item.ledger_date}</td>
                          <td>
                            <strong>{item.source_label || item.source_module}</strong>
                            <span className="cell-note">{item.source_table} #{item.source_id}</span>
                          </td>
                          <td>{item.concept}</td>
                          <td>{item.account_delta_ars > 0 ? ars(item.account_delta_ars) : "-"}</td>
                          <td>{item.account_delta_ars < 0 ? ars(Math.abs(item.account_delta_ars)) : "-"}</td>
                          <td>{item.venue_receivable_ars > 0 ? ars(item.venue_receivable_ars) : "-"}</td>
                          <td>{item.status || "-"}</td>
                          <td>{item.notes || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {artistFinanceView === "technical" && (
              <>
                <h2>Detalle tecnico</h2>
                <p className="field-help">Vista para auditoria: ledger de lectura, movimientos staging, recuperos aplicados y datos viejos. No es la pantalla operativa normal.</p>
                <h3>Ledger de lectura</h3>
                <div className="summary-table-wrap compact-table">
                  <table className="summary-table">
                    <thead>
                      <tr>
                        <th>Fecha</th>
                        <th>Tipo</th>
                        <th>Artista</th>
                        <th>Proyecto</th>
                        <th>Concepto</th>
                        <th>Cuenta</th>
                        <th>Inversion</th>
                        <th>Recuperable</th>
                        <th>Origen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {artistFinance?.finance_ledger.entries.length === 0 && (
                        <tr><td colSpan={9}>Sin movimientos tecnicos para este filtro.</td></tr>
                      )}
                      {artistFinance?.finance_ledger.entries.map((item) => (
                        <tr key={item.id}>
                          <td>{item.ledger_date}</td>
                          <td>{item.ledger_type}</td>
                          <td>{item.artist}</td>
                          <td>{item.project_name || "-"}</td>
                          <td>
                            <strong>{item.concept}</strong>
                            {item.notes && <span className="cell-note">{item.notes}</span>}
                          </td>
                          <td>{item.account_delta_ars ? ars(item.account_delta_ars) : "-"}</td>
                          <td>{item.investment_ars ? ars(item.investment_ars) : "-"}</td>
                          <td>{item.recoverable_open_ars ? ars(item.recoverable_open_ars) : "-"}</td>
                          <td>
                            <span>{item.source_module}</span>
                            <span className="cell-note">{item.source_table} #{item.source_id}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <h3>Movimientos financieros staging</h3>
                <div className="summary-table-wrap">
                  <table className="summary-table">
                    <thead>
                      <tr>
                        <th>Fecha</th>
                        <th>Artista</th>
                        <th>Area</th>
                        <th>Proyecto</th>
                        <th>Concepto</th>
                        <th>Compromiso</th>
                        <th>Pagado</th>
                        <th>Pendiente</th>
                        <th>Recuperable</th>
                        <th>Estado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredArtistFinanceMovements.length === 0 && (
                        <tr><td colSpan={10}>Sin movimientos financieros para este filtro.</td></tr>
                      )}
                      {filteredArtistFinanceMovements.map((item) => (
                        <tr key={item.id}>
                          <td>{item.movement_date}</td>
                          <td>{item.artist}</td>
                          <td>{item.business_area}</td>
                          <td>{item.project_name || "-"}</td>
                          <td>
                            <strong>{item.concept}</strong>
                            <span className="cell-note">{item.category} - {item.movement_type}</span>
                            {item.recoverable ? (
                              <span className="cell-note">Metodo: {item.recovery_method || "none"} | costo {item.artist_percent}% / {item.producer_percent}%</span>
                            ) : null}
                            {item.recovered_amount_ars ? (
                              <span className="cell-note">Recuperado {ars(item.recovered_amount_ars)} | saldo {ars(item.recoverable_open_ars || 0)}</span>
                            ) : null}
                            {item.notes && <span className="cell-note">{item.notes}</span>}
                          </td>
                          <td>{ars(item.amount_ars)}</td>
                          <td>{ars(item.paid_amount_ars)}</td>
                          <td className={item.pending_amount_ars > 0 ? "amount-warn" : ""}>{ars(item.pending_amount_ars)}</td>
                          <td>
                            {item.recoverable ? "Si" : "No"}
                            {item.recoverable ? <span className="cell-note">{item.recoverable_percent}%</span> : null}
                          </td>
                          <td>{item.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <h3>Recuperos aplicados</h3>
                <div className="summary-table-wrap compact-table">
                  <table className="summary-table">
                    <thead>
                      <tr>
                        <th>Fecha</th>
                        <th>Proyecto</th>
                        <th>Origen</th>
                        <th>Aplicado</th>
                        <th>Metodo</th>
                        <th>Movimiento destino</th>
                        <th>Notas</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredArtistFinanceRecoveries.length === 0 && (
                        <tr><td colSpan={7}>Sin aplicaciones de recupero para este filtro.</td></tr>
                      )}
                      {filteredArtistFinanceRecoveries.map((item) => (
                        <tr key={item.id}>
                          <td>{item.application_date}</td>
                          <td>{item.project_name || "-"}</td>
                          <td>
                            <strong>{item.source_label || item.source_type}</strong>
                            <span className="cell-note">{item.source_type} #{item.source_id || "-"}</span>
                          </td>
                          <td>{ars(item.amount_ars)}</td>
                          <td>{item.recovery_method}</td>
                          <td>Movimiento #{item.finance_movement_id}</td>
                          <td>{item.notes || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {artistFinanceView === "booking" && (
              <>
                <h2>Booking por mes</h2>
                <div className="summary-table-wrap compact-table">
                  <table className="summary-table">
                    <thead>
                      <tr>
                        <th>Mes</th>
                        <th>Shows</th>
                        <th>Indyana objetivo</th>
                        <th>Deben a Indyana</th>
                        <th>Indyana debe artista</th>
                        <th>Deuda boliche</th>
                      </tr>
                    </thead>
                    <tbody>
                      {artistFinance?.monthly_booking.map((month) => (
                        <tr key={month.month}>
                          <td><strong>{month.month}</strong></td>
                          <td>{month.shows}</td>
                          <td>{ars(month.indyana_target)}</td>
                          <td>{ars(month.indyana_balance)}</td>
                          <td>{ars(month.artist_balance)}</td>
                          <td>{ars(month.venue_balance)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {artistFinanceView === "technical" && (
              <>
                <h2>Auditoria vieja</h2>
                <p className="field-help">Lectura tecnica de booking_artist_ledger. No es recupero vigente ni ledger financiero: solo se conserva para auditar datos historicos.</p>
                <div className="summary-table-wrap compact-table">
                  <table className="summary-table">
                    <thead>
                      <tr>
                        <th>Fecha</th>
                        <th>Tipo</th>
                        <th>Proyecto</th>
                        <th>Concepto</th>
                        <th>Importe</th>
                        <th>Recuperable</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(artistFinance?.legacy_movements || []).map((item) => (
                        <tr key={item.id}>
                          <td>{item.movement_date}</td>
                          <td>{item.movement_type}</td>
                          <td>{item.project || "-"}</td>
                          <td>{item.concept}</td>
                          <td>{ars(item.amount)}</td>
                          <td>{item.recoverable ? "Si" : "No"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        )}

        {view === "finance-movements" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Movimientos financieros</h1>
                <p>Carga hechos financieros reales o pendientes. El tratamiento contable se define aparte y queda trazable para control.</p>
              </div>
              <div className="button-row">
                <button type="button" onClick={loadFinanceMovements} disabled={financeMovementLoading}>
                  {financeMovementLoading ? "Actualizando..." : "Actualizar"}
                </button>
                <button type="button" className="secondary" onClick={resetFinanceMovementForm}>Limpiar</button>
              </div>
            </div>

            <form
              className="panel nested-panel finance-dynamic-form"
              onSubmit={financeMovementIsBookingAccountFlow ? (event) => event.preventDefault() : saveFinanceMovement}
            >
              <div className="row">
                <div>
                  <label htmlFor="finance_date">Fecha</label>
                  <input id="finance_date" type="date" value={financeMovementForm.movementDate} onChange={(event) => updateFinanceMovementField("movementDate", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="finance_area">{financeMovementAreaLabel}</label>
                  <select id="finance_area" value={financeMovementForm.businessArea} onChange={(event) => updateFinanceMovementArea(event.target.value as FinanceMovementForm["businessArea"])}>
                    <option value="">Elegir area</option>
                    {financeMovementAreaOptions.map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                  <p className="field-help">
                    {financeMovementForm.businessArea
                      ? financeMovementIsOfficeArea
                        ? "Oficina no lleva artista. Usa empleado/proveedor cuando corresponda."
                        : "Esta area trabaja con artista y proyecto asociado si existe."
                      : "Primero elegi a que parte del negocio pertenece el movimiento."}
                  </p>
                </div>
              </div>

              {financeMovementShowTopArtistSelector && (
                <div className="row">
                  <div>
                    <label htmlFor="finance_artist">Artista</label>
                    <select id="finance_artist" value={financeMovementForm.artist} onChange={(event) => updateFinanceMovementArtist(event.target.value)}>
                      <option value="">Elegir artista</option>
                      {financeMovementArtistOptions.map((artist) => (
                        <option key={artist} value={artist}>{artist}</option>
                      ))}
                    </select>
                    <p className="field-help">
                      {financeMovementArtistOptions.length === 0
                        ? "No hay artistas disponibles para tu usuario en esta pantalla."
                        : "La lista respeta los permisos de artistas del usuario."}
                    </p>
                  </div>
                  <div>
                    <label htmlFor="finance_project_select">Proyecto asociado</label>
                    <select
                      id="finance_project_select"
                      value={financeMovementProjectSelectValue}
                      onChange={(event) => {
                        const value = event.target.value;
                        setFinanceMovementProjectMode(value === "__new__" ? "new" : "existing");
                        updateFinanceMovementField("projectName", value === "__new__" ? "" : value);
                      }}
                      disabled={!financeMovementForm.artist}
                    >
                      <option value="">Sin proyecto asociado</option>
                      {financeProjectOptions.map((project) => (
                        <option key={project.id} value={project.name}>{project.name}</option>
                      ))}
                      <option value="__new__">Nuevo proyecto...</option>
                    </select>
                    {financeMovementProjectIsNew && (
                      <input
                        className="stacked-input"
                        value={financeMovementForm.projectName}
                        onChange={(event) => updateFinanceMovementField("projectName", event.target.value)}
                        placeholder="Nombre del nuevo proyecto"
                      />
                    )}
                  </div>
                </div>
              )}

              {financeMovementForm.businessArea && (
              <div>
                <label>Que queres cargar?</label>
                <div className="finance-flow-strip">
                  <button
                    type="button"
                    className={financeMovementForm.movementType === "gasto" ? "active" : ""}
                    onClick={() => updateFinanceMovementType("gasto")}
                  >
                    Gasto / inversion
                  </button>
                  <button
                    type="button"
                    className={financeMovementForm.movementType === "pago" ? "active" : ""}
                    onClick={() => updateFinanceMovementType("pago")}
                  >
                    Pago / cobro
                  </button>
                  <button
                    type="button"
                    className={financeMovementForm.movementType === "ajuste" ? "active" : ""}
                    onClick={() => updateFinanceMovementType("ajuste")}
                  >
                    Ajuste admin
                  </button>
                </div>
              </div>
              )}

              {financeMovementForm.businessArea && (
              <div className="row three">
                <div>
                  <label htmlFor="finance_category">{financeMovementCategoryLabel}</label>
                  <select id="finance_category" value={financeMovementForm.category} onChange={(event) => updateFinanceMovementField("category", event.target.value)}>
                    <option value="">Elegir categoria</option>
                    {financeMovementCategoryOptions.map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                  <p className="field-help">
                    {financeMovementForm.businessArea === "estructura"
                      ? "Sueldo, oficina y gastos internos viven aca como categorias de estructura."
                      : "La categoria cambia segun el sector elegido."}
                  </p>
                </div>
              </div>
              )}

              {financeMovementIsBookingAccountFlow ? (
                <div className="booking-parent-movement-card finance-booking-application">
                  <div className="section-heading compact-heading">
                    <div>
                      <h2>Aplicar pago/cobro a cuenta booking</h2>
                      <p>Selecciona el artista, carga el movimiento real y aplicalo a los shows que corresponde cerrar.</p>
                    </div>
                  </div>
                  {!financeMovementForm.artist && (
                    <p className="field-help danger-text">Elegir artista/unidad para traer sus shows abiertos.</p>
                  )}
                  {financeMovementForm.artist && artistFinanceLoading && (
                    <p className="field-help">Cargando cuenta booking de {financeMovementForm.artist}...</p>
                  )}
                  {financeMovementForm.artist && (
                    <>
                      <div className="row">
                        <div>
                          <label htmlFor="finance_booking_parent_date">Fecha del movimiento</label>
                          <input
                            id="finance_booking_parent_date"
                            type="date"
                            value={artistFinanceBookingMovementDraft.movementDate}
                            onChange={(event) => updateArtistFinanceBookingMovementField("movementDate", event.target.value)}
                          />
                        </div>
                        <div>
                          <label htmlFor="finance_booking_parent_type">Tipo</label>
                          <select
                            id="finance_booking_parent_type"
                            value={artistFinanceBookingMovementDraft.movementType}
                            onChange={(event) => setArtistFinanceBookingMovementDraft((current) => ({
                              ...current,
                              movementType: event.target.value as BookingParentMovementType,
                              paymentMethod: event.target.value === "compensacion_booking" ? "compensacion" : current.paymentMethod,
                              applications: {},
                            }))}
                          >
                            {Object.entries(bookingParentMovementLabels).map(([key, label]) => (
                              <option key={key} value={key}>{label}</option>
                            ))}
                          </select>
                          <p className="field-help">{bookingParentMovementHelp[artistFinanceBookingMovementDraft.movementType]}</p>
                        </div>
                        <div>
                          <label htmlFor="finance_booking_parent_amount">Importe total</label>
                          <input
                            id="finance_booking_parent_amount"
                            inputMode="decimal"
                            value={artistFinanceBookingMovementDraft.amount}
                            onChange={(event) => updateArtistFinanceBookingMovementField("amount", event.target.value)}
                            placeholder="$ 0"
                          />
                        </div>
                        <div>
                          <label htmlFor="finance_booking_parent_method">Metodo</label>
                          <select
                            id="finance_booking_parent_method"
                            value={artistFinanceBookingMovementDraft.paymentMethod}
                            onChange={(event) => updateArtistFinanceBookingMovementField("paymentMethod", event.target.value as BookingParentMovementDraft["paymentMethod"])}
                          >
                            <option value="transferencia">Transferencia</option>
                            <option value="efectivo">Efectivo</option>
                            <option value="compensacion">Compensacion</option>
                            <option value="ajuste">Ajuste</option>
                            <option value="otro">Otro</option>
                          </select>
                        </div>
                      </div>
                      <div className="row">
                        <div>
                          <label htmlFor="finance_booking_parent_counterparty">Contraparte</label>
                          <input
                            id="finance_booking_parent_counterparty"
                            value={artistFinanceBookingMovementDraft.counterparty}
                            onChange={(event) => updateArtistFinanceBookingMovementField("counterparty", event.target.value)}
                            placeholder={financeMovementForm.artist}
                          />
                        </div>
                        <div>
                          <label htmlFor="finance_booking_parent_proofs">Comprobante / refs</label>
                          <textarea
                            id="finance_booking_parent_proofs"
                            value={artistFinanceBookingMovementDraft.proofRefs}
                            onChange={(event) => updateArtistFinanceBookingMovementField("proofRefs", event.target.value)}
                            placeholder="Uno por linea"
                          />
                        </div>
                        <div>
                          <label htmlFor="finance_booking_parent_notes">Notas</label>
                          <textarea
                            id="finance_booking_parent_notes"
                            value={artistFinanceBookingMovementDraft.notes}
                            onChange={(event) => updateArtistFinanceBookingMovementField("notes", event.target.value)}
                            placeholder="Ej: pago recibido para saldar shows pendientes"
                          />
                        </div>
                      </div>
                      <div className="booking-parent-summary">
                        <div>
                          <span>Importe movimiento</span>
                          <strong>{ars(artistFinanceBookingMovementAmount)}</strong>
                        </div>
                        <div>
                          <span>Aplicado a shows</span>
                          <strong>{ars(artistFinanceBookingMovementApplied)}</strong>
                        </div>
                        <div className={artistFinanceBookingMovementRemaining < -0.01 ? "danger" : artistFinanceBookingMovementRemaining > 0.01 ? "warn" : ""}>
                          <span>{artistFinanceBookingMovementRemaining >= 0 ? "Sin aplicar" : "Excedido"}</span>
                          <strong>{ars(Math.abs(artistFinanceBookingMovementRemaining))}</strong>
                        </div>
                        <div className={artistFinanceBookingMovementOverApplied ? "danger" : ""}>
                          <span>Control</span>
                          <strong>{artistFinanceBookingMovementOverApplied ? "Revisar" : "OK"}</strong>
                        </div>
                      </div>
                      <div className="button-row">
                        <button
                          type="button"
                          className="secondary"
                          onClick={suggestArtistFinanceBookingMovementApplications}
                          disabled={artistFinanceBookingMovementAmount <= 0 || artistFinanceBookingMovementRows.length === 0}
                        >
                          Sugerir por fecha
                        </button>
                        <button type="button" className="secondary" onClick={resetArtistFinanceBookingMovementDraft}>Limpiar aplicacion</button>
                        <button
                          type="button"
                          onClick={submitArtistFinanceBookingMovement}
                          disabled={!artistFinanceBookingMovementCanSave}
                        >
                          Guardar movimiento
                        </button>
                      </div>
                      <div className="summary-table-wrap compact-table">
                        <table className="summary-table">
                          <thead>
                            <tr>
                              <th>Usar</th>
                              <th>Fecha</th>
                              <th>Show</th>
                              <th>Saldo elegible</th>
                              <th>Aplicar</th>
                              <th>Resultado</th>
                            </tr>
                          </thead>
                          <tbody>
                            {artistFinanceBookingMovementRows.length === 0 && (
                              <tr><td colSpan={6}>Sin saldos compatibles con este tipo de movimiento.</td></tr>
                            )}
                            {artistFinanceBookingMovementRows.map(({ item, openAmount, appliedAmount }) => {
                              const result = appliedAmount <= 0.01
                                ? "sin aplicar"
                                : appliedAmount > openAmount + 0.01
                                  ? "excede saldo"
                                  : Math.abs(openAmount - appliedAmount) <= 0.01
                                    ? "cerraria"
                                    : `quedaria ${ars(openAmount - appliedAmount)}`;
                              return (
                                <tr key={`finance-booking-parent-${item.id}`} className={appliedAmount > openAmount + 0.01 ? "danger-row" : ""}>
                                  <td>
                                    <input
                                      type="checkbox"
                                      checked={appliedAmount > 0.01}
                                      onChange={(event) => {
                                        if (!event.target.checked) {
                                          updateArtistFinanceBookingMovementApplication(item.id, "");
                                          return;
                                        }
                                        const remaining = Math.max(artistFinanceBookingMovementAmount - artistFinanceBookingMovementApplied, 0);
                                        updateArtistFinanceBookingMovementApplication(item.id, amountToInput(Math.min(openAmount, remaining > 0 ? remaining : openAmount)));
                                      }}
                                    />
                                  </td>
                                  <td>{item.show_date}</td>
                                  <td>
                                    <strong>{item.venue}</strong>
                                    <span className="cell-note">Show #{item.id}</span>
                                  </td>
                                  <td>{ars(openAmount)}</td>
                                  <td>
                                    <input
                                      inputMode="decimal"
                                      value={artistFinanceBookingMovementDraft.applications[item.id] || ""}
                                      onChange={(event) => updateArtistFinanceBookingMovementApplication(item.id, event.target.value)}
                                      placeholder="$ 0"
                                    />
                                  </td>
                                  <td>{result}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}
                </div>
              ) : financeMovementIsEmployeeReimbursementFlow ? (
                <>
                  <div className="section-heading compact">
                    <div>
                      <h2>Reintegro a empleado</h2>
                      <p>Registra el pago real al empleado y aplica ese importe contra gastos que pago con plata propia.</p>
                    </div>
                  </div>
                  <div className="recoupment-panel">
                    <div className="row three">
                      <div>
                        <label htmlFor="finance_employee_reimbursement_employee">Empleado</label>
                        <select
                          id="finance_employee_reimbursement_employee"
                          value={financeMovementForm.counterparty}
                          onFocus={() => {
                            if (!financeEmployeeOptionsLoading && financeEmployeeOptions.length === 0) {
                              loadFinanceEmployeeOptions();
                            }
                          }}
                          onChange={(event) => updateFinanceMovementField("counterparty", event.target.value)}
                        >
                          <option value="">{financeEmployeeOptionsLoading ? "Cargando empleados..." : "Elegir empleado"}</option>
                          {financeEmployeeOptions.map((employee) => (
                            <option key={employee.id} value={employee.display_name}>{employee.display_name}</option>
                          ))}
                        </select>
                        <p className="field-help">La lista trae empleados habilitados para operaciones financieras.</p>
                      </div>
                      <div>
                        <label htmlFor="finance_employee_reimbursement_amount">Importe pagado</label>
                        <input
                          id="finance_employee_reimbursement_amount"
                          inputMode="decimal"
                          value={financeMovementForm.amount}
                          onChange={(event) => updateFinanceMovementField("amount", event.target.value)}
                          placeholder="$ 0"
                        />
                      </div>
                      <div>
                        <label htmlFor="finance_employee_reimbursement_currency">Moneda</label>
                        <select
                          id="finance_employee_reimbursement_currency"
                          value={financeMovementForm.currency}
                          onChange={(event) => updateFinanceMovementField("currency", event.target.value as "ARS" | "USD")}
                        >
                          <option value="ARS">ARS</option>
                          <option value="USD">USD</option>
                        </select>
                        {financeMovementForm.currency === "USD" && (
                          <input
                            className="inline-followup"
                            inputMode="decimal"
                            value={financeMovementForm.fxRate}
                            onChange={(event) => updateFinanceMovementField("fxRate", event.target.value)}
                            placeholder="Tipo de cambio"
                          />
                        )}
                      </div>
                    </div>

                    <div className="control-dashboard">
                      <div>
                        <span>Importe pago</span>
                        <strong>{ars(financeMovementAmountArs)}</strong>
                      </div>
                      <div>
                        <span>Aplicado</span>
                        <strong>{ars(financeMovementAccountApplicationTotalArs)}</strong>
                      </div>
                      <div className={financeMovementAccountApplicationTotalArs - financeMovementAmountArs > 0.05 ? "danger" : ""}>
                        <span>Sin aplicar</span>
                        <strong>{ars(Math.max(financeMovementAmountArs - financeMovementAccountApplicationTotalArs, 0))}</strong>
                      </div>
                    </div>

                    {!financeMovementForm.counterparty && (
                      <p className="field-help">Elegir empleado para ver sus reintegros pendientes.</p>
                    )}
                    {financeMovementForm.counterparty && financeMovementSelectedEmployeePendingReimbursements.length === 0 && (
                      <p className="field-help">No hay reintegros pendientes para este empleado con los filtros actuales.</p>
                    )}
                    {financeMovementSelectedEmployeePendingReimbursements.length > 0 && (
                      <div className="summary-table-wrap compact-table">
                        <table className="summary-table">
                          <thead>
                            <tr>
                              <th></th>
                              <th>Fecha</th>
                              <th>Artista</th>
                              <th>Concepto</th>
                              <th>Saldo</th>
                              <th>Aplicar</th>
                            </tr>
                          </thead>
                          <tbody>
                            {financeMovementSelectedEmployeePendingReimbursements.map((item) => {
                              const balance = item.balance_ars || item.amount_ars || 0;
                              const selectedAmount = selectedFinanceAccountApplicationAmount(item.id);
                              return (
                                <tr key={item.id}>
                                  <td>
                                    <input
                                      type="checkbox"
                                      checked={Boolean(selectedAmount)}
                                      onChange={(event) => toggleFinanceAccountApplication(item.id, balance, event.target.checked)}
                                    />
                                  </td>
                                  <td>{item.entry_date}</td>
                                  <td>{item.artist}</td>
                                  <td>
                                    <strong>{item.concept}</strong>
                                    <span className="cell-note">Movimiento #{item.movement_id}</span>
                                  </td>
                                  <td>{ars(balance)}</td>
                                  <td>
                                    <input
                                      inputMode="decimal"
                                      value={selectedAmount}
                                      onChange={(event) => updateFinanceAccountApplicationAmount(item.id, event.target.value)}
                                      placeholder="$ 0"
                                    />
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                    <div className="button-row">
                      <button type="submit" disabled={financeMovementLoading || !financeMovementCanSave}>
                        {financeMovementLoading ? "Guardando..." : "Guardar reintegro"}
                      </button>
                    </div>
                    {!financeMovementCanSave && (
                      <p className="field-help">Necesitas permiso de crear en Movimientos financieros.</p>
                    )}
                  </div>
                </>
              ) : financeMovementIsFinancialDocumentFlow ? (
                <>
                  <div className="section-heading compact">
                    <div>
                      <h2>{financeMovementDocumentTitle}</h2>
                      <p>Genera un PDF desde este movimiento financiero. No aplica saldos automaticamente.</p>
                    </div>
                  </div>
                  <div className="recoupment-panel">
                    <div className="row three">
                      <div>
                        <label htmlFor="finance_document_issuer">Empresa emisora</label>
                        <select
                          id="finance_document_issuer"
                          value={financeMovementForm.documentIssuerCompany}
                          onChange={(event) => updateFinanceMovementField("documentIssuerCompany", event.target.value as FinanceDocumentIssuerCompany)}
                        >
                          {financeDocumentIssuerCompanies.map((company) => (
                            <option key={company} value={company}>{company}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label htmlFor="finance_document_from">{financeMovementDocumentCounterpartyLabel}</label>
                        <input
                          id="finance_document_from"
                          value={financeMovementForm.documentCounterparty}
                          onChange={(event) => updateFinanceMovementField("documentCounterparty", event.target.value)}
                          placeholder={financeMovementDocumentType === "payment_order" ? "Persona, proveedor, artista" : "Cliente, boliche, productor"}
                        />
                      </div>
                      {financeMovementIsShowDepositDocumentFlow && (
                      <div>
                        <label htmlFor="finance_document_show_date">Fecha del show</label>
                        <input
                          id="finance_document_show_date"
                          type="date"
                          value={financeMovementForm.documentShowDate}
                          onChange={(event) => updateFinanceMovementField("documentShowDate", event.target.value)}
                        />
                      </div>
                      )}
                    </div>

                    <div className="row three">
                      {financeMovementIsShowDepositDocumentFlow && (
                      <div>
                        <label htmlFor="finance_document_venue">Lugar / venue</label>
                        <input
                          id="finance_document_venue"
                          value={financeMovementForm.documentVenue}
                          onChange={(event) => updateFinanceMovementField("documentVenue", event.target.value)}
                          placeholder="Nombre del lugar o evento"
                        />
                      </div>
                      )}
                      <div>
                        <label htmlFor="finance_document_concept">Concepto</label>
                        <input
                          id="finance_document_concept"
                          value={financeMovementForm.concept}
                          onChange={(event) => updateFinanceMovementField("concept", event.target.value)}
                          placeholder={financeMovementDocumentDefaultConcept}
                        />
                      </div>
                      <div>
                        <label htmlFor="finance_document_amount">{financeMovementDocumentAmountLabel}</label>
                        <input
                          id="finance_document_amount"
                          inputMode="decimal"
                          value={financeMovementForm.amount}
                          onChange={(event) => updateFinanceMovementField("amount", event.target.value)}
                          placeholder="ARS o u$ 300"
                        />
                      </div>
                    </div>

                    <div className="row three">
                      <div>
                        <label htmlFor="finance_document_currency">Moneda</label>
                        <select id="finance_document_currency" value={financeMovementForm.currency} onChange={(event) => updateFinanceMovementField("currency", event.target.value as "ARS" | "USD")}>
                          <option value="ARS">ARS</option>
                          <option value="USD">USD</option>
                        </select>
                      </div>
                      <div>
                        <label htmlFor="finance_document_fx">Tipo de cambio</label>
                        <input id="finance_document_fx" inputMode="decimal" value={financeMovementForm.fxRate} onChange={(event) => updateFinanceMovementField("fxRate", event.target.value)} placeholder="Solo si es USD" />
                      </div>
                      <div className="metric-card">
                        <span>Total ARS</span>
                        <strong>{ars(financeMovementAmountArs || 0)}</strong>
                      </div>
                    </div>

                    {financeMovementIsShowDepositDocumentFlow && (
                    <div className="row">
                      <div>
                        <label htmlFor="finance_document_primary_artist">Artista principal</label>
                        <select
                          id="finance_document_primary_artist"
                          value={financeMovementForm.documentPrimaryArtist}
                          onChange={(event) => updateFinanceMovementField("documentPrimaryArtist", event.target.value)}
                        >
                          <option value="">Elegir artista</option>
                          {financeMovementArtistOptions.map((artist) => (
                            <option key={artist} value={artist}>{artist}</option>
                          ))}
                        </select>
                        <p className="field-help">Este artista funciona como ancla del movimiento para permisos y filtros.</p>
                      </div>
                      <div>
                        <label htmlFor="finance_document_artists">Otros artistas del show</label>
                      <select
                        id="finance_document_artists"
                        multiple
                        size={Math.min(Math.max(financeMovementArtistOptions.length, 3), 6)}
                        value={financeMovementForm.documentArtists}
                        onChange={(event) => updateFinanceMovementField(
                          "documentArtists",
                          Array.from(event.currentTarget.selectedOptions).map((option) => option.value),
                        )}
                      >
                        {financeMovementArtistOptions.map((artist) => (
                          <option key={artist} value={artist}>{artist}</option>
                        ))}
                      </select>
                        <p className="field-help">Opcional. Para seleccionar más de uno, usa Ctrl o Shift. El principal queda incluido automáticamente.</p>
                      </div>
                    </div>

                    )}
                    <label htmlFor="finance_document_notes">Notas del documento</label>
                    <textarea
                      id="finance_document_notes"
                      value={financeMovementForm.documentNotes}
                      onChange={(event) => updateFinanceMovementField("documentNotes", event.target.value)}
                      placeholder="Comprobante, condicion o aclaracion para el documento"
                    />
                  </div>

                  <details className="audit-details">
                    <summary>Avanzado / auditoria</summary>
                    <div className="row three">
                      <div>
                        <label htmlFor="finance_document_vat">IVA interno</label>
                        <select
                          id="finance_document_vat"
                          value={financeMovementForm.documentVatMode}
                          onChange={(event) => updateFinanceMovementField("documentVatMode", event.target.value as FinanceMovementForm["documentVatMode"])}
                        >
                          <option value="no_aplica">No aplica</option>
                          <option value="mas_iva">Más IVA</option>
                          <option value="iva_incluido">IVA incluido</option>
                        </select>
                        <p className="field-help">Dato interno. No aparece en el PDF del documento.</p>
                      </div>
                      <div>
                        <label htmlFor="finance_document_status">Estado</label>
                        <select id="finance_document_status" value={financeMovementForm.status} onChange={(event) => updateFinanceMovementField("status", event.target.value as FinanceMovementForm["status"])}>
                          <option value="borrador">Borrador</option>
                          <option value="pendiente_control">Pendiente control</option>
                          <option value="aprobado">Aprobado</option>
                          <option value="aplicado">Aplicado</option>
                          <option value="anulado">Anulado</option>
                        </select>
                      </div>
                      <div>
                        <label htmlFor="finance_document_proofs">Comprobantes / links</label>
                        <textarea id="finance_document_proofs" value={financeMovementForm.proofRefs} onChange={(event) => updateFinanceMovementField("proofRefs", event.target.value)} placeholder="Uno por linea" />
                      </div>
                      <div>
                        <label htmlFor="finance_document_general_notes">Notas internas</label>
                        <textarea id="finance_document_general_notes" value={financeMovementForm.notes} onChange={(event) => updateFinanceMovementField("notes", event.target.value)} />
                      </div>
                    </div>
                  </details>

                  <div className="button-row document-actions">
                    <button type="submit" name="finance_action" value="save_document" disabled={financeMovementLoading || !financeMovementCanSave}>
                      {financeMovementLoading ? "Guardando..." : financeMovementEditingId ? "Actualizar documento" : "Guardar documento"}
                    </button>
                    <button type="submit" name="finance_action" value="save_print_document" disabled={financeMovementLoading || !financeMovementCanSave}>
                      {financeMovementLoading ? "Guardando..." : "Guardar y abrir PDF"}
                    </button>
                  </div>
                  {financeMovementLastReceiptPdf && (
                    <p className="field-help">
                      Ultimo documento guardado:{" "}
                      <a href={financeMovementLastReceiptPdf.href} target="_blank" rel="noreferrer">
                        abrir {financeMovementLastReceiptPdf.label} en PDF
                      </a>
                    </p>
                  )}
                  {!financeMovementCanSave && (
                    <p className="field-help">
                      {financeMovementEditingId
                        ? "Necesitas permiso de editar en Movimientos financieros."
                        : "Necesitas permiso de crear en Movimientos financieros."}
                    </p>
                  )}
                </>
              ) : financeMovementShowConceptFields ? (
                <>
              <div className="section-heading compact">
                <div>
                  <h2>Conceptos</h2>
                  <p>Usa un solo concepto para una carga simple, o multiples conceptos para un proyecto con varias partidas.</p>
                </div>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={financeMovementForm.multipleConcepts}
                    disabled={Boolean(financeMovementEditingId)}
                    onChange={(event) => setFinanceMovementMultipleConcepts(event.target.checked)}
                  />
                  Multiples conceptos
                </label>
              </div>

              {!financeMovementForm.multipleConcepts && (
                <>
                  <label htmlFor="finance_concept">Concepto</label>
                  <input id="finance_concept" value={financeMovementForm.concept} onChange={(event) => updateFinanceMovementField("concept", event.target.value)} placeholder="Ej: fotografa, sonido, anticipo, recupero show" />

                  <div className="row three">
                    <div>
                      <label htmlFor="finance_counterparty">{financeMovementNeedsEmployee ? "Empleado" : "A quien se pago / de quien viene"}</label>
                      {financeMovementNeedsEmployee ? (
                        <>
                          <select
                            id="finance_counterparty"
                            value={financeMovementForm.counterparty}
                            onFocus={() => {
                              if (!financeEmployeeOptionsLoading && financeEmployeeOptions.length === 0) {
                                loadFinanceEmployeeOptions();
                              }
                            }}
                            onChange={(event) => updateFinanceMovementField("counterparty", event.target.value)}
                          >
                            <option value="">{financeEmployeeOptionsLoading ? "Cargando empleados..." : "Elegir empleado"}</option>
                            {financeEmployeeOptions.map((employee) => (
                              <option key={employee.id} value={employee.display_name}>{employee.display_name}</option>
                            ))}
                          </select>
                          <p className="field-help">
                            {financeMovementSelectedEmployee
                              ? `${employeeCompensationLabels[financeMovementSelectedEmployee.compensation_type] || "Sin compensacion fija"}${financeMovementSelectedEmployee.salary_amount ? ` - pactado ${employeeSalaryAmount(financeMovementSelectedEmployee.salary_currency, financeMovementSelectedEmployee.salary_amount)}` : ""}`
                              : financeEmployeeOptionsLoading
                                ? "Buscando empleados habilitados para sueldos y compensaciones."
                                : "Elegilo desde la lista de empleados habilitada por permisos."}
                          </p>
                        </>
                      ) : (
                        <input
                          id="finance_counterparty"
                          value={financeMovementForm.counterparty}
                          onChange={(event) => updateFinanceMovementField("counterparty", event.target.value)}
                          placeholder="Proveedor, manager, artista, tercero"
                        />
                      )}
                    </div>
                    <div>
                      <label htmlFor="finance_paid_by">Quien pago / recibio</label>
                      <select
                        id="finance_paid_by"
                        value={financeMovementForm.paidBy}
                        onFocus={() => {
                          if (!financeEmployeeOptionsLoading && financeEmployeeOptions.length === 0) {
                            loadFinanceEmployeeOptions();
                          }
                        }}
                        onChange={(event) => updateFinanceMovementField("paidBy", event.target.value as FinanceMovementForm["paidBy"])}
                      >
                        <option value="indyana">Indyana</option>
                        <option value="artista">Artista</option>
                        <option value="manager">Manager</option>
                        <option value="empleado">Empleado</option>
                        <option value="tercero">Tercero</option>
                        <option value="desconocido">Desconocido</option>
                      </select>
                      {financeMovementForm.paidBy === "empleado" && (
                        <>
                          <select
                            className="inline-followup"
                            value={financeMovementForm.paidByEmployeeId}
                            onFocus={() => {
                              if (!financeEmployeeOptionsLoading && financeEmployeeOptions.length === 0) {
                                loadFinanceEmployeeOptions();
                              }
                            }}
                            onChange={(event) => updateFinanceMovementField("paidByEmployeeId", event.target.value)}
                          >
                            <option value="">{financeEmployeeOptionsLoading ? "Cargando empleados..." : "Elegir empleado"}</option>
                            {financeEmployeeOptions.map((employee) => (
                              <option key={employee.id} value={String(employee.id)}>{employee.display_name}</option>
                            ))}
                          </select>
                          <p className="field-help">El gasto queda imputado al artista/proyecto, y genera reintegro pendiente al empleado.</p>
                        </>
                      )}
                    </div>
                    <div>
                      <label htmlFor="finance_amount">Compromiso total</label>
                      <input id="finance_amount" inputMode="decimal" value={financeMovementForm.amount} onChange={(event) => updateFinanceMovementField("amount", event.target.value)} placeholder="ARS o u$ 300" />
                    </div>
                  </div>

                  <div className="row three">
                    <div>
                      <label htmlFor="finance_paid_amount">Pagado real</label>
                      <input id="finance_paid_amount" inputMode="decimal" value={financeMovementForm.paidAmount} onChange={(event) => updateFinanceMovementField("paidAmount", event.target.value)} placeholder="Si esta vacio, asume total pagado" />
                    </div>
                    <div>
                      <label htmlFor="finance_payment_status">Estado de pago</label>
                      <select id="finance_payment_status" value={financeMovementForm.paymentStatus} onChange={(event) => updateFinanceMovementField("paymentStatus", event.target.value as FinanceMovementForm["paymentStatus"])}>
                        <option value="">Automatico</option>
                        <option value="pendiente">Pendiente</option>
                        <option value="parcial">Parcial</option>
                        <option value="pagado">Pagado</option>
                      </select>
                    </div>
                    <div>
                      <label htmlFor="finance_due_date">Vencimiento</label>
                      <input id="finance_due_date" type="date" value={financeMovementForm.dueDate} onChange={(event) => updateFinanceMovementField("dueDate", event.target.value)} />
                    </div>
                  </div>

                  <div className="row three">
                    <div>
                      <label htmlFor="finance_currency">Moneda</label>
                      <select id="finance_currency" value={financeMovementForm.currency} onChange={(event) => updateFinanceMovementField("currency", event.target.value as "ARS" | "USD")}>
                        <option value="ARS">ARS</option>
                        <option value="USD">USD</option>
                      </select>
                    </div>
                    <div>
                      <label htmlFor="finance_fx">Tipo de cambio</label>
                      <input id="finance_fx" inputMode="decimal" value={financeMovementForm.fxRate} onChange={(event) => updateFinanceMovementField("fxRate", event.target.value)} placeholder="Solo si es USD" />
                    </div>
                    <div className="metric-card">
                      <span>Compromiso ARS</span>
                      <strong>{ars(financeMovementAmountArs || 0)}</strong>
                    </div>
                  </div>

                  {financeMovementForm.movementType === "gasto" && (
                    <div className="recoupment-panel">
                      <label className="checkbox-field">
                        <input
                          type="checkbox"
                          checked={financeMovementForm.generateDocumentPdf}
                          onChange={(event) => updateFinanceMovementField("generateDocumentPdf", event.target.checked)}
                        />
                        Generar orden de pago PDF
                      </label>
                      <p className="field-help">
                        Usa los datos de este gasto/inversion y emite un documento formal sin crear otro movimiento.
                      </p>
                      {financeMovementForm.generateDocumentPdf && (
                        <>
                          <div className="row three">
                            <div>
                              <label htmlFor="finance_expense_document_issuer">Empresa emisora</label>
                              <select
                                id="finance_expense_document_issuer"
                                value={financeMovementForm.documentIssuerCompany}
                                onChange={(event) => updateFinanceMovementField("documentIssuerCompany", event.target.value as FinanceDocumentIssuerCompany)}
                              >
                                {financeDocumentIssuerCompanies.map((company) => (
                                  <option key={company} value={company}>{company}</option>
                                ))}
                              </select>
                            </div>
                            <div>
                              <label htmlFor="finance_expense_document_to">A quien se paga</label>
                              <input
                                id="finance_expense_document_to"
                                value={financeMovementForm.documentCounterparty}
                                onChange={(event) => updateFinanceMovementField("documentCounterparty", event.target.value)}
                                placeholder={financeMovementForm.counterparty || "Persona, proveedor, artista"}
                              />
                              <p className="field-help">Si lo dejas vacio, toma el campo "A quien se pago".</p>
                            </div>
                            <div className="metric-card">
                              <span>Orden de pago</span>
                              <strong>{financeMovementForm.currency} {parseMoneyInput(stripUsdPrefix(financeMovementForm.amount)).toLocaleString("es-AR", { maximumFractionDigits: 2 })}</strong>
                            </div>
                          </div>
                          <label htmlFor="finance_expense_document_notes">Notas del documento</label>
                          <textarea
                            id="finance_expense_document_notes"
                            value={financeMovementForm.documentNotes}
                            onChange={(event) => updateFinanceMovementField("documentNotes", event.target.value)}
                            placeholder="Texto opcional para el PDF"
                          />
                          <details className="audit-details">
                            <summary>Avanzado documento</summary>
                            <div className="row three">
                              <div>
                                <label htmlFor="finance_expense_document_vat">IVA interno</label>
                                <select
                                  id="finance_expense_document_vat"
                                  value={financeMovementForm.documentVatMode}
                                  onChange={(event) => updateFinanceMovementField("documentVatMode", event.target.value as FinanceMovementForm["documentVatMode"])}
                                >
                                  <option value="no_aplica">No aplica</option>
                                  <option value="mas_iva">Mas IVA</option>
                                  <option value="iva_incluido">IVA incluido</option>
                                </select>
                                <p className="field-help">Dato interno. No aparece en el PDF.</p>
                              </div>
                            </div>
                          </details>
                        </>
                      )}
                    </div>
                  )}
                </>
              )}

              {financeMovementForm.multipleConcepts && (
                <div className="summary-table-wrap compact-table">
                  <table className="summary-table">
                    <thead>
                      <tr>
                        <th>Concepto</th>
                        <th>A quien</th>
                        <th>Quien pago</th>
                        <th>Compromiso</th>
                        <th>Pagado</th>
                        <th>Moneda</th>
                        <th>TC</th>
                        <th>Estado</th>
                        <th>Vence</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {financeMovementForm.conceptLines.map((line, index) => (
                        <tr key={line.uid}>
                          <td>
                            <input value={line.concept} onChange={(event) => updateFinanceMovementLineField(line.uid, "concept", event.target.value)} placeholder={`Concepto ${index + 1}`} />
                          </td>
                          <td>
                            <input value={line.counterparty} onChange={(event) => updateFinanceMovementLineField(line.uid, "counterparty", event.target.value)} placeholder="Proveedor / tercero" />
                          </td>
                          <td>
                            <select value={line.paidBy} onChange={(event) => updateFinanceMovementLineField(line.uid, "paidBy", event.target.value as FinanceMovementLineForm["paidBy"])}>
                              <option value="indyana">Indyana</option>
                              <option value="artista">Artista</option>
                              <option value="manager">Manager</option>
                              <option value="empleado">Empleado</option>
                              <option value="tercero">Tercero</option>
                              <option value="desconocido">Desconocido</option>
                            </select>
                            {line.paidBy === "empleado" && (
                              <select
                                className="inline-followup"
                                value={line.paidByEmployeeId}
                                onFocus={() => {
                                  if (!financeEmployeeOptionsLoading && financeEmployeeOptions.length === 0) {
                                    loadFinanceEmployeeOptions();
                                  }
                                }}
                                onChange={(event) => updateFinanceMovementLineField(line.uid, "paidByEmployeeId", event.target.value)}
                              >
                                <option value="">{financeEmployeeOptionsLoading ? "Cargando..." : "Empleado"}</option>
                                {financeEmployeeOptions.map((employee) => (
                                  <option key={employee.id} value={String(employee.id)}>{employee.display_name}</option>
                                ))}
                              </select>
                            )}
                          </td>
                          <td>
                            <input inputMode="decimal" value={line.amount} onChange={(event) => updateFinanceMovementLineField(line.uid, "amount", event.target.value)} placeholder="ARS o u$" />
                          </td>
                          <td>
                            <input inputMode="decimal" value={line.paidAmount} onChange={(event) => updateFinanceMovementLineField(line.uid, "paidAmount", event.target.value)} placeholder="vacio = total" />
                          </td>
                          <td>
                            <select value={line.currency} onChange={(event) => updateFinanceMovementLineField(line.uid, "currency", event.target.value as "ARS" | "USD")}>
                              <option value="ARS">ARS</option>
                              <option value="USD">USD</option>
                            </select>
                          </td>
                          <td>
                            <input inputMode="decimal" value={line.fxRate} onChange={(event) => updateFinanceMovementLineField(line.uid, "fxRate", event.target.value)} placeholder="si USD" />
                          </td>
                          <td>
                            <select value={line.paymentStatus} onChange={(event) => updateFinanceMovementLineField(line.uid, "paymentStatus", event.target.value as FinanceMovementLineForm["paymentStatus"])}>
                              <option value="">Auto</option>
                              <option value="pendiente">Pendiente</option>
                              <option value="parcial">Parcial</option>
                              <option value="pagado">Pagado</option>
                            </select>
                          </td>
                          <td>
                            <input type="date" value={line.dueDate} onChange={(event) => updateFinanceMovementLineField(line.uid, "dueDate", event.target.value)} />
                          </td>
                          <td>
                            <button type="button" className="secondary" onClick={() => removeFinanceMovementLine(line.uid)} disabled={financeMovementForm.conceptLines.length <= 1}>Quitar</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="button-row">
                    <button type="button" onClick={addFinanceMovementLine}>Agregar concepto</button>
                  </div>
                </div>
              )}

              <div className="control-dashboard">
                <div>
                  <span>Pagado ARS</span>
                  <strong>{ars(financeMovementPaidArs || 0)}</strong>
                </div>
                <div className={financeMovementPendingArs > 0 ? "danger" : ""}>
                  <span>Deuda pendiente</span>
                  <strong>{ars(financeMovementPendingArs || 0)}</strong>
                </div>
                <div>
                  <span>Estado sugerido</span>
                  <strong>{financeMovementPendingArs <= 0 ? "pagado" : financeMovementPaidArs > 0 ? "parcial" : "pendiente"}</strong>
                </div>
              </div>

              <div className="section-heading compact">
                <div>
                  <h2>Distribucion economica</h2>
                  <p>Opcional. Usa esto cuando caja y costo real no son lo mismo.</p>
                </div>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={financeMovementForm.economicDistributionEnabled}
                    disabled={financeMovementForm.multipleConcepts}
                    onChange={(event) => setFinanceEconomicDistributionEnabled(event.target.checked)}
                  />
                  Costo compartido / imputacion manual
                </label>
              </div>
              {financeMovementForm.multipleConcepts && (
                <p className="field-help">Para distribuir economicamente, carga un solo concepto por movimiento.</p>
              )}
              {financeMovementForm.economicDistributionEnabled && (
                <div className="recoupment-panel">
                  <div className="summary-table-wrap compact-table">
                    <table className="summary-table">
                      <thead>
                        <tr>
                          <th>Tipo</th>
                          <th>Destino</th>
                          <th>Area</th>
                          <th>Importe</th>
                          <th>Moneda</th>
                          <th>TC</th>
                          <th>Notas</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {financeMovementForm.allocationLines.map((line) => (
                          <tr key={line.uid}>
                            <td>
                              <select value={line.allocationType} onChange={(event) => updateFinanceAllocationLineField(line.uid, "allocationType", event.target.value as FinanceAllocationType)}>
                                <option value="indyana_cost">Costo Indyana</option>
                                <option value="third_party_receivable">Cuenta por cobrar a tercero</option>
                                <option value="artist_current_account">Cuenta corriente artista</option>
                                <option value="other">Otra imputacion</option>
                              </select>
                            </td>
                            <td>
                              <input value={line.targetName} onChange={(event) => updateFinanceAllocationLineField(line.uid, "targetName", event.target.value)} placeholder="Indyana, productora, artista" />
                            </td>
                            <td>
                              <select value={line.businessArea} onChange={(event) => updateFinanceAllocationLineField(line.uid, "businessArea", event.target.value as FinanceAllocationForm["businessArea"])}>
                                <option value="booking">Booking</option>
                                <option value="label">Label</option>
                                <option value="management">Management</option>
                                <option value="marketing">Marketing</option>
                                <option value="digitales">Digitales</option>
                                <option value="administracion">Administracion</option>
                                <option value="estructura">Estructura</option>
                                <option value="general">General</option>
                              </select>
                            </td>
                            <td>
                              <input inputMode="decimal" value={line.amount} onChange={(event) => updateFinanceAllocationLineField(line.uid, "amount", event.target.value)} placeholder="Importe" />
                            </td>
                            <td>
                              <select value={line.currency} onChange={(event) => updateFinanceAllocationLineField(line.uid, "currency", event.target.value as "ARS" | "USD")}>
                                <option value="ARS">ARS</option>
                                <option value="USD">USD</option>
                              </select>
                            </td>
                            <td>
                              <input inputMode="decimal" value={line.fxRate} onChange={(event) => updateFinanceAllocationLineField(line.uid, "fxRate", event.target.value)} placeholder="si USD" />
                            </td>
                            <td>
                              <input value={line.notes} onChange={(event) => updateFinanceAllocationLineField(line.uid, "notes", event.target.value)} placeholder="opcional" />
                            </td>
                            <td>
                              <button type="button" className="secondary" onClick={() => removeFinanceAllocationLine(line.uid)} disabled={financeMovementForm.allocationLines.length <= 1}>Quitar</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="button-row">
                    <button type="button" onClick={addFinanceAllocationLine}>Agregar imputacion</button>
                  </div>
                  <div className="control-dashboard">
                    <div>
                      <span>Distribuido</span>
                      <strong>{ars(financeAllocationPreviewTotals.amountArs)}</strong>
                    </div>
                    <div>
                      <span>Costo Indyana</span>
                      <strong>{ars(financeAllocationPreviewTotals.indyanaCostArs)}</strong>
                    </div>
                    <div>
                      <span>A cobrar tercero</span>
                      <strong>{ars(financeAllocationPreviewTotals.thirdPartyReceivableArs)}</strong>
                    </div>
                    <div className={Math.abs(financeAllocationDifferenceArs) > 0.05 ? "danger" : ""}>
                      <span>Diferencia</span>
                      <strong>{ars(financeAllocationDifferenceArs)}</strong>
                    </div>
                  </div>
                </div>
              )}

              {financeMovementShowTreatment && (
                <>
                  <div className="section-heading compact">
                    <div>
                      <h2>Tratamiento financiero</h2>
                      <p>Define si el hecho queda como inversion, cuenta corriente, recuperable o pendiente de criterio.</p>
                    </div>
                  </div>
                  <div className="recoupment-panel">
                    <div className="row three">
                      <label className="checkbox-field">
                        <input type="checkbox" checked={financeMovementForm.recoverable} onChange={(event) => updateFinanceMovementField("recoverable", event.target.checked)} />
                        Es recuperable
                      </label>
                      <div>
                        <label htmlFor="finance_recoverable_pct">Parte recuperable %</label>
                        <input id="finance_recoverable_pct" inputMode="decimal" value={financeMovementForm.recoverablePercent} onChange={(event) => updateFinanceMovementField("recoverablePercent", event.target.value)} />
                      </div>
                      <div>
                        <label htmlFor="finance_effect">Impacto esperado</label>
                        <select id="finance_effect" value={financeMovementForm.accountEffect} onChange={(event) => updateFinanceMovementField("accountEffect", event.target.value as FinanceMovementForm["accountEffect"])}>
                          <option value="inversion_indyana">Inversion Indyana</option>
                          <option value="artista_debe_indyana">Artista debe a Indyana</option>
                          <option value="indyana_debe_artista">Indyana debe artista</option>
                          <option value="sin_impacto">Pendiente / sin impacto por ahora</option>
                        </select>
                      </div>
                    </div>

                    {financeMovementForm.recoverable && (
                      <div className="row three">
                        <div>
                          <label htmlFor="finance_recovery_method">Como se recupera</label>
                          <select id="finance_recovery_method" value={financeMovementForm.recoveryMethod} onChange={(event) => updateFinanceMovementField("recoveryMethod", event.target.value as FinanceMovementForm["recoveryMethod"])}>
                            <option value="none">Elegir metodo</option>
                            <option value="before_split">Antes del split del show</option>
                            <option value="after_split">Despues del split</option>
                            <option value="direct_account">Cuenta corriente directa</option>
                            <option value="royalties">Regalias digitales</option>
                            <option value="manual">Manual / caso especial</option>
                          </select>
                          <p className="field-help">{financeRecoveryMethodHelp[financeMovementForm.recoveryMethod]}</p>
                        </div>
                        <div>
                          <label htmlFor="finance_artist_pct">Costo economico artista %</label>
                          <input id="finance_artist_pct" inputMode="decimal" value={financeMovementForm.artistPercent} onChange={(event) => updateFinanceMovementField("artistPercent", event.target.value)} />
                        </div>
                        <div>
                          <label htmlFor="finance_producer_pct">Costo economico Indyana %</label>
                          <input id="finance_producer_pct" inputMode="decimal" value={financeMovementForm.producerPercent} onChange={(event) => updateFinanceMovementField("producerPercent", event.target.value)} />
                        </div>
                      </div>
                    )}
                    {financeMovementForm.recoverable && (
                      <div className="control-dashboard">
                        <div>
                          <span>Base recuperable</span>
                          <strong>{ars(financeMovementRecoverableBase)}</strong>
                        </div>
                        <div>
                          <span>Recupero caja Indyana</span>
                          <strong>{ars(financeMovementCashRecovery)}</strong>
                        </div>
                        <div>
                          <span>Costo artista</span>
                          <strong>{ars(financeMovementArtistEconomicCost)}</strong>
                        </div>
                        <div>
                          <span>Costo Indyana</span>
                          <strong>{ars(financeMovementProducerEconomicCost)}</strong>
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}

              <details className="audit-details">
                <summary>Avanzado / auditoria</summary>
                <div className="row three">
                  <div>
                    <label htmlFor="finance_status">Estado</label>
                    <select id="finance_status" value={financeMovementForm.status} onChange={(event) => updateFinanceMovementField("status", event.target.value as FinanceMovementForm["status"])}>
                      <option value="borrador">Borrador</option>
                      <option value="pendiente_control">Pendiente control</option>
                      <option value="aprobado">Aprobado</option>
                      <option value="aplicado">Aplicado</option>
                      <option value="anulado">Anulado</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="finance_source">Origen tecnico</label>
                    <select id="finance_source" value={financeMovementForm.sourceType} onChange={(event) => updateFinanceMovementField("sourceType", event.target.value as FinanceMovementForm["sourceType"])}>
                      <option value="manual">Manual</option>
                      <option value="legacy">Historico</option>
                      <option value="booking">Booking</option>
                      <option value="royalties">Regalias</option>
                      <option value="import">Importacion</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="finance_source_id">Referencia origen</label>
                    <input id="finance_source_id" value={financeMovementForm.sourceId} onChange={(event) => updateFinanceMovementField("sourceId", event.target.value)} placeholder="Show ID, reporte, Excel, etc." />
                  </div>
                </div>
              </details>

              <label htmlFor="finance_proofs">Comprobantes / links</label>
              <textarea id="finance_proofs" value={financeMovementForm.proofRefs} onChange={(event) => updateFinanceMovementField("proofRefs", event.target.value)} placeholder="Uno por linea" />

              <label htmlFor="finance_notes">Notas</label>
              <textarea id="finance_notes" value={financeMovementForm.notes} onChange={(event) => updateFinanceMovementField("notes", event.target.value)} />

              <div className="button-row">
                <button type="submit" disabled={financeMovementLoading || !financeMovementCanSave}>
                  {financeMovementLoading ? "Guardando..." : financeMovementEditingId ? "Actualizar movimiento" : "Guardar en staging"}
                </button>
                {financeMovementIsExpenseDocumentFlow && (
                  <button type="submit" name="finance_action" value="save_print_document" disabled={financeMovementLoading || !financeMovementCanSave}>
                    {financeMovementLoading ? "Guardando..." : "Guardar y abrir PDF"}
                  </button>
                )}
              </div>
              {!financeMovementCanSave && (
                <p className="field-help">
                  {financeMovementNeedsEmployee && !(financeMovementEditingId ? financeMovementCanEditPayroll : financeMovementCanCreatePayroll)
                    ? "Necesitas permiso en Sueldos y compensaciones para cargar o editar sueldos/comisiones internas."
                    : financeMovementEditingId
                    ? "Necesitas permiso de editar en Movimientos financieros."
                    : "Necesitas permiso de crear en Movimientos financieros."}
                </p>
              )}
                </>
              ) : null}
            </form>

            <div className="section-heading">
              <div>
                <h2>Movimientos cargados</h2>
                <p>{financeMovements?.summary.note || "Capa de staging financiero."}</p>
              </div>
            </div>

            <div className="row three">
              <div>
                <label htmlFor="finance_filter_artist">Filtrar artista</label>
                <select
                  id="finance_filter_artist"
                  value={financeMovementArtistFilter}
                  onChange={(event) => {
                    setFinanceMovementArtistFilter(event.target.value);
                    setFinanceMovementProjectFilter("");
                  }}
                >
                  <option value="">Todos</option>
                  {(financeMovements?.artists || []).map((artist) => (
                    <option key={artist} value={artist}>{artist}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="finance_filter_project">Filtrar proyecto</label>
                <select id="finance_filter_project" value={financeMovementProjectFilter} onChange={(event) => setFinanceMovementProjectFilter(event.target.value)}>
                  <option value="">Todos los proyectos</option>
                  {financeMovementProjectOptions.map((project) => (
                    <option key={project} value={project}>{project}</option>
                  ))}
                </select>
                <p className="field-help">Si queda vacio, muestra todo lo del artista seleccionado.</p>
              </div>
              <div>
                <label htmlFor="finance_filter_status">Filtrar estado</label>
                <select id="finance_filter_status" value={financeMovementStatusFilter} onChange={(event) => setFinanceMovementStatusFilter(event.target.value)}>
                  <option value="">Todos</option>
                  <option value="borrador">Borrador</option>
                  <option value="pendiente_control">Pendiente control</option>
                  <option value="aprobado">Aprobado</option>
                  <option value="aplicado">Aplicado</option>
                  <option value="anulado">Anulado</option>
                </select>
              </div>
              <div className="metric-card">
                <span>Compromiso visible</span>
                <strong>{ars(financeMovements?.summary.amount_ars || 0)}</strong>
              </div>
              <div className="metric-card">
                <span>Pagado visible</span>
                <strong>{ars(financeMovements?.summary.paid_amount_ars || 0)}</strong>
              </div>
              <div className="metric-card">
                <span>Deuda visible</span>
                <strong>{ars(financeMovements?.summary.pending_amount_ars || 0)}</strong>
              </div>
            </div>

            {(financeMovements?.employee_reimbursements?.summary || []).length > 0 && (
              <div className="recoupment-panel compact-panel">
                <div className="section-heading compact">
                  <div>
                    <h2>Reintegros a empleados</h2>
                    <p>Gastos del negocio pagados por empleados. El gasto sigue imputado al artista/proyecto; este bloque muestra lo que Indyana debe reintegrar.</p>
                  </div>
                </div>
                <div className="control-dashboard">
                  {(financeMovements?.employee_reimbursements?.summary || []).map((item) => (
                    <div key={item.employee_name}>
                      <span>{item.employee_name}</span>
                      <strong>{ars(item.amount_ars)}</strong>
                      <small>{item.rows} movimiento(s)</small>
                    </div>
                  ))}
                </div>
                <details className="audit-details">
                  <summary>Ver detalle de reintegros</summary>
                  <div className="summary-table-wrap compact-table">
                    <table className="summary-table">
                      <thead>
                        <tr>
                          <th>Fecha</th>
                          <th>Empleado</th>
                          <th>Artista</th>
                          <th>Concepto</th>
                          <th>Original</th>
                          <th>Aplicado</th>
                          <th>Saldo</th>
                          <th>Movimiento</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(financeMovements?.employee_reimbursements?.items || []).map((item) => (
                          <tr key={item.id}>
                            <td>{item.entry_date}</td>
                            <td>{item.employee_name}</td>
                            <td>{item.artist}</td>
                            <td>{item.concept}</td>
                            <td>{ars(item.amount_ars)}</td>
                            <td>{ars(item.applied_amount_ars || 0)}</td>
                            <td>{ars(item.balance_ars || item.amount_ars)}</td>
                            <td>#{item.movement_id}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              </div>
            )}

            <div className="summary-table-wrap">
              <table className="summary-table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Artista</th>
                    <th>Area</th>
                    <th>Proyecto</th>
                    <th>Concepto</th>
                    <th>Compromiso</th>
                    <th>Pagado</th>
                    <th>Imputacion</th>
                    <th>Pendiente</th>
                    <th>Recuperable</th>
                    <th>Estado</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {!financeMovements && (
                    <tr><td colSpan={12}>Cargando movimientos...</td></tr>
                  )}
                  {financeMovements?.items.length === 0 && (
                    <tr><td colSpan={12}>Sin movimientos para este filtro.</td></tr>
                  )}
                  {financeMovements?.items.map((item) => (
                    <tr key={item.id}>
                      <td>{item.movement_date}</td>
                      <td>{item.artist}</td>
                      <td>{item.business_area}</td>
                      <td>{item.project_name || "-"}</td>
                      <td>
                        <strong>{item.concept}</strong>
                        <span className="cell-note">{item.category} - {item.movement_type}</span>
                        {item.document_detail && (
                          <span className="cell-note">
                            Documento #{String(item.document_detail.document_number).padStart(6, "0")} - {item.document_detail.counterparty_name}
                          </span>
                        )}
                        {item.notes && <span className="cell-note">{item.notes}</span>}
                        {item.paid_by === "empleado" && item.paid_by_employee_name && (
                          <span className="cell-note">Pagó empleado: {item.paid_by_employee_name}</span>
                        )}
                        {item.recoverable ? (
                          <span className="cell-note">Metodo: {item.recovery_method || "none"} | costo {item.artist_percent}% / {item.producer_percent}%</span>
                        ) : null}
                      </td>
                      <td>
                        {ars(item.amount_ars)}
                        {item.currency === "USD" && <span className="cell-note">USD {item.amount} x {item.fx_rate}</span>}
                      </td>
                      <td>{ars(item.paid_amount_ars)}</td>
                      <td>
                        {(item.allocation_lines || []).length > 0 ? (
                          <>
                            {item.allocation_lines.map((line, index) => (
                              <span className="cell-note" key={`${item.id}_allocation_${index}`}>
                                {financeAllocationTypeLabels[line.allocation_type] || line.allocation_type}: {ars(line.amount_ars)} {line.target_name}
                              </span>
                            ))}
                          </>
                        ) : (
                          <span className="cell-note">Costo Indyana: {ars(item.amount_ars)}</span>
                        )}
                      </td>
                      <td className={item.pending_amount_ars > 0 ? "amount-warn" : ""}>
                        {ars(item.pending_amount_ars)}
                        {item.pending_amount_ars > 0 && <span className="cell-note">{item.payment_status}</span>}
                        {item.due_date && <span className="cell-note">Vence {item.due_date}</span>}
                      </td>
                      <td>
                        {item.recoverable ? "Si" : "No"}
                        {item.recoverable ? <span className="cell-note">{item.recoverable_percent}%</span> : null}
                      </td>
                      <td>
                        {item.status}
                        {isFinanceMovementLocked(item.status) && <span className="cell-note">Bloqueado</span>}
                      </td>
                      <td>
                        <div className="button-row compact-buttons">
                          {isFinanceMovementLocked(item.status) ? (
                            <span className="cell-note">Sin edicion</span>
                          ) : canEditModule("finance_movements") ? (
                            <button type="button" className="secondary" onClick={() => editFinanceMovement(item)}>Editar</button>
                          ) : (
                            <span className="cell-note">Solo carga</span>
                          )}
                          {item.document_detail && (
                            <a
                              className="button-link secondary"
                              href={`/api/finance/documents/${item.document_detail.id}/pdf`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              PDF
                            </a>
                          )}
                        </div>
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
              {bookingLabForm.collectedAmount.trim() && parseAmountInput(bookingLabForm.collectedAmount, bookingLabFxRate) < parseAmountInput(bookingLabForm.grossAmount, bookingLabFxRate) && (
                <div className="booking-payment-box">
                  <div className="row">
                    <label className="check-row">
                      <input
                        type="radio"
                        name="booking_lab_shortfall_policy"
                        checked={bookingLabForm.venueShortfallPolicy === "deuda_boliche"}
                        onChange={() => updateBookingLabField("venueShortfallPolicy", "deuda_boliche")}
                      />
                      <span>Dejar saldo al boliche</span>
                    </label>
                    <label className="check-row">
                      <input
                        type="radio"
                        name="booking_lab_shortfall_policy"
                        checked={bookingLabForm.venueShortfallPolicy === "ajustar_cachet"}
                        onChange={() => updateBookingLabField("venueShortfallPolicy", "ajustar_cachet")}
                      />
                      <span>Ajustar cachet al cobrado</span>
                    </label>
                  </div>
                  <p className="field-help">Esta decision define si la base del evento usa el pactado o el cobrado real.</p>
                </div>
              )}

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
                  <span>Base regla general</span>
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

        {view === "booking" && bookingSurface === "dashboard" && (
          <BookingDashboard
            onOpenSettlements={openBookingSettlements}
            onOpenSummary={() => openView("booking-summary")}
            onOpenDetail={() => openView("booking-artist-summary")}
            onOpenCaserio={() => openView("caserio")}
            onStartSettlement={startAgendaSettlement}
            onOpenLinkedSettlement={openLinkedAgendaSettlement}
            canOpenSummary={canAccessModule("booking_summary")}
            canOpenDetail={canAccessModule("booking_detail")}
            canOpenCaserio={canAccessModule("caserio")}
          />
        )}

        {view === "booking" && bookingSurface === "settlement" && (
          <section className="booking-mode-bar" aria-label="Tipo de booking">
            <button type="button" className="secondary" onClick={() => setBookingSurface("dashboard")}>Volver al centro de booking</button>
            <div className="booking-mode-switch" role="tablist" aria-label="Seleccionar tipo de booking">
              <button
                type="button"
                role="tab"
                aria-selected={bookingWorkspaceMode === "individual"}
                className={bookingWorkspaceMode === "individual" ? "active" : ""}
                disabled={!canAccessBookingMode("individual")}
                onClick={() => selectBookingMode("individual")}
              >
                Booking individual
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={bookingWorkspaceMode === "shared"}
                className={bookingWorkspaceMode === "shared" ? "active" : ""}
                disabled={!canAccessBookingMode("shared")}
                onClick={() => selectBookingMode("shared")}
              >
                Booking compartido
              </button>
            </div>
          </section>
        )}

        {view === "booking" && bookingSurface === "settlement" && bookingWorkspaceMode === "shared" && (
          <section className="panel wide-panel">
            <div className="section-heading">
              <div>
                <h1>Booking compartido</h1>
                <p>Eventos madre con gastos compartidos y liquidaciones internas por artista.</p>
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

              {!compositeBookingEditingId && renderBookingAgendaPrefill("shared")}
              {!compositeBookingEditingId && (
                <p className="field-help">
                  {compositeBookingAgendaEventId
                    ? `Vinculada a Agenda #${compositeBookingAgendaEventId}.`
                    : "Si el show no existe en Agenda, se creará y vinculará al guardar."}
                </p>
              )}

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

        {view === "employees" && (
          <div className="grid artist-grid">
            <form className="panel" onSubmit={submitEmployeeRecord}>
              <div className="section-heading compact">
                <div>
                  <h1>{employeeEditingId ? `Editando empleado #${employeeEditingId}` : "ABM de empleados"}</h1>
                  <p>Equipo VPO, funciones y base para permisos por modulo.</p>
                </div>
                {employeeEditingId && (
                  <button type="button" onClick={resetEmployeeForm}>Cancelar</button>
                )}
              </div>

              <label htmlFor="employee_display_name">Nombre</label>
              <input
                id="employee_display_name"
                value={employeeForm.displayName}
                onChange={(event) => updateEmployeeField("displayName", event.target.value)}
                required
              />

              <div className="row">
                <div>
                  <label htmlFor="employee_cuit">CUIT / CUIL</label>
                  <input
                    id="employee_cuit"
                    value={employeeForm.cuit}
                    onChange={(event) => updateEmployeeField("cuit", event.target.value)}
                  />
                </div>
                <div>
                  <label htmlFor="employee_phone">Telefono</label>
                  <input
                    id="employee_phone"
                    value={employeeForm.phone}
                    onChange={(event) => updateEmployeeField("phone", event.target.value)}
                  />
                </div>
              </div>

              <label htmlFor="employee_email">Email</label>
              <input
                id="employee_email"
                type="email"
                value={employeeForm.email}
                onChange={(event) => updateEmployeeField("email", event.target.value)}
              />

              <label htmlFor="employee_address">Domicilio</label>
              <input
                id="employee_address"
                value={employeeForm.address}
                onChange={(event) => updateEmployeeField("address", event.target.value)}
              />

              <div className="section-heading compact">
                <div>
                  <h2>Funciones</h2>
                  <p>Un empleado puede tener mas de una funcion.</p>
                </div>
              </div>
              <div className="checkbox-grid">
                {(employeeFunctionOptions.length ? employeeFunctionOptions : ["Tour Manager", "Project Manager", "Label", "Digitales", "Administracion", "Presidente", "Vice Presidente"]).map((functionName) => (
                  <label className="checkbox-field" key={functionName}>
                    <input
                      type="checkbox"
                      checked={employeeForm.functions.includes(functionName)}
                      onChange={() => toggleEmployeeFunction(functionName)}
                    />
                    {functionName}
                  </label>
                ))}
              </div>

              <div className="section-heading compact">
                <div>
                  <h2>Compensacion</h2>
                  <p>Esto guarda la condicion pactada. El pago real se carga en Movimientos Financieros.</p>
                </div>
              </div>
              <div className="row three">
                <div>
                  <label htmlFor="employee_compensation_type">Modelo</label>
                  <select
                    id="employee_compensation_type"
                    value={employeeForm.compensationType}
                    onChange={(event) => updateEmployeeField("compensationType", event.target.value as EmployeeCompensationType)}
                  >
                    <option value="none">Sin compensacion fija</option>
                    <option value="salary">Salario mensual</option>
                    <option value="salary_plus_booking_commission">Salario + comision booking</option>
                    <option value="booking_commission_only">Solo comision booking</option>
                  </select>
                </div>
                {employeeForm.compensationType !== "none" && employeeForm.compensationType !== "booking_commission_only" && (
                  <>
                    <div>
                      <label htmlFor="employee_salary_amount">Salario pactado</label>
                      <input
                        id="employee_salary_amount"
                        inputMode="decimal"
                        value={employeeForm.salaryAmount}
                        onChange={(event) => updateEmployeeField("salaryAmount", event.target.value)}
                        placeholder="Importe mensual"
                      />
                    </div>
                    <div>
                      <label htmlFor="employee_salary_currency">Moneda</label>
                      <select
                        id="employee_salary_currency"
                        value={employeeForm.salaryCurrency}
                        onChange={(event) => updateEmployeeField("salaryCurrency", event.target.value as "ARS" | "USD")}
                      >
                        <option value="ARS">ARS</option>
                        <option value="USD">USD</option>
                      </select>
                    </div>
                  </>
                )}
              </div>
              {employeeForm.compensationType !== "none" && (
                <>
                  <label htmlFor="employee_salary_notes">Notas de compensacion</label>
                  <textarea
                    id="employee_salary_notes"
                    value={employeeForm.salaryNotes}
                    onChange={(event) => updateEmployeeField("salaryNotes", event.target.value)}
                    placeholder="Ej: parte fija, financiacion externa, condicion pendiente"
                  />
                </>
              )}
              <p className="field-help">
                Las comisiones variables de booking se configuran en la tarjeta Comisiones. Este bloque no crea pagos automaticos.
              </p>

              <div className="section-heading compact">
                <div>
                  <h2>Usuario web</h2>
                  <p>Este usuario ya es la base operativa de login local/cloud.</p>
                </div>
              </div>
              <div className="row three">
                <div>
                  <label htmlFor="employee_username">Usuario</label>
                  <input
                    id="employee_username"
                    value={employeeForm.username}
                    onChange={(event) => updateEmployeeField("username", event.target.value)}
                    placeholder="salomef"
                  />
                </div>
                <div>
                  <label htmlFor="employee_user_role">Rol global</label>
                  <select
                    id="employee_user_role"
                    value={employeeForm.userRole}
                    onChange={(event) => updateEmployeeField("userRole", event.target.value as EmployeeForm["userRole"])}
                  >
                    <option value="viewer">Viewer</option>
                    <option value="editor">Editor</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={employeeForm.userActive}
                    onChange={(event) => updateEmployeeField("userActive", event.target.checked)}
                  />
                  Usuario activo
                </label>
              </div>
              <div className="row">
                <div>
                  <label htmlFor="employee_new_password">Establecer contrasena</label>
                  <input
                    id="employee_new_password"
                    type="password"
                    value={employeeForm.newPassword}
                    onChange={(event) => updateEmployeeField("newPassword", event.target.value)}
                    placeholder="Dejar vacio para no cambiar"
                    autoComplete="new-password"
                  />
                </div>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={employeeForm.mustChangePassword}
                    onChange={(event) => updateEmployeeField("mustChangePassword", event.target.checked)}
                  />
                  Pedir cambio al ingresar
                </label>
              </div>
              <p className="field-help">
                Default inicial: Indyana2026!. Si estableces esa clave, deja marcado pedir cambio.
              </p>

              <div className="section-heading compact">
                <div>
                  <h2>Permisos por modulo</h2>
                  <p>Inicio se habilita automaticamente si tiene acceso a algun modulo. Cada permiso se valida en pantalla y servidor.</p>
                </div>
              </div>
              <div className="permission-level-list">
                {(employeeForm.permissions.length ? employeeForm.permissions : defaultEmployeePermissions()).map((permission) => {
                  const moduleLabel = employeeModules.find((module) => module.module_key === permission.module_key)?.label || permission.module_key;
                  const level = employeePermissionLevel(permission);
                  const usesArtistScope = permissionUsesArtistScope(permission);
                  const allArtists = permissionHasAllArtists(permission);
                  const selectedArtists = permissionArtistNames(permission);
                  const levelHelp = permission.module_key === "booking_agenda"
                    ? {
                        none: "No puede abrir la Agenda.",
                        view: "Puede ver toda la Agenda.",
                        create: "Puede ver y cargar entradas.",
                        edit: "Puede ver, cargar y editar entradas.",
                        admin: "Puede administrar toda la Agenda.",
                      }[level]
                    : {
                        none: "No puede abrir el modulo.",
                        view: "Puede entrar y ver historial.",
                        create: "Puede entrar y cargar nuevo, sin historial amplio.",
                        edit: "Puede ver historial, cargar y editar.",
                        admin: "Puede hacer todo, incluyendo aprobar/cerrar.",
                      }[level];
                  return (
                    <div className="permission-level-row" key={permission.module_key}>
                      <div>
                        <strong>{moduleLabel}</strong>
                        <span>{levelHelp}</span>
                      </div>
                      <select
                        value={level}
                        onChange={(event) => updateEmployeePermissionLevel(permission.module_key, event.target.value)}
                      >
                        <option value="none">Sin acceso</option>
                        <option value="view">Ver</option>
                        <option value="create">Cargar</option>
                        <option value="edit">Editar</option>
                        <option value="admin">Admin</option>
                      </select>
                      {usesArtistScope && level !== "none" && (
                        <div className="permission-scope-box">
                          <div className="permission-scope-header">
                            <strong>Artistas</strong>
                            <span>{allArtists ? "Todos" : `${selectedArtists.length} seleccionado(s)`}</span>
                          </div>
                          <div className="permission-scope-mode">
                            <label className="check-row">
                              <input
                                type="radio"
                                name={`artist_scope_${permission.module_key}`}
                                checked={allArtists}
                                onChange={() => updateEmployeePermissionArtistMode(permission.module_key, "all")}
                              />
                              <span>Todos los artistas</span>
                            </label>
                            <label className="check-row">
                              <input
                                type="radio"
                                name={`artist_scope_${permission.module_key}`}
                                checked={!allArtists}
                                onChange={() => updateEmployeePermissionArtistMode(permission.module_key, "selected")}
                              />
                              <span>Solo seleccionados</span>
                            </label>
                          </div>
                          {!allArtists && (
                            <div className="permission-artist-grid">
                              {bookingArtists.map((artist) => (
                                <label className="checkbox-field compact" key={`${permission.module_key}_${artist}`}>
                                  <input
                                    type="checkbox"
                                    checked={selectedArtists.includes(artist)}
                                    onChange={() => toggleEmployeePermissionArtist(permission.module_key, artist)}
                                  />
                                  {artist}
                                </label>
                              ))}
                              {bookingArtists.length === 0 && (
                                <p className="field-help">No hay artistas cargados para seleccionar.</p>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              <label htmlFor="employee_notes">Notas</label>
              <textarea
                id="employee_notes"
                value={employeeForm.notes}
                onChange={(event) => updateEmployeeField("notes", event.target.value)}
              />

              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={employeeForm.active}
                  onChange={(event) => updateEmployeeField("active", event.target.checked)}
                />
                Activo
              </label>

              <button type="submit" disabled={employeeLoading}>
                {employeeLoading ? "Guardando..." : employeeEditingId ? "Guardar cambios" : "Crear empleado"}
              </button>
            </form>

            <section className="panel">
              <div className="section-heading compact">
                <div>
                  <h1>Empleados</h1>
                  <p>La edicion granular de permisos queda preparada para la siguiente etapa.</p>
                </div>
                <button type="button" onClick={loadEmployeeRecords}>Actualizar</button>
              </div>

              <label htmlFor="employee_search">Buscar empleado</label>
              <input
                id="employee_search"
                value={employeeSearch}
                onChange={(event) => setEmployeeSearch(event.target.value)}
                placeholder="Nombre, funcion, email, telefono"
              />
              <p className="field-help">
                Mostrando {filteredEmployeeRecords.length} de {employeeRecords.length} empleado(s). Modulos definidos: {employeeModules.length}.
              </p>

              <div className="artist-record-list">
                {employeeRecords.length === 0 && (
                  <p className="field-help">Todavia no hay empleados cargados.</p>
                )}
                {employeeRecords.length > 0 && filteredEmployeeRecords.length === 0 && (
                  <p className="field-help">No hay empleados que coincidan con la busqueda.</p>
                )}

                {filteredEmployeeRecords.map((item) => {
                  const enabledPermissions = item.permissions.filter((permission) => permission.can_access).length;
                  const primaryUser = item.users?.[0];
                  return (
                    <div className={`artist-record-item ${item.active ? "" : "inactive"}`} key={item.id}>
                      <div>
                        <strong>{item.display_name}</strong>
                        <span>{item.active ? "Empleado activo" : "Empleado inactivo"}</span>
                      </div>
                      <div className="artist-record-meta">
                        <span>{item.functions.length ? item.functions.join(" / ") : "Sin funcion"}</span>
                        <span>{item.phone || "Sin telefono"}</span>
                        <span>{item.email || "Sin email"}</span>
                        <span>{item.active ? "Activo" : "Inactivo"}</span>
                      </div>
                      <div className="artist-record-meta">
                        <span>{employeeCompensationLabels[item.compensation_type] || "Sin compensacion fija"}</span>
                        {item.compensation_type !== "none" && item.compensation_type !== "booking_commission_only" && (
                          <span>{employeeSalaryAmount(item.salary_currency, item.salary_amount || 0)} mensual</span>
                        )}
                        {item.salary_notes && <span>{item.salary_notes}</span>}
                      </div>
                      <div className="artist-record-meta">
                        <span>{primaryUser ? `Usuario: ${primaryUser.username}` : "Sin usuario"}</span>
                        <span>{primaryUser ? `Rol: ${primaryUser.global_role}` : "Sin rol"}</span>
                        <span>{primaryUser?.active ? "Login activo" : primaryUser ? "Login inactivo" : "Login pendiente"}</span>
                        <span>{primaryUser?.has_password ? "Con contrasena" : "Sin contrasena"}</span>
                        {primaryUser?.must_change_password && <span>Cambio requerido</span>}
                        <span>{primaryUser?.auth_source || "Sin origen auth"}</span>
                      </div>
                      {item.address && <p>{item.address}</p>}
                      {item.notes && <p>{item.notes}</p>}
                      <div className="booking-status">
                        <span>{enabledPermissions} permiso(s) con acceso</span>
                        {item.display_name.toLowerCase() === "ruben elkowich" && <span>Super-admin</span>}
                      </div>
                      <div className="booking-actions">
                        <button type="button" onClick={() => editEmployeeRecord(item)}>Editar</button>
                        <button type="button" onClick={() => resetEmployeePassword(item)} disabled={employeeLoading}>
                          Establecer contrasena default
                        </button>
                        {item.active && item.display_name.toLowerCase() !== "ruben elkowich" && (
                          <button type="button" className="secondary-danger" onClick={() => deactivateEmployeeRecord(item)}>
                            Desactivar
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          </div>
        )}

        {view === "booking" && bookingSurface === "settlement" && bookingWorkspaceMode === "individual" && (
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

              {!bookingEditingId && renderBookingAgendaPrefill("individual")}
              {!bookingEditingId && (
                <p className="field-help">
                  {bookingAgendaEventId
                    ? `Vinculada a Agenda #${bookingAgendaEventId}.`
                    : "Si el show no existe en Agenda, se creará y vinculará al guardar."}
                </p>
              )}

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
                        venueShortfallPolicy: checked ? current.venueShortfallPolicy : "deuda_boliche",
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
                    <div className="row">
                      <label className="check-row">
                        <input
                          type="radio"
                          name="booking_venue_shortfall_policy"
                          checked={bookingForm.venueShortfallPolicy === "deuda_boliche"}
                          onChange={() => updateBookingField("venueShortfallPolicy", "deuda_boliche")}
                        />
                        <span>Dejar saldo al boliche</span>
                      </label>
                      <label className="check-row">
                        <input
                          type="radio"
                          name="booking_venue_shortfall_policy"
                          checked={bookingForm.venueShortfallPolicy === "ajustar_cachet"}
                          onChange={() => updateBookingField("venueShortfallPolicy", "ajustar_cachet")}
                        />
                        <span>Ajustar cachet al cobrado</span>
                      </label>
                    </div>
                    <label htmlFor="booking_venue_payment_notes">Nota deuda boliche</label>
                    <textarea id="booking_venue_payment_notes" value={bookingForm.venuePaymentNotes} onChange={(event) => updateBookingField("venuePaymentNotes", event.target.value)} placeholder="Ej: cachet pactado 1.500.000, el venue pago 1.000.000 y queda deuda." />
                    <p className="field-help">
                      Con saldo al boliche, el show liquida sobre el cachet pactado y la diferencia queda pendiente.
                      Con ajuste de cachet, liquida sobre el cobrado real y no genera deuda del boliche.
                    </p>
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
                    <h2>Comision directa / booking fee</h2>
                    <p>Usalo cuando una comision se resuelve antes del split del artista.</p>
                  </div>
                  <div className="button-row">
                    <button type="button" onClick={() => addBookingDirectCommission("salida_directa")}>Salida directa</button>
                    <button type="button" onClick={() => addBookingDirectCommission("incorpora_base")}>Suma a base</button>
                  </div>
                </div>

                {bookingForm.directCommissions.length === 0 && (
                  <p className="field-help">Sin comision directa. Para shows comunes no hace falta cargar nada aca.</p>
                )}

                {bookingForm.directCommissions.length > 0 && (
                  <div className="adjustment-summary">
                    <span>Total fee {localAmount(bookingDirectCommissionSummary.total, bookingForm.currency)}</span>
                    <span>Sale directo {localAmount(bookingDirectCommissionSummary.outgoing, bookingForm.currency)}</span>
                    <span>Suma a base {localAmount(bookingDirectCommissionSummary.incorporated, bookingForm.currency)}</span>
                    <span>Neto para split {localAmount(bookingSuggestion.splitBase, bookingForm.currency)}</span>
                  </div>
                )}

                {bookingForm.directCommissions.map((commission, index) => (
                  <div className="adjustment-card" key={commission.uid}>
                    <div className="adjustment-card-title">
                      <strong>Comision directa {index + 1}</strong>
                      <button type="button" onClick={() => removeBookingDirectCommission(commission.uid)}>Quitar</button>
                    </div>

                    <div className="row four">
                      <div>
                        <label htmlFor={`direct_commission_concept_${commission.uid}`}>Concepto</label>
                        <input id={`direct_commission_concept_${commission.uid}`} value={commission.concept} onChange={(event) => updateBookingDirectCommissionField(commission.uid, "concept", event.target.value)} placeholder="Booking fee, Marce, Gaston" />
                      </div>
                      <div>
                        <label htmlFor={`direct_commission_recipient_${commission.uid}`}>Quien cobra / recibe</label>
                        <input id={`direct_commission_recipient_${commission.uid}`} value={commission.recipient} onChange={(event) => updateBookingDirectCommissionField(commission.uid, "recipient", event.target.value)} placeholder="Marce, Gaston, otro" />
                      </div>
                      <div>
                        <label htmlFor={`direct_commission_destination_${commission.uid}`}>Tratamiento</label>
                        <select id={`direct_commission_destination_${commission.uid}`} value={commission.destination} onChange={(event) => updateBookingDirectCommissionField(commission.uid, "destination", event.target.value as "salida_directa" | "incorpora_base")}>
                          <option value="salida_directa">Sale directo</option>
                          <option value="incorpora_base">Suma a base</option>
                        </select>
                      </div>
                      <div>
                        <label htmlFor={`direct_commission_amount_${commission.uid}`}>Importe</label>
                        <input id={`direct_commission_amount_${commission.uid}`} inputMode="decimal" value={commission.amount} onChange={(event) => updateBookingDirectCommissionField(commission.uid, "amount", event.target.value)} />
                      </div>
                    </div>

                    <p className="field-help">
                      Sale directo baja el neto del show. Suma a base queda trazado como booking fee, pero vuelve a la base del artista antes del split.
                    </p>
                    <label htmlFor={`direct_commission_notes_${commission.uid}`}>Nota</label>
                    <textarea id={`direct_commission_notes_${commission.uid}`} value={commission.notes} onChange={(event) => updateBookingDirectCommissionField(commission.uid, "notes", event.target.value)} />
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

                    {adjustment.destination === "producer" && (
                      <label className="inline-check">
                        <input
                          type="checkbox"
                          checked={adjustment.recoveryAutoApply}
                          onChange={(event) => updateBookingPreSplitAdjustmentField(adjustment.uid, "recoveryAutoApply", event.target.checked)}
                        />
                        Imputar como recupero al saldo pendiente mas viejo
                      </label>
                    )}
                    {adjustment.destination === "producer" && adjustment.recoveryAutoApply && (
                      <p className="field-help">
                        Al guardar, el sistema aplica este importe por FIFO contra proyectos recuperables abiertos del artista.
                        Si no hay saldo abierto, no permite guardar para evitar una imputacion falsa.
                      </p>
                    )}

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
                  <p className="field-help">Sin caja detallada. Podes usar los campos pagado/rendido de abajo como antes.</p>
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
                    <p className="field-help">El ingreso de Indyana se mantiene. Esta marca solo bloquea la comision general, salvo reglas particulares en Comisiones.</p>
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

              <button type="submit" disabled={bookingLoading || bookingArtists.length === 0 || (bookingEditingId ? !canEditModule("booking") : !canCreateModule("booking"))}>
                {bookingLoading ? "Guardando..." : bookingEditingId ? "Actualizar show" : "Guardar show"}
              </button>
              {!(bookingEditingId ? canEditModule("booking") : canCreateModule("booking")) && (
                <p className="field-help">Tu usuario puede consultar la pantalla, pero no tiene permiso para esta accion.</p>
              )}
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
                      <span>{bookingOpenTargetBalance(item, "venue") > 0.01 ? "Deuda boliche" : item.settlement_status || "pendiente"}</span>
                      <span>{ars(bookingOpenBalanceAmount(item))}</span>
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
                      <span className={bookingSettlementIsClosed(item.settlement_status) && bookingOpenBalanceAmount(item) <= 0.01 ? "status-ok" : "status-warn"}>
                        Cierre: {item.settlement_status || "pendiente"}
                      </span>
                      {Math.abs(bookingOpenTargetBalance(item, "producer")) > 0.01 && (
                        <span className="status-danger">
                          {bookingOpenTargetBalance(item, "producer") > 0 ? "Saldo VPO" : "VPO cobro de mas"} {ars(Math.abs(bookingOpenTargetBalance(item, "producer")))}
                        </span>
                      )}
                      {Math.abs(bookingOpenTargetBalance(item, "artist")) > 0.01 && (
                        <span className="status-danger">
                          {bookingOpenTargetBalance(item, "artist") > 0 ? "Saldo artista" : "Artista cobro de mas"} {ars(Math.abs(bookingOpenTargetBalance(item, "artist")))}
                        </span>
                      )}
                      {Math.abs(bookingOpenTargetBalance(item, "venue")) > 0.01 && (
                        <span className="status-danger">Deuda boliche {ars(bookingOpenTargetBalance(item, "venue"))}</span>
                      )}
                      {item.show_expenses.length > 0 && <span>{item.show_expenses.length} gasto(s)</span>}
                      {item.pre_split_adjustments.length > 0 && <span>{item.pre_split_adjustments.length} ajuste(s) pre split</span>}
                      {(item.external_shares || []).length > 0 && <span>{item.external_shares.length} tercero(s)</span>}
                      {item.receipt_refs.length > 0 && <span>{item.receipt_refs.length} comprobante(s)</span>}
                      {item.artist_adjustments.length > 0 && <span>{item.artist_adjustments.length} ajuste(s)</span>}
                      {(item.account_applications || []).length > 0 && <span>{item.account_applications?.length} aplicacion(es) cuenta</span>}
                    </div>
                    {bookingAccountShowId === item.id && (
                      <div className="booking-account-panel">
                        <div className="section-heading compact-heading">
                          <div>
                            <h3>Aplicar saldo de cuenta</h3>
                            <p>Registra pagos, reintegros o compensaciones posteriores sin reescribir la liquidacion.</p>
                          </div>
                          <button type="button" className="secondary-danger" onClick={() => setBookingAccountShowId(null)}>
                            Cerrar
                          </button>
                        </div>
                        <div className="booking-account-balances">
                          {(["artist", "producer", "venue"] as BookingAccountTarget[]).map((target) => (
                            <button
                              type="button"
                              key={`${item.id}-${target}`}
                              className={bookingAccountForm.targetBalance === target ? "active" : ""}
                              onClick={() => updateBookingAccountTarget(item, target)}
                              disabled={Math.abs(bookingOpenTargetBalance(item, target)) <= 0.01}
                            >
                              <span>{bookingAccountTargetLabel(item, target)}</span>
                              <strong>{ars(Math.abs(bookingOpenTargetBalance(item, target)))}</strong>
                            </button>
                          ))}
                        </div>
                        <div className="row four">
                          <div>
                            <label htmlFor={`booking_account_date_${item.id}`}>Fecha</label>
                            <input id={`booking_account_date_${item.id}`} type="date" value={bookingAccountForm.applicationDate} onChange={(event) => updateBookingAccountField("applicationDate", event.target.value)} />
                          </div>
                          <div>
                            <label htmlFor={`booking_account_type_${item.id}`}>Tipo</label>
                            <select id={`booking_account_type_${item.id}`} value={bookingAccountForm.applicationType} onChange={(event) => updateBookingAccountField("applicationType", event.target.value as BookingAccountApplicationForm["applicationType"])}>
                              <option value="artist_payment">Pago a artista</option>
                              <option value="artist_reimbursement">Reintegro artista</option>
                              <option value="producer_reimbursement">Rendicion a Indyana</option>
                              <option value="venue_payment">Pago boliche</option>
                              <option value="compensation">Compensacion</option>
                              <option value="adjustment">Ajuste</option>
                            </select>
                          </div>
                          <div>
                            <label htmlFor={`booking_account_amount_${item.id}`}>Importe</label>
                            <input id={`booking_account_amount_${item.id}`} inputMode="decimal" value={bookingAccountForm.amount} onChange={(event) => updateBookingAccountField("amount", event.target.value)} />
                          </div>
                          <div>
                            <label htmlFor={`booking_account_method_${item.id}`}>Metodo</label>
                            <select id={`booking_account_method_${item.id}`} value={bookingAccountForm.paymentMethod} onChange={(event) => updateBookingAccountField("paymentMethod", event.target.value as BookingAccountApplicationForm["paymentMethod"])}>
                              <option value="transferencia">Transferencia</option>
                              <option value="efectivo">Efectivo</option>
                              <option value="compensacion">Compensacion</option>
                              <option value="ajuste">Ajuste</option>
                              <option value="otro">Otro</option>
                            </select>
                          </div>
                        </div>
                        <div className="row three">
                          <div>
                            <label htmlFor={`booking_account_counterparty_${item.id}`}>Contraparte</label>
                            <input id={`booking_account_counterparty_${item.id}`} value={bookingAccountForm.counterparty} onChange={(event) => updateBookingAccountField("counterparty", event.target.value)} />
                          </div>
                          <div>
                            <label htmlFor={`booking_account_linked_${item.id}`}>Show compensado</label>
                            <input id={`booking_account_linked_${item.id}`} inputMode="numeric" value={bookingAccountForm.linkedShowId} onChange={(event) => updateBookingAccountField("linkedShowId", event.target.value)} placeholder="ID opcional" />
                          </div>
                          <div>
                            <label htmlFor={`booking_account_proofs_${item.id}`}>Comprobantes</label>
                            <input id={`booking_account_proofs_${item.id}`} value={bookingAccountForm.proofRefs} onChange={(event) => updateBookingAccountField("proofRefs", event.target.value)} placeholder="Link o ruta" />
                          </div>
                        </div>
                        <label htmlFor={`booking_account_notes_${item.id}`}>Nota</label>
                        <textarea id={`booking_account_notes_${item.id}`} value={bookingAccountForm.notes} onChange={(event) => updateBookingAccountField("notes", event.target.value)} />
                        <div className="booking-actions">
                          <button type="button" onClick={() => submitBookingAccountApplication(item)} disabled={bookingLoading}>
                            Aplicar saldo
                          </button>
                        </div>
                      </div>
                    )}
                    <div className="booking-actions">
                      {canEditModule("booking") && <button type="button" onClick={() => editBookingShow(item)}>Editar</button>}
                      {canEditModule("booking") && bookingOpenBalanceAmount(item) > 0.01 && (
                        <button type="button" onClick={() => openBookingAccountApplication(item)}>
                          Saldar / aplicar
                        </button>
                      )}
                      {canApproveModule("booking") && (
                        <button type="button" className="secondary-danger" onClick={() => deleteBookingShow(item)}>
                          Eliminar
                        </button>
                      )}
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
