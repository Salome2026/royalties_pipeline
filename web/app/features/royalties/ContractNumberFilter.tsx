"use client";

import { useEffect, useState } from "react";
import { Check, LoaderCircle, Search, X } from "lucide-react";
import { parseContractNumbers } from "./contractNumberSelection";
import { requestDistributionReportContracts, type DistributionReportContract } from "./api";
import styles from "./RoyaltyReportModule.module.css";

export function ContractNumberFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<DistributionReportContract[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const parsed = parseContractNumbers(value);
  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true); setError("");
    requestDistributionReportContracts().then((rows) => { if (active) setItems(rows); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "No se pudieron cargar los contratos."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open]);
  function toggle(number: number) {
    if (parsed.error) return;
    onChange((parsed.numbers.includes(number) ? parsed.numbers.filter((n) => n !== number) : [...parsed.numbers, number]).join(", "));
  }
  const normalized = (text: string) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const visible = items.filter((item) => normalized(`${item.number} ${item.label} ${item.sublabel}`).includes(normalized(query)));
  return <div className={styles.field}>
    <label htmlFor="royalty_contract_numbers">Contratos de distribución <em>Opcional</em></label>
    <div className={styles.contractEntry}>
      <input id="royalty_contract_numbers" value={value} onChange={(event) => onChange(event.target.value)} placeholder="Ej. 10010, 10011" aria-describedby="royalty_contract_help" aria-invalid={Boolean(parsed.error)} />
      <button type="button" className={styles.secondaryAction} aria-expanded={open} aria-controls="royalty_contract_picker" onClick={() => setOpen(!open)}><Search size={16} />Buscar contratos</button>
    </div>
    <small id="royalty_contract_help">Ingresá los números separados por comas. El reporte incluirá solo temas vinculados a esos contratos; las palabras clave y demás filtros se aplican dentro de esa selección.</small>
    {parsed.error && <small role="alert">{parsed.error}</small>}
    {parsed.numbers.length > 0 && <div className={styles.artistSelection} aria-label="Contratos seleccionados">
      {parsed.numbers.map((number) => <span key={number}>{number}<button type="button" aria-label={`Quitar contrato ${number}`} onClick={() => toggle(number)}><X size={14} /></button></span>)}
    </div>}
    {open && <div id="royalty_contract_picker" className={styles.contractPicker}>
      <label htmlFor="royalty_contract_search">Buscar por número, sello o subsello</label>
      <input id="royalty_contract_search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ej. Caserio" autoFocus />
      <div className={styles.contractList} aria-label="Contratos disponibles" aria-live="polite">
        {loading ? <small><LoaderCircle size={14} /> Cargando contratos…</small> : error ? <small role="alert">{error}</small> : !visible.length ? <small>No se encontraron contratos.</small> : visible.map((item) => {
          const selected = parsed.numbers.includes(item.number);
          return <button type="button" key={item.number} aria-pressed={selected} disabled={Boolean(parsed.error) || (!selected && parsed.numbers.length >= 100)} onClick={() => toggle(item.number)}>
            <span><strong>{item.number}</strong><small>{item.label}{item.sublabel ? ` / ${item.sublabel}` : ""}</small></span>
            {selected && <Check size={18} />}
          </button>;
        })}
      </div>
    </div>}
  </div>;
}
