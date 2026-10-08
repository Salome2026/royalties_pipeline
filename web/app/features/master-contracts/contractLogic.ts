export type ParticipationRule = {
  treatment: "direct" | "artist_contract" | "project_owners";
  retained_percent?: number | null;
  retained_recipient?: string;
  contract_artist?: string | null;
  contract_version?: number | null;
};

export type Participant = {
  artist: string;
  percent: number | null;
  internal_contract_indyana_percent: number | null;
  rule?: ParticipationRule | null;
};

export type Allocation = {
  principal: string;
  indyana_percent: number | null;
  principal_percent: number | null;
  apply_guest_contracts: boolean;
  participants: Participant[];
  principal_rule?: ParticipationRule | null;
};

export type MasterAgreement = {
  id: string;
  label: string;
  commercialization: "pending" | "distribution" | "master";
  allocation_model?: "flat" | "pools";
  contract_kind?: "simple" | "project";
  master_pool_percent?: number | null;
  company_name?: string;
  owner_split_mode?: "percent" | "equal";
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
    principal_rule: fallback.principal_rule,
  };
}

export function allocationTotals(agreement: MasterAgreement | undefined, allocation: Allocation) {
  const master = agreement?.allocation_model === "pools" ? agreement.master_pool_percent || 0
    : agreement?.commercialization === "master" ? agreement.owners.reduce((sum, owner) => sum + (owner.percent || 0), 0) : 0;
  const participation = (allocation.principal_percent || 0)
    + allocation.participants.reduce((sum, item) => sum + (item.percent || 0), 0)
    + (agreement?.commercialization === "master" || agreement?.allocation_model === "pools" ? 0 : allocation.indyana_percent || 0);
  return { master, participation, general: master + participation };
}

export const beneficiaryKey = (name: string) => name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().replace(/\s+/g, " ").toLowerCase();

export function ownershipTotal(agreement: MasterAgreement): number {
  return agreement.owner_split_mode === "equal" && agreement.owners.length ? 100
    : agreement.owners.reduce((sum, owner) => sum + (owner.percent || 0), 0);
}

export function poolAgreement(agreement: MasterAgreement, allocation: Allocation): MasterAgreement {
  if (agreement.allocation_model === "pools") return agreement;
  const pool = agreement.commercialization === "master"
    ? agreement.owners.reduce((sum, owner) => sum + (owner.percent || 0), 0) : allocation.indyana_percent;
  return {
    ...agreement, allocation_model: "pools", contract_kind: "simple", master_pool_percent: pool,
    company_name: "Indyana", owner_split_mode: "percent",
    // Legacy owners held points of total income; convert only on explicit operator action.
    owners: agreement.owners.map((owner) => ({ ...owner, percent: owner.percent === null ? null
      : pool ? owner.percent * 100 / pool : agreement.owners.length === 1 ? 100 : null })),
    allocation: { ...allocation, principal_rule: { treatment: "direct" }, participants: allocation.participants.map((item) => ({
      ...item, rule: allocation.apply_guest_contracts && item.internal_contract_indyana_percent !== null
        ? { treatment: "artist_contract", retained_percent: item.internal_contract_indyana_percent, retained_recipient: "Indyana" }
        : { treatment: "direct" },
    })) },
  };
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
      ...(agreement.commercialization === "master" ? agreement.owners.map((owner) => owner.percent) : [allocation.indyana_percent]),
      ...(agreement.allocation_model === "pools" ? [agreement.master_pool_percent ?? null, allocation.principal_rule?.retained_percent ?? null,
        ...allocation.participants.map((item) => item.rule?.retained_percent ?? null)] : [])];
    if (values.some((value) => value !== null && (!Number.isFinite(value) || value < 0 || value > 100))) errors.push(`${label}: los porcentajes deben estar entre 0 y 100.`);
    const total = allocationTotals(agreement, allocation).general;
    if (total > 100 + tolerance) errors.push(`${label}: master y participaciones suman ${total.toLocaleString("es-AR", { maximumFractionDigits: 2 })}%; no pueden superar 100%.`);
    if (agreement.allocation_model === "pools") {
      if (agreement.commercialization === "master" && ownershipTotal(agreement) > 100 + tolerance) errors.push(`${label}: los titulares de la bolsa master superan 100%.`);
      const ownerKeys = agreement.owners.map((item) => beneficiaryKey(item.name)).filter(Boolean);
      if (new Set(ownerKeys).size !== ownerKeys.length) errors.push(`${label}: hay titulares repetidos.`);
      const rows = [{ artist: allocation.principal, rule: allocation.principal_rule }, ...allocation.participants];
      const keys = rows.map((item) => beneficiaryKey(item.artist)).filter(Boolean);
      if (new Set(keys).size !== keys.length) errors.push(`${label}: hay participantes repetidos.`);
      if (rows.some((row) => row.rule?.treatment === "project_owners")
        && (agreement.commercialization === "distribution" || agreement.contract_kind !== "project")) errors.push(`${label}: el reparto entre socios requiere un proyecto con master.`);
    }
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

