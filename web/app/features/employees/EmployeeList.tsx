"use client";

import { employeeCompensationLabels } from "./types";
import { formatEmployeeSalary } from "./model";
import type { EmployeeRecord } from "./types";

type Props = {
  records: EmployeeRecord[];
  filteredRecords: EmployeeRecord[];
  moduleCount: number;
  search: string;
  loading: boolean;
  onSearchChange: (value: string) => void;
  onRefresh: () => Promise<void>;
  onEdit: (item: EmployeeRecord) => void;
  onResetPassword: (item: EmployeeRecord) => Promise<void>;
  onDeactivate: (item: EmployeeRecord) => Promise<void>;
};

export function EmployeeList({ records, filteredRecords, moduleCount, search, loading, onSearchChange, onRefresh, onEdit, onResetPassword, onDeactivate }: Props) {
  return (
    <section className="panel">
      <div className="section-heading compact">
        <div><h1>Empleados</h1><p>La edicion granular de permisos queda preparada para la siguiente etapa.</p></div>
        <button type="button" onClick={() => void onRefresh()}>Actualizar</button>
      </div>
      <label htmlFor="employee_search">Buscar empleado</label>
      <input id="employee_search" value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Nombre, funcion, email, telefono" />
      <p className="field-help">Mostrando {filteredRecords.length} de {records.length} empleado(s). Modulos definidos: {moduleCount}.</p>
      <div className="artist-record-list">
        {records.length === 0 && <p className="field-help">Todavia no hay empleados cargados.</p>}
        {records.length > 0 && filteredRecords.length === 0 && <p className="field-help">No hay empleados que coincidan con la busqueda.</p>}
        {filteredRecords.map((item) => {
          const enabledPermissions = item.permissions.filter((permission) => permission.can_access).length;
          const primaryUser = item.users?.[0];
          return (
            <div className={`artist-record-item ${item.active ? "" : "inactive"}`} key={item.id}>
              <div><strong>{item.display_name}</strong><span>{item.active ? "Empleado activo" : "Empleado inactivo"}</span></div>
              <div className="artist-record-meta">
                <span>{item.functions.length ? item.functions.join(" / ") : "Sin funcion"}</span><span>{item.phone || "Sin telefono"}</span><span>{item.email || "Sin email"}</span><span>{item.active ? "Activo" : "Inactivo"}</span>
              </div>
              <div className="artist-record-meta">
                <span>{employeeCompensationLabels[item.compensation_type] || "Sin compensacion fija"}</span>
                {item.compensation_type !== "none" && item.compensation_type !== "booking_commission_only" && <span>{formatEmployeeSalary(item.salary_currency, item.salary_amount || 0)} mensual</span>}
                {item.salary_notes && <span>{item.salary_notes}</span>}
              </div>
              <div className="artist-record-meta">
                <span>{primaryUser ? `Usuario: ${primaryUser.username}` : "Sin usuario"}</span><span>{primaryUser ? `Rol: ${primaryUser.global_role}` : "Sin rol"}</span><span>{primaryUser?.active ? "Login activo" : primaryUser ? "Login inactivo" : "Login pendiente"}</span><span>{primaryUser?.has_password ? "Con contrasena" : "Sin contrasena"}</span>{primaryUser?.must_change_password && <span>Cambio requerido</span>}<span>{primaryUser?.auth_source || "Sin origen auth"}</span>
              </div>
              {item.address && <p>{item.address}</p>}{item.notes && <p>{item.notes}</p>}
              <div className="booking-status"><span>{enabledPermissions} permiso(s) con acceso</span>{item.display_name.toLowerCase() === "ruben elkowich" && <span>Super-admin</span>}</div>
              <div className="booking-actions">
                <button type="button" onClick={() => onEdit(item)}>Editar</button>
                <button type="button" onClick={() => void onResetPassword(item)} disabled={loading}>Establecer contrasena default</button>
                {item.active && item.display_name.toLowerCase() !== "ruben elkowich" && <button type="button" className="secondary-danger" onClick={() => void onDeactivate(item)}>Desactivar</button>}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
