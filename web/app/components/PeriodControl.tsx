"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  MONTH_NAMES_SHORT,
  PeriodMode,
  PeriodProfile,
  PeriodSelection,
  formatMonth,
  resolvePeriod,
} from "../lib/period";

type PeriodControlProps = {
  id: string;
  label: string;
  profile: PeriodProfile;
  selection: PeriodSelection;
  onChange: (selection: PeriodSelection) => void;
  minMonth?: string | null;
  maxMonth?: string | null;
  variant?: "range" | "until";
  presets?: PeriodMode[];
  helperText?: string;
};

function yearsFor(minMonth?: string | null, maxMonth?: string | null) {
  const currentYear = new Date().getFullYear();
  const firstYear = minMonth && /^\d{4}-\d{2}$/.test(minMonth) ? Number(minMonth.slice(0, 4)) : 2020;
  const lastYear = maxMonth && /^\d{4}-\d{2}$/.test(maxMonth) ? Number(maxMonth.slice(0, 4)) : Math.max(2030, currentYear + 2);
  return Array.from({ length: Math.max(1, lastYear - firstYear + 1) }, (_, index) => String(firstYear + index));
}

function selectionYear(selection: PeriodSelection, minMonth?: string | null, maxMonth?: string | null) {
  const candidate = selection.startMonth || selection.endMonth;
  if (candidate) return candidate.slice(0, 4);
  const currentYear = String(new Date().getFullYear());
  const years = yearsFor(minMonth, maxMonth);
  if (years.includes(currentYear)) return currentYear;
  return years[years.length - 1] || currentYear;
}

function editableMode(mode: PeriodMode, variant: "range" | "until"): PeriodMode {
  if (variant === "until") return "until_month";
  return mode === "closed_range" ? "closed_range" : "single_month";
}

function clampPair(startMonth: string, endMonth: string) {
  if (startMonth && endMonth && startMonth > endMonth) {
    return { startMonth: endMonth, endMonth: startMonth };
  }
  return { startMonth, endMonth };
}

export function PeriodControl({
  id,
  label,
  profile,
  selection,
  onChange,
  minMonth,
  maxMonth,
  variant = "range",
  presets = ["all"],
  helperText,
}: PeriodControlProps) {
  const [open, setOpen] = useState(false);
  const [draftMode, setDraftMode] = useState<PeriodMode>(editableMode(selection.mode, variant));
  const [activeBound, setActiveBound] = useState<"start" | "end">("start");
  const [year, setYear] = useState(selectionYear(selection, minMonth, maxMonth));
  const rootRef = useRef<HTMLDivElement | null>(null);
  const resolved = useMemo(() => resolvePeriod(selection, profile), [selection, profile]);
  const years = useMemo(() => yearsFor(minMonth, maxMonth), [minMonth, maxMonth]);

  useEffect(() => {
    setYear(selectionYear(selection, minMonth, maxMonth));
    setDraftMode(editableMode(selection.mode, variant));
  }, [selection, minMonth, maxMonth, variant]);

  useEffect(() => {
    function onDocumentMouseDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocumentMouseDown);
    return () => document.removeEventListener("mousedown", onDocumentMouseDown);
  }, []);

  function monthDisabled(value: string) {
    return Boolean((minMonth && value < minMonth) || (maxMonth && value > maxMonth));
  }

  function pickMonth(value: string) {
    if (monthDisabled(value)) return;
    if (variant === "until" || draftMode === "until_month") {
      onChange({ mode: "until_month", endMonth: value });
      setOpen(false);
      return;
    }
    if (draftMode === "single_month" || draftMode === "from_month") {
      onChange(draftMode === "from_month"
        ? { mode: "from_month", startMonth: value }
        : { mode: "single_month", startMonth: value, endMonth: value });
      setOpen(false);
      return;
    }

    const currentStart = selection.startMonth || value;
    const currentEnd = selection.endMonth || value;
    const next = activeBound === "start"
      ? clampPair(value, currentEnd)
      : clampPair(currentStart, value);
    onChange({ mode: "closed_range", ...next });
    setActiveBound(activeBound === "start" ? "end" : "start");
    if (activeBound === "end") setOpen(false);
  }

  function chooseMode(mode: PeriodMode) {
    if (mode === "all" || mode === "last_6_months" || mode === "last_12_months") {
      onChange({ mode });
      setOpen(false);
      return;
    }
    setDraftMode(mode);
    setActiveBound(mode === "until_month" ? "end" : "start");
  }

  const selectedStart = selection.startMonth ? formatMonth(selection.startMonth) : "Elegir";
  const selectedEnd = selection.endMonth ? formatMonth(selection.endMonth) : "Elegir";

  return (
    <div className="period-control" ref={rootRef}>
      <label htmlFor={`${id}_trigger`}>{label}</label>
      <button
        id={`${id}_trigger`}
        type="button"
        className="period-trigger"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <strong>{resolved.label}</strong>
      </button>
      {helperText && <p className="field-help">{helperText}</p>}

      {open && (
        <div className="period-popover" role="dialog" aria-label={label}>
          <div className="period-quick-row">
            {presets.includes("all") && (
              <button type="button" className={selection.mode === "all" ? "active" : ""} onClick={() => chooseMode("all")}>
                Todo
              </button>
            )}
            {presets.includes("last_6_months") && (
              <button type="button" className={selection.mode === "last_6_months" ? "active" : ""} onClick={() => chooseMode("last_6_months")}>
                Últimos 6
              </button>
            )}
            {presets.includes("last_12_months") && (
              <button type="button" className={selection.mode === "last_12_months" ? "active" : ""} onClick={() => chooseMode("last_12_months")}>
                Últimos 12
              </button>
            )}
          </div>

          {variant === "range" ? (
            <div className="period-mode-row">
              <button type="button" className={draftMode === "single_month" ? "active" : ""} onClick={() => chooseMode("single_month")}>
                Mes
              </button>
              <button type="button" className={draftMode === "closed_range" ? "active" : ""} onClick={() => chooseMode("closed_range")}>
                Rango
              </button>
            </div>
          ) : (
            <div className="period-mode-row">
              <button type="button" className="active" onClick={() => chooseMode("until_month")}>
                Hasta
              </button>
            </div>
          )}

          {draftMode === "closed_range" && variant === "range" && (
            <div className="period-bound-row">
              <button type="button" className={activeBound === "start" ? "active" : ""} onClick={() => setActiveBound("start")}>
                Desde <strong>{selectedStart}</strong>
              </button>
              <button type="button" className={activeBound === "end" ? "active" : ""} onClick={() => setActiveBound("end")}>
                Hasta <strong>{selectedEnd}</strong>
              </button>
            </div>
          )}

          <div className="period-year-row">
            <button type="button" onClick={() => {
              const index = years.indexOf(year);
              if (index > 0) setYear(years[index - 1]);
            }}>
              &lt;
            </button>
            <select id={`${id}_year`} value={year} onChange={(event) => setYear(event.target.value)} aria-label="Año">
              {years.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
            <button type="button" onClick={() => {
              const index = years.indexOf(year);
              if (index >= 0 && index < years.length - 1) setYear(years[index + 1]);
            }}>
              &gt;
            </button>
          </div>

          <div className="period-month-grid">
            {MONTH_NAMES_SHORT.map((month, index) => {
              const value = `${year}-${String(index + 1).padStart(2, "0")}`;
              const selected = value === selection.startMonth || value === selection.endMonth;
              return (
                <button
                  type="button"
                  key={value}
                  disabled={monthDisabled(value)}
                  className={selected ? "active" : ""}
                  onClick={() => pickMonth(value)}
                >
                  {month}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
