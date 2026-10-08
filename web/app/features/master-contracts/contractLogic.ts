export type Participant = {
  artist: string;
  percent: number | null;
  internal_contract_indyana_percent: number | null;
};

export type Allocation = {
  principal: string;
  indyana_percent: number | null;
  principal_percent: number | null;
  apply_guest_contracts: boolean;
  participants: Participant[];
};

export type MasterAgreement = {
  id: string;
  label: string;
  commercialization: "pending" | "distribution" | "master";
  owners: Array<{ name: string; percent: number | null }>;
  effective_from: string | null;
  effective_until: string | null;
  allocation?: Allocation | null;
};

export type StatementIncome = { statement_month: string; amount_usd: number };
export const tolerance = 0.0001;

export function agreementAllocation(agreement: MasterAgreement | undefined, fallback: Allocation): Allocation {
  return agreement?.allocation || {
    principal: fallback.principal, indyana_percent: fallback.indyana_percent,
    principal_percent: fallback.principal_percent, apply_guest_contracts: fallback.apply_guest_contracts,
    participants: fallback.participants,
  };
}

export function allocationTotals(agreement: MasterAgreement | undefined, allocation: Allocation) {
  const master = agreement?.commercialization === "master"
    ? agreement.owners.reduce((sum, owner) => sum + (owner.percent || 0), 0) : 0;
  const participation = (allocation.principal_percent || 0)
    + allocation.participants.reduce((sum, item) => sum + (item.percent || 0), 0)
    + (agreement?.commercialization === "master" ? 0 : allocation.indyana_percent || 0);
  return { master, participation, general: master + participation };
}

export function periodBoundary(value: string | null, end = false): string | null {
  if (!value || !/^\d{4}-(0[1-9]|1[0-2])(?:-\d{2})?$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day || 1);
  date.setUTCHours(0, 0, 0, 0);
  if (value.length === 7 && end) date.setUTCMonth(month, 0);
  const normalized = date.toISOString().slice(0, 10);
  return (value.length === 7 ? normalized.slice(0, 7) : normalized) === value ? normalized : null;
}

export function nextAgreementStart(agreements: MasterAgreement[]): string | null {
  if (agreements.some((item) => !item.effective_until)) return null;
  const ends = agreements.map((item) => periodBoundary(item.effective_until, true));
  if (ends.some((value) => !value)) return null;
  const last = ends.filter((value): value is string => !!value).sort().at(-1);
  if (!last) return null;
  const date = new Date(`${last}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

export function contractErrors(agreements: MasterAgreement[], fallback: Allocation): string[] {
  const errors: string[] = [];
  const intervals: Array<{ start: string; end: string; label: string }> = [];
  for (const agreement of agreements) {
    const label = agreement.label || "Contrato";
    const start = periodBoundary(agreement.effective_from);
    const end = periodBoundary(agreement.effective_until, true);
    if ((agreement.effective_from && !start) || (agreement.effective_until && !end)) errors.push(`${label}: fecha inválida.`);
    if (start && end && start > end) errors.push(`${label}: Hasta es anterior a Desde.`);
    if (start) intervals.push({ start, end: end || "9999-12-31", label });
    const allocation = agreementAllocation(agreement, fallback);
    const values = [allocation.principal_percent, ...allocation.participants.flatMap((item) => [item.percent, item.internal_contract_indyana_percent]),
      ...(agreement.commercialization === "master" ? agreement.owners.map((owner) => owner.percent) : [allocation.indyana_percent])];
    if (values.some((value) => value !== null && (!Number.isFinite(value) || value < 0 || value > 100))) errors.push(`${label}: los porcentajes deben estar entre 0 y 100.`);
    const total = allocationTotals(agreement, allocation).general;
    if (total > 100 + tolerance) errors.push(`${label}: master y participaciones suman ${total.toLocaleString("es-AR", { maximumFractionDigits: 2 })}%; no pueden superar 100%.`);
  }
  intervals.sort((a, b) => a.start.localeCompare(b.start));
  for (let index = 1; index < intervals.length; index++) {
    if (intervals[index].start <= intervals[index - 1].end) errors.push(`${intervals[index - 1].label} y ${intervals[index].label}: las vigencias se superponen.`);
  }
  return errors;
}

export function agreementIncome(agreement: MasterAgreement | undefined, income: StatementIncome[], today: string): number | null {
  const start = periodBoundary(agreement?.effective_from || null);
  const end = agreement?.effective_until ? periodBoundary(agreement.effective_until, true) : today;
  if (!start || !end || start > end) return null;
  // Statements are monthly in the published mart and use the first day as their canonical date.
  return income.reduce((sum, item) => {
    const date = `${item.statement_month}-01`;
    return sum + (date >= start && date <= end ? item.amount_usd : 0);
  }, 0);
}

export function previewAllocation(agreement: MasterAgreement, allocation: Allocation, amount: number) {
  if (!allocation.principal.trim() || allocation.principal_percent === null
    || allocation.participants.some((item) => !item.artist.trim() || item.percent === null)
    || Math.abs(allocationTotals(agreement, allocation).general - 100) > tolerance) return null;
  if (agreement.commercialization === "pending") return null;
  if (agreement.commercialization === "master"
    ? !agreement.owners.length || agreement.owners.some((owner) => !owner.name.trim() || owner.percent === null)
    : allocation.indyana_percent === null) return null;
  const rows = agreement.commercialization === "master"
    ? agreement.owners.map((owner) => ({ artist: owner.name, percent: owner.percent || 0 }))
    : [{ artist: "Indyana", percent: allocation.indyana_percent || 0 }];
  let retained = 0;
  const guests = allocation.participants.map((item) => {
    const base = item.percent || 0;
    const retention = allocation.apply_guest_contracts ? base * (item.internal_contract_indyana_percent || 0) / 100 : 0;
    retained += retention;
    return { artist: item.artist, percent: base - retention };
  });
  if (retained) {
    const indyana = rows.find((row) => row.artist.trim().toLowerCase() === "indyana");
    if (indyana) indyana.percent += retained;
    else rows.push({ artist: "Indyana", percent: retained });
  }
  return [...rows, { artist: allocation.principal, percent: allocation.principal_percent }, ...guests]
    .map((row) => ({ ...row, amount: amount * row.percent / 100 }));
}
