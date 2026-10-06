"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { ArrowLeft, FilePenLine, Plus, RefreshCw, Search } from "lucide-react";
import styles from "./MasterContractsModule.module.css";

export type ArtistContract = {
  artist_key: string;
  artist_name: string;
  indyana_percent: number;
  has_contract: boolean;
  effective_from: string | null;
  is_project: boolean;
  is_active: boolean;
  notes: string;
  version: number;
  updated_by: string;
  updated_at: string;
};

type Draft = Pick<ArtistContract, "artist_name" | "effective_from" | "is_project" | "is_active" | "notes"> & {
  indyana_percent: number | null;
  has_contract: boolean | null;
  version: number;
};
type Message = { type: "ok" | "error"; text: string };

const blankDraft = (): Draft => ({
  artist_name: "", indyana_percent: null, has_contract: null,
  effective_from: null, is_project: false, is_active: true, notes: "", version: 0,
});

export function ArtistContractsPanel({ canEdit, onBack, onMessage }: {
  canEdit: boolean;
  onBack: () => void;
  onMessage: (message: Message | null) => void;
}) {
  const [items, setItems] = useState<ArtistContract[]>([]);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState<Draft>(blankDraft);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/master-contract-artists", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "No se pudieron cargar los contratos.");
      setItems(data.items);
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudieron cargar los contratos." });
    } finally {
      setLoading(false);
    }
  }, [onMessage]);

  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => items.filter((item) => item.artist_name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())), [items, query]);
  const selected = items.find((item) => item.artist_key === selectedKey);
  const changed = selected
    ? draft.artist_name !== selected.artist_name || draft.indyana_percent !== selected.indyana_percent
      || draft.has_contract !== selected.has_contract || draft.effective_from !== selected.effective_from
      || draft.is_project !== selected.is_project || draft.is_active !== selected.is_active
      || draft.notes !== selected.notes
    : Boolean(draft.artist_name.trim());

  function select(item: ArtistContract) {
    if (changed && !window.confirm("Hay cambios sin guardar. ¿Abrir otro contrato?")) return;
    setSelectedKey(item.artist_key);
    setDraft({
      artist_name: item.artist_name, indyana_percent: item.indyana_percent,
      has_contract: item.has_contract, effective_from: item.effective_from,
      is_project: item.is_project, is_active: item.is_active, notes: item.notes, version: item.version,
    });
  }

  function newContract() {
    if (changed && !window.confirm("Hay cambios sin guardar. ¿Crear otro contrato?")) return;
    setSelectedKey(null);
    setDraft(blankDraft());
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!canEdit || draft.indyana_percent === null || draft.has_contract === null) return;
    setSaving(true);
    try {
      const response = await fetch("/api/master-contract-artists", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...draft, expected_version: draft.version }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "No se pudo guardar el contrato.");
      setSelectedKey(data.artist_key);
      setDraft({
        artist_name: data.artist_name, indyana_percent: data.indyana_percent,
        has_contract: data.has_contract, effective_from: data.effective_from,
        is_project: data.is_project, is_active: data.is_active, notes: data.notes, version: data.version,
      });
      onMessage({ type: "ok", text: "Contrato guardado. Solo se sugerirá en fichas nuevas; los repartos guardados no cambiaron." });
      await load();
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo guardar el contrato." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={styles.workspace}>
      <header className={styles.detailHeader}>
        <button type="button" className={styles.iconButton} title="Volver a repartos por ISRC" aria-label="Volver a repartos por ISRC" onClick={() => {
          if (!changed || window.confirm("Hay cambios sin guardar. ¿Volver al catálogo?")) onBack();
        }}><ArrowLeft size={19} /></button>
        <div className={styles.heading}><span>Contratos</span><h1>Contratos de artistas</h1><p>Condiciones generales del master, independientes de cada ISRC.</p></div>
        <button type="button" className={styles.iconButton} title="Actualizar contratos" aria-label="Actualizar contratos" disabled={loading} onClick={() => void load()}><RefreshCw size={18} /></button>
      </header>
      <div className={styles.artistLayout}>
        <div className={styles.artistList}>
          <div className={styles.artistListTools}>
            <div className={styles.searchBox}><Search size={18} /><input aria-label="Buscar artista" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar artista" /></div>
            {canEdit && <button type="button" className={styles.iconButton} title="Nuevo contrato" aria-label="Nuevo contrato" onClick={newContract}><Plus size={18} /></button>}
          </div>
          <div className={styles.listMeta}><span>{loading ? "Cargando..." : `${filtered.length} artistas`}</span></div>
          <div className={styles.artistRows}>
            {filtered.map((item) => <button type="button" key={item.artist_key} className={`${styles.artistRow} ${selectedKey === item.artist_key ? styles.artistRowSelected : ""}`} onClick={() => select(item)}>
              <span><strong>{item.artist_name}</strong><small>{item.is_project ? "Proyecto" : "Artista"} · {item.is_active ? "Activo" : "Inactivo"}</small></span>
              <span className={styles.artistPercent}>{item.indyana_percent}%<small>Indyana</small></span>
            </button>)}
            {!loading && filtered.length === 0 && <p className={styles.artistEmpty}>No hay contratos para esta búsqueda.</p>}
          </div>
        </div>
        <form className={styles.artistForm} onSubmit={(event) => void save(event)}>
          <div className={styles.sectionHeading}><h2>{selected ? selected.artist_name : "Nuevo contrato"}</h2><span>{selected ? `Versión ${selected.version}` : "Sin guardar"}</span></div>
          <div className={styles.artistFormFields}>
            <label>Artista o proyecto<input required maxLength={200} disabled={!canEdit || Boolean(selected)} value={draft.artist_name} onChange={(event) => setDraft({ ...draft, artist_name: event.target.value })} placeholder="Nombre del artista" /></label>
            <label>Indyana %<input required type="number" inputMode="decimal" min="0" max="100" step="0.01" disabled={!canEdit} value={draft.indyana_percent ?? ""} onChange={(event) => setDraft({ ...draft, indyana_percent: event.target.value === "" ? null : Number(event.target.value) })} /></label>
            <label>Artista %<input type="number" value={draft.indyana_percent === null ? "" : 100 - draft.indyana_percent} readOnly /></label>
            <label>¿Existe contrato?<select required disabled={!canEdit} value={draft.has_contract === null ? "unknown" : draft.has_contract ? "yes" : "no"} onChange={(event) => setDraft({ ...draft, has_contract: event.target.value === "unknown" ? null : event.target.value === "yes" })}><option value="unknown" disabled>Seleccionar</option><option value="yes">Sí</option><option value="no">No</option></select></label>
            <label>Vigente desde<input type="month" disabled={!canEdit} value={draft.effective_from || ""} onChange={(event) => setDraft({ ...draft, effective_from: event.target.value || null })} /></label>
          </div>
          <label className={styles.checkboxLine}><input type="checkbox" disabled={!canEdit} checked={draft.is_project} onChange={(event) => setDraft({ ...draft, is_project: event.target.checked })} /><span>Proyecto con invitados que pueden tener contrato propio</span></label>
          <label className={styles.checkboxLine}><input type="checkbox" disabled={!canEdit} checked={draft.is_active} onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })} /><span>Usar como propuesta en fichas nuevas</span></label>
          <label className={styles.notesLabel}>Notas<textarea rows={3} maxLength={3000} disabled={!canEdit} value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} /></label>
          <p className={styles.safetyNote}>Una ficha de ISRC puede tener un reparto distinto. Ningún contrato se aplica automáticamente a los informes.</p>
          {selected && <p className={styles.auditLine}>Último guardado: {selected.updated_at} por {selected.updated_by}.</p>}
          {canEdit && <div className={styles.actions}><button type="submit" className={styles.primaryButton} disabled={saving || !changed || draft.indyana_percent === null || draft.has_contract === null}><FilePenLine size={16} />{saving ? "Guardando..." : "Guardar contrato"}</button></div>}
        </form>
      </div>
    </section>
  );
}
