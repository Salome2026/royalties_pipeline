"use client";

import { KeyRound, Pencil, RefreshCw, Search, UserRound, UserX } from "lucide-react";
import { employeeCompensationLabels } from "./types";
import { formatEmployeeSalary } from "./model";
import type { EmployeeRecord } from "./types";

type Props = {
  records: EmployeeRecord[];
  filteredRecords: EmployeeRecord[];
  moduleCount: number;
  editingId: number | null;
  search: string;
  loading: boolean;
  onSearchChange: (value: string) => void;
  onRefresh: () => Promise<void>;
  onEdit: (item: EmployeeRecord) => void;
  onResetPassword: (item: EmployeeRecord) => Promise<void>;
  onDeactivate: (item: EmployeeRecord) => Promise<void>;
};

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "VP";
}

export function EmployeeList({ records, filteredRecords, moduleCount, editingId, search, loading, onSearchChange, onRefresh, onEdit, onResetPassword, onDeactivate }: Props) {
  return (
    <aside className="employees-directory">
      <div className="employees-directory-heading">
        <div><span>Directorio</span><strong>{records.length} personas</strong></div>
        <button className="employees-icon-button" type="button" onClick={() => void onRefresh()} title="Actualizar empleados" aria-label="Actualizar empleados">
          <RefreshCw size={16} className={loading ? "is-spinning" : ""} />
        </button>
      </div>
      <div className="employees-search">
        <Search size={16} aria-hidden="true" />
        <input id="employee_search" aria-label="Buscar empleado" value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Buscar por nombre o funcion" />
      </div>
      <div className="employees-directory-meta"><span>{filteredRecords.length} visibles</span><span>{moduleCount} modulos</span></div>
      <div className="employees-record-list">
        {records.length === 0 && <div className="employees-empty"><UserRound size={20} /><span>Todavia no hay empleados cargados.</span></div>}
        {records.length > 0 && filteredRecords.length === 0 && <div className="employees-empty"><Search size={20} /><span>No hay coincidencias.</span></div>}
        {filteredRecords.map((item) => {
          const enabledPermissions = item.permissions.filter((permission) => permission.can_access).length;
          const primaryUser = item.users?.[0];
          return (
            <article className={`employees-record ${editingId === item.id ? "is-selected" : ""} ${item.active ? "" : "is-inactive"}`} key={item.id}>
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
              <div className="employees-record-details">
                <span>{employeeCompensationLabels[item.compensation_type] || "Sin compensacion fija"}</span>
                {item.compensation_type !== "none" && item.compensation_type !== "booking_commission_only" && <strong>{formatEmployeeSalary(item.salary_currency, item.salary_amount || 0)} mensual</strong>}
              </div>
              <div className="employees-record-actions">
                <button type="button" onClick={() => onEdit(item)} title="Editar empleado"><Pencil size={14} /> Editar</button>
                <button type="button" onClick={() => void onResetPassword(item)} disabled={loading} title="Establecer contrasena default"><KeyRound size={14} /> Clave</button>
                {item.active && item.display_name.toLowerCase() !== "ruben elkowich" && <button type="button" className="is-danger" onClick={() => void onDeactivate(item)} title="Desactivar empleado"><UserX size={14} /> Desactivar</button>}
              </div>
            </article>
          );
        })}
      </div>
    </aside>
  );
}
