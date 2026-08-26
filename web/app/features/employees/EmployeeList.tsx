"use client";

import { Pencil, RefreshCw, Search, UserRound } from "lucide-react";
import type { EmployeeRecord } from "./types";

type Props = {
  filteredRecords: EmployeeRecord[];
  search: string;
  loading: boolean;
  onSearchChange: (value: string) => void;
  onRefresh: () => Promise<void>;
  onEdit: (item: EmployeeRecord) => void;
};

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "VP";
}

export function EmployeeList({ filteredRecords, search, loading, onSearchChange, onRefresh, onEdit }: Props) {
  const hasQuery = search.trim().length > 0;
  return (
    <section className="employees-directory">
      <div className="employees-directory-heading">
        <div><span>Directorio</span><strong>Buscar una persona</strong></div>
        <button className="employees-icon-button" type="button" onClick={() => void onRefresh()} title="Actualizar empleados" aria-label="Actualizar empleados">
          <RefreshCw size={16} className={loading ? "is-spinning" : ""} />
        </button>
      </div>
      <div className="employees-search employees-search-main">
        <Search size={16} aria-hidden="true" />
        <input id="employee_search" aria-label="Buscar empleado" value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Buscar por nombre o funcion" />
      </div>
      <div className="employees-directory-meta"><span>{hasQuery ? `${filteredRecords.length} coincidencias` : "Nombre, función o usuario"}</span><span>Elegí para abrir la ficha</span></div>
      <div className="employees-record-list">
        {!hasQuery && <div className="employees-empty employees-empty-search"><Search size={24} /><strong>El directorio empieza con una búsqueda</strong><span>No mostramos información del equipo hasta que escribas a quién necesitás.</span></div>}
        {hasQuery && filteredRecords.length === 0 && <div className="employees-empty"><UserRound size={20} /><span>No hay coincidencias.</span></div>}
        {hasQuery && filteredRecords.map((item) => {
          const enabledPermissions = item.permissions.filter((permission) => permission.can_access).length;
          const primaryUser = item.users?.[0];
          return (
            <article className={`employees-record ${item.active ? "" : "is-inactive"}`} key={item.id}>
              <button className="employees-record-main" type="button" onClick={() => onEdit(item)}>
                <span className="employees-avatar">{initials(item.display_name)}</span>
                <span className="employees-record-copy">
                  <strong>{item.display_name}</strong>
                  <small>{item.functions.length ? item.functions.join(" · ") : "Funcion pendiente"}</small>
                  <span className="employees-record-badges">
                    <em className={item.active ? "is-active" : ""}>{item.active ? "Activo" : "Inactivo"}</em>
                    <em>{enabledPermissions} accesos</em>
                    {primaryUser && <em>@{primaryUser.username}</em>}
                  </span>
                </span>
                <Pencil size={15} aria-hidden="true" />
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}
