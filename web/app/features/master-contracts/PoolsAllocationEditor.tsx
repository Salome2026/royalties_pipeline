"use client";

import { Divide, FilePenLine, Plus, Trash2 } from "lucide-react";
import styles from "./MasterContractsModule.module.css";
import { artistBeneficiaries, type ArtistContract } from "./ArtistContractsPanel";
import { beneficiaryKey, simpleMasterAgreement, ownershipTotal, participantExclusions, poolAgreement, type Allocation, type MasterAgreement, type ParticipationRule } from "./contractLogic";

const numberOrNull = (value: string) => value.trim() === "" ? null : Number(value);
const percent = (value: number) => value.toLocaleString("es-AR", { maximumFractionDigits: 4 });

export function PoolsAllocationEditor({ agreement, allocation, canEdit, artistOptions, artistContracts, onChange, onEditArtist }: {
  agreement: MasterAgreement;
  allocation: Allocation;
  canEdit: boolean;
  artistOptions: string[];
  artistContracts: ArtistContract[];
  onChange: (agreement: MasterAgreement) => void;
  onEditArtist: (artist: string) => void;
}) {
  const isMaster = agreement.commercialization === "master";
  const isProject = agreement.contract_kind === "project";
  const optionsId = `allocation-artists-${agreement.id}`;
  const rows = [{ artist: allocation.principal, percent: allocation.principal_percent, rule: allocation.principal_rule }, ...allocation.participants];
  const remaining = agreement.master_pool_percent == null ? null : 100 - agreement.master_pool_percent;
  const participation = rows.reduce((sum, row) => sum + (row.percent || 0), 0);

  function update(patch: Partial<MasterAgreement>) { onChange({ ...agreement, ...patch }); }
  function updateAllocation(patch: Partial<Allocation>) { update({ allocation: { ...allocation, ...patch } }); }
  function updateRow(index: number, patch: { artist?: string; percent?: number | null; rule?: ParticipationRule }) {
    const exclusions = patch.artist !== undefined ? {
      catalog_participant_exclusions: participantExclusions(allocation, rows[index].artist, patch.artist, artistOptions),
    } : {};
    if (index === 0) updateAllocation({
      ...exclusions,
      ...(patch.artist !== undefined ? { principal: patch.artist } : {}),
      ...(patch.percent !== undefined ? { principal_percent: patch.percent } : {}),
      ...(patch.rule ? { principal_rule: patch.rule } : {}),
    });
    else updateAllocation({ ...exclusions, participants: allocation.participants.map((item, position) => position === index - 1 ? { ...item, ...patch } : item) });
  }

  const simple = isMaster && !isProject ? simpleMasterAgreement(agreement, allocation) : null;
  if (simple && simple.allocation) {
    const current = simple.allocation;
    const entries = [
      ...simple.owners.map((owner, index) => ({ name: owner.name, percent: owner.percent, kind: "owner", index })),
      { name: current.principal, percent: current.principal_percent, kind: "principal", index: 0 },
      ...current.participants.map((row, index) => ({ name: row.artist, percent: row.percent, kind: "participant", index })),
    ];
    const total = entries.reduce((sum, row) => sum + (row.percent || 0), 0);
    const change = (entry: typeof entries[number], name: string, value: number | null) => {
      const next = structuredClone(simple);
      const target = next.allocation!;
      if (entry.kind === "owner") next.owners[entry.index] = { name, percent: value };
      else if (entry.kind === "principal") { target.principal = name; target.principal_percent = value; }
      else target.participants[entry.index] = { ...target.participants[entry.index], artist: name, percent: value };
      onChange(next);
    };
    return <section className={styles.band}>
      <div className={styles.sectionHeading}><h2>Reparto del master</h2><span className={Math.abs(total - 100) < .0001 ? styles.counterOk : styles.counterPending}>Total {percent(total)}%</span></div>
      <div className={styles.segmented} aria-label="Tipo de contrato">
        <button type="button" aria-pressed="true" className={styles.selected} disabled={!canEdit}>Contrato simple</button>
        <button type="button" disabled={!canEdit} onClick={() => onChange({ ...poolAgreement(simple, current), contract_kind: "project" })}>Proyecto con socios</button>
      </div>
      <div className={styles.ownerRows}>{entries.map((entry, index) => <div className={styles.ownerRow} key={index}>
        <label>{entry.kind === "principal" ? "Artista principal" : "Titular / participante"}<input list={optionsId} disabled={!canEdit} value={entry.name} onChange={(event) => change(entry, event.target.value, entry.percent)} /></label>
        <label>% del ingreso total<input type="number" min="0" max="100" step="any" disabled={!canEdit} value={entry.percent ?? ""} onChange={(event) => change(entry, entry.name, numberOrNull(event.target.value))} /></label>
        {canEdit && entry.name.trim() && <button type="button" className={styles.iconButton} title={`Contrato de ${entry.name}`} onClick={() => onEditArtist(entry.name)}><FilePenLine size={16} /></button>}
        {canEdit && entry.kind !== "principal" && <button type="button" className={styles.iconButton} title={`Quitar ${entry.name || "participante"}`} onClick={() => {
          const next = structuredClone(simple);
          if (entry.kind === "owner") next.owners.splice(entry.index, 1);
          else {
            next.allocation!.catalog_participant_exclusions = participantExclusions(current, entry.name, "", artistOptions);
            next.allocation!.participants.splice(entry.index, 1);
          }
          onChange(next);
        }}><Trash2 size={16} /></button>}
      </div>)}</div>
      {total > 100.0001 && <p className={styles.counterPending} role="alert">El reparto supera el 100%.</p>}
      {canEdit && <button type="button" className={styles.addButton} disabled={current.participants.length >= 10} onClick={() => onChange({ ...simple, allocation: { ...current, participants: [...current.participants, { artist: "", percent: null, internal_contract_indyana_percent: null, rule: { treatment: "direct" } }] } })}><Plus size={16} />Agregar participante</button>}
      <datalist id={optionsId}>{[...new Set(["Indyana", "Mawz", ...artistOptions])].map((name) => <option value={name} key={name} />)}</datalist>
    </section>;
  }

  if (agreement.allocation_model !== "pools") return <section className={styles.band}>
    <div className={styles.sectionHeading}><h2>Reparto guardado</h2>
      {canEdit && <button type="button" className={styles.secondaryButton} onClick={() => onChange(poolAgreement(agreement, allocation))}><FilePenLine size={16} />Editar con bolsas</button>}
    </div>
    <div className={styles.legacyRows}>
      {rows.map((row, index) => <div key={index}><span>{row.artist || "Sin definir"}</span><strong>{row.percent == null ? "-" : `${percent(row.percent)}%`}</strong></div>)}
    </div>
  </section>;

  return <>
    <section className={styles.band}>
      <div className={styles.sectionHeading}><h2>Reparto inicial</h2></div>
      {isMaster && <div className={styles.segmented} aria-label="Tipo de contrato">
        {(["simple", "project"] as const).map((kind) => <button type="button" key={kind} disabled={!canEdit} aria-pressed={(agreement.contract_kind || "simple") === kind}
          className={(agreement.contract_kind || "simple") === kind ? styles.selected : ""} onClick={() => {
            if (kind === "simple" && rows.some((row) => row.rule?.treatment === "project_owners")) {
              if (!window.confirm("Las participaciones repartidas entre socios pasarán a cobro directo. ¿Continuar?")) return;
              update({ contract_kind: kind, allocation: { ...allocation,
                principal_rule: allocation.principal_rule?.treatment === "project_owners" ? { treatment: "direct" } : allocation.principal_rule,
                participants: allocation.participants.map((item) => item.rule?.treatment === "project_owners" ? { ...item, rule: { treatment: "direct" } } : item),
              } });
            } else update({ contract_kind: kind });
          }}>{kind === "simple" ? "Contrato simple" : "Proyecto con socios"}</button>)}
      </div>}
      <div className={styles.poolFields}>
        <label>{isMaster ? "Bolsa master %" : "Comercialización %"}<input aria-label="Bolsa master porcentaje" type="number" min="0" max="100" step="any" disabled={!canEdit} value={agreement.master_pool_percent ?? ""}
          onChange={(event) => update({ master_pool_percent: numberOrNull(event.target.value) })} /></label>
        <label>Bolsa participaciones %<input aria-label="Bolsa participaciones porcentaje" type="number" min="0" max="100" step="any" disabled={!canEdit} value={remaining ?? ""}
          onChange={(event) => update({ master_pool_percent: event.target.value === "" ? null : 100 - Number(event.target.value) })} /></label>
        {!isMaster && <label>Destinatario<input list={optionsId} disabled={!canEdit} value={agreement.company_name || "Indyana"} onChange={(event) => update({ company_name: event.target.value })} /></label>}
      </div>
    </section>

    {isMaster && <section className={styles.band}>
      <div className={styles.sectionHeading}><h2>{isProject ? "Titulares y socios" : "Titulares del master"}</h2><span className={Math.abs(ownershipTotal(agreement) - 100) < .0001 ? styles.counterOk : styles.counterPending}>Titularidad {percent(ownershipTotal(agreement))}%</span></div>
      <label className={styles.checkboxLine}><input type="checkbox" disabled={!canEdit} checked={agreement.owner_split_mode === "equal"} onChange={(event) => update({
        owner_split_mode: event.target.checked ? "equal" : "percent",
        owners: event.target.checked ? agreement.owners : agreement.owners.map((owner) => ({ ...owner, percent: 100 / agreement.owners.length })),
      })} /><span>Partes iguales</span></label>
      <div className={styles.ownerRows}>
        {agreement.owners.map((owner, index) => <div className={styles.ownerRow} key={index}>
          <label>Titular {index + 1}<input list={optionsId} disabled={!canEdit} value={owner.name} onChange={(event) => update({ owners: agreement.owners.map((item, position) => position === index ? { ...item, name: event.target.value } : item) })} /></label>
          <label>% de la bolsa master{agreement.owner_split_mode === "equal"
            ? <output>{percent(100 / agreement.owners.length)}%</output>
            : <input type="number" min="0" max="100" step="any" disabled={!canEdit} value={owner.percent ?? ""} onChange={(event) => update({ owners: agreement.owners.map((item, position) => position === index ? { ...item, percent: numberOrNull(event.target.value) } : item) })} />}</label>
          {canEdit && agreement.owners.length > 1 && <button type="button" className={styles.iconButton} title={`Quitar titular ${index + 1}`} aria-label={`Quitar titular ${index + 1}`} onClick={() => update({ owners: agreement.owners.filter((_, position) => position !== index) })}><Trash2 size={16} /></button>}
        </div>)}
      </div>
      {canEdit && <button type="button" className={styles.addButton} disabled={agreement.owners.length >= 12} onClick={() => update({ owners: [...agreement.owners, { name: "", percent: null }] })}><Plus size={16} />Agregar titular</button>}
    </section>}

    <section className={styles.band}>
      <div className={styles.sectionHeading}><h2>Participaciones</h2><span>{percent(participation)}% de {remaining == null ? "-" : `${percent(remaining)}%`}</span></div>
      <div className={styles.participantRows}>
        {rows.map((row, index) => {
          const rule = row.rule || { treatment: "direct" };
          const contract = artistContracts.find((item) => item.is_active && beneficiaryKey(item.artist_name) === beneficiaryKey(row.artist));
          const availableBeneficiaries = contract ? artistBeneficiaries(contract) : [];
          const contractApplied = contract && rule.contract_version === contract.version
            && beneficiaryKey(rule.contract_artist || "") === beneficiaryKey(contract.artist_name)
            && rule.beneficiaries?.length === availableBeneficiaries.length
            && rule.beneficiaries.every((item, position) =>
              beneficiaryKey(item.name) === beneficiaryKey(availableBeneficiaries[position].name)
              && item.percent === availableBeneficiaries[position].percent);
          return <div className={styles.participantRow} key={index}>
            <div className={styles.participantIdentity}>
              <label>{index === 0 ? "Artista principal" : `Participante ${index}`}<input list={optionsId} disabled={!canEdit} value={row.artist}
                onChange={(event) => updateRow(index, { artist: event.target.value, rule: rule.treatment === "artist_contract" ? { treatment: "artist_contract", retained_percent: null, retained_recipient: rule.retained_recipient || "Indyana" } : rule })} /></label>
              <label>% del ingreso<input type="number" min="0" max="100" step="any" disabled={!canEdit} value={row.percent ?? ""} onChange={(event) => updateRow(index, { percent: numberOrNull(event.target.value) })} /></label>
              {canEdit && index > 0 && <button type="button" className={styles.iconButton} title={`Quitar participante ${index}`} aria-label={`Quitar participante ${index}`} onClick={() => updateAllocation({
                catalog_participant_exclusions: participantExclusions(allocation, row.artist, "", artistOptions),
                participants: allocation.participants.filter((_, position) => position !== index - 1),
              })}><Trash2 size={16} /></button>}
            </div>
            <div className={styles.treatmentRow}>
              <label>Tratamiento<select disabled={!canEdit} value={rule.treatment} onChange={(event) => updateRow(index, { rule: {
                treatment: event.target.value as ParticipationRule["treatment"], retained_percent: null, retained_recipient: "Indyana",
              } })}>
                <option value="direct">Cobro directo</option><option value="artist_contract">Aplicar contrato del artista</option>
                {isMaster && isProject && <option value="project_owners">Repartir entre socios</option>}
              </select></label>
              {canEdit && row.artist.trim() && <button type="button" className={styles.iconButton} title={`Contrato de ${row.artist}`} aria-label={`Contrato de ${row.artist}`} onClick={() => onEditArtist(row.artist)}><FilePenLine size={16} /></button>}
            </div>
            {rule.treatment === "artist_contract" && <div className={styles.ruleFields}>
              {rule.beneficiaries != null ? <div className={styles.ruleReference}>{rule.beneficiaries.map((item, position) => <span key={position}>{item.name}: {percent(item.percent || 0)}%</span>)}</div> : <>
              <label>Retención del contrato %<input type="number" min="0" max="100" step="any" disabled={!canEdit} value={rule.retained_percent ?? ""} onChange={(event) => updateRow(index, { rule: { ...rule, retained_percent: numberOrNull(event.target.value), contract_artist: null, contract_version: null } })} /></label>
              <label>Retención para<input list={optionsId} disabled={!canEdit} value={rule.retained_recipient || ""} onChange={(event) => updateRow(index, { rule: { ...rule, retained_recipient: event.target.value } })} /></label>
              </>}
              {contract && !contractApplied && <div className={styles.ruleReference}><span>Contrato disponible · versión {contract.version}: {availableBeneficiaries.map((item) => `${item.name}: ${percent(item.percent || 0)}%`).join(" · ")}</span>
                {canEdit && <button type="button" className={styles.secondaryButton} onClick={() => updateRow(index, { rule: { treatment: "artist_contract", beneficiaries: structuredClone(artistBeneficiaries(contract)), contract_artist: contract.artist_name, contract_version: contract.version } })}>Usar contrato</button>}
              </div>}
              {rule.contract_artist && <small className={styles.fieldHint}>Contrato: {rule.contract_artist} · versión {rule.contract_version}</small>}
            </div>}
          </div>;
        })}
      </div>
      {canEdit && <div className={styles.actions}>
        <button type="button" className={styles.addButton} disabled={allocation.participants.length >= 10} onClick={() => updateAllocation({ participants: [...allocation.participants, { artist: "", percent: null, internal_contract_indyana_percent: null, rule: { treatment: "direct" } }] })}><Plus size={16} />Agregar participante</button>
        <button type="button" className={styles.secondaryButton} disabled={remaining === null} onClick={() => {
          if (rows.some((row) => row.percent !== null) && !window.confirm("¿Repartir la bolsa de participaciones en partes iguales?")) return;
          const value = (remaining || 0) / rows.length;
          updateAllocation({ principal_percent: value, participants: allocation.participants.map((item) => ({ ...item, percent: value })) });
        }}><Divide size={16} />Repartir por igual</button>
      </div>}
    </section>
    <datalist id={optionsId}>{[...new Set(["Indyana", "Mawz", ...artistOptions])].map((name) => <option value={name} key={name} />)}</datalist>
  </>;
}