export type PreviewRow = { artist: string; percent: number; amount: number; origins: Array<{ label: string; percent: number }> };

export function previewAllocation(agreement: MasterAgreement, allocation: Allocation, amount: number): PreviewRow[] | null {
  if (contractErrors([agreement], allocation).length) return null;
  if (!allocation.principal.trim() || allocation.principal_percent === null
    || allocation.participants.some((item) => !item.artist.trim() || item.percent === null)
    || Math.abs(allocationTotals(agreement, allocation).general - 100) > tolerance) return null;
  if (agreement.commercialization === "pending") return null;
  if (agreement.commercialization === "master"
    ? !agreement.owners.length || agreement.owners.some((owner) => !owner.name.trim()
      || (agreement.owner_split_mode !== "equal" && owner.percent === null))
    : agreement.allocation_model !== "pools" && allocation.indyana_percent === null) return null;
  if (agreement.allocation_model === "pools") return previewPools(agreement, allocation, amount);
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
  return settleRows([...rows, { artist: allocation.principal, percent: allocation.principal_percent }, ...guests]
    .map((row) => ({ ...row, label: "Reparto guardado" })), amount);
}

function previewPools(agreement: MasterAgreement, allocation: Allocation, amount: number): PreviewRow[] | null {
  if (agreement.master_pool_percent == null || (agreement.commercialization === "master"
    && Math.abs(ownershipTotal(agreement) - 100) > tolerance)) return null;
  if (agreement.commercialization === "distribution" && !((agreement.company_name ?? "Indyana").trim())) return null;
  const rows: Array<{ artist: string; percent: number; label: string }> = [];
  function owners(base: number, label: string) {
    const total = ownershipTotal(agreement);
    agreement.owners.forEach((owner) => rows.push({ artist: owner.name, label,
      percent: base * (agreement.owner_split_mode === "equal" ? 1 / agreement.owners.length : (owner.percent || 0) / total) }));
  }
  if (agreement.commercialization === "master") owners(agreement.master_pool_percent, "Titular del master");
  else rows.push({ artist: agreement.company_name || "Indyana", percent: agreement.master_pool_percent, label: "Distribución" });
  const participants = [{ artist: allocation.principal, percent: allocation.principal_percent, rule: allocation.principal_rule }, ...allocation.participants];
  for (const row of participants) {
    const base = row.percent || 0;
    const rule = row.rule || { treatment: "direct" };
    if (rule.treatment === "project_owners") owners(base, `Participación de ${row.artist}`);
    else if (rule.treatment === "artist_contract") {
      if (rule.retained_percent == null || !rule.retained_recipient?.trim()) return null;
      const retained = base * rule.retained_percent / 100;
      rows.push({ artist: rule.retained_recipient, percent: retained, label: `Contrato de ${row.artist}` });
      rows.push({ artist: row.artist, percent: base - retained, label: "Participación después de contrato" });
    } else rows.push({ artist: row.artist, percent: base, label: "Participación directa" });
  }
  return settleRows(rows, amount);
}

function settleRows(rows: Array<{ artist: string; percent: number; label: string }>, amount: number): PreviewRow[] {
  const grouped = new Map<string, PreviewRow>();
  for (const row of rows) {
    const key = beneficiaryKey(row.artist);
    const result = grouped.get(key) || { artist: row.artist.trim(), percent: 0, amount: 0, origins: [] };
    result.percent += row.percent;
    result.origins.push({ label: row.label, percent: row.percent });
    grouped.set(key, result);
  }
  const result = [...grouped.values()];
  const totalPercent = result.reduce((sum, row) => sum + row.percent, 0);
  // Round once, after consolidation; largest remainders assign every cent, including adjustments.
  const cents = Math.round(Math.abs(amount) * 100 + 1e-8);
  const exact = result.map((row) => cents * row.percent / totalPercent);
  const floor = exact.map((value) => Math.floor(value + 1e-8));
  const order = result.map((_, index) => index).sort((a, b) => (exact[b] - floor[b]) - (exact[a] - floor[a]) || a - b);
  const remaining = cents - floor.reduce((sum, value) => sum + value, 0);
  order.slice(0, remaining).forEach((index) => floor[index]++);
  result.forEach((row, index) => { row.amount = (amount < 0 ? -1 : 1) * floor[index] / 100; });
  return result;
}
