"use client";

import { useEffect, useRef, useState } from "react";
import { CheckSquare2, ChevronDown, Square } from "lucide-react";
import styles from "./DigitalIncome.module.css";

export type SelectionOption = { key: string; label: string };
export type SelectionIntent = "all" | "exclusive" | "toggle";

type Props = {
  label: string;
  options: SelectionOption[];
  allKeys: string[];
  selected: string[] | null;
  disabled?: boolean;
  onChange: (selected: string[] | null, intent: SelectionIntent) => void;
};

export default function SelectionMenu({ label, options, allKeys, selected, disabled, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  const selectedKeys = selected === null ? allKeys : selected;
  const visibleSelected = options.filter((item) => selectedKeys.includes(item.key));
  const summary = visibleSelected.length === options.length ? "Todas"
    : visibleSelected.length === 0 ? "Ninguna"
    : visibleSelected.length === 1 ? visibleSelected[0].label
    : `${visibleSelected.length} de ${options.length}`;

  function toggle(key: string) {
    const next = selectedKeys.includes(key)
      ? selectedKeys.filter((item) => item !== key)
      : [...selectedKeys, key];
    onChange(next.length === allKeys.length ? null : next, "toggle");
  }

  return <div className={styles.selectionField} ref={root} onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}>
    <span className={styles.selectionLabel}>{label}</span>
    <button type="button" className={styles.selectionTrigger} onClick={() => setOpen(!open)} aria-expanded={open} disabled={disabled}>
      <span>{summary}</span><ChevronDown size={16} aria-hidden="true" />
    </button>
    {open && <div className={styles.selectionPopover} role="group" aria-label={label}>
      <div className={`${styles.selectionRow} ${styles.selectionAllRow}`}>
        <button type="button" className={styles.selectionName} onClick={() => onChange(null, "all")} disabled={disabled}>Todas</button>
        <button type="button" className={styles.selectionCheck} role="checkbox" aria-checked={selected === null || selectedKeys.length === allKeys.length} aria-label={`Todas las ${label.toLowerCase()}`} onClick={() => selectedKeys.length === allKeys.length ? onChange([], "exclusive") : onChange(null, "all")} disabled={disabled}>
          {selectedKeys.length === allKeys.length ? <CheckSquare2 size={16} /> : <Square size={16} />}
        </button>
      </div>
      <div className={styles.selectionList}>
        {options.map((item) => {
          const checked = selectedKeys.includes(item.key);
          return <div className={styles.selectionRow} key={item.key}>
            <button type="button" className={styles.selectionName} onClick={() => onChange([item.key], "exclusive")} disabled={disabled}>{item.label}</button>
            <button type="button" className={styles.selectionCheck} role="checkbox" aria-checked={checked} aria-label={item.label} onClick={() => toggle(item.key)} disabled={disabled}>
              {checked ? <CheckSquare2 size={16} /> : <Square size={16} />}
            </button>
          </div>;
        })}
      </div>
    </div>}
  </div>;
}
