"use client";

import { Pencil, ShieldCheck, UserRoundCheck, UserRoundX } from "lucide-react";
import { formatEmployeeSalary } from "./model";
import { employeeCompensationLabels, type EmployeeRecord } from "./types";

type Props = {
  records: EmployeeRecord[];
  onEdit: (item: EmployeeRecord) => void;
};

export function EmployeeOverview({ records, onEdit }: Props) {
  return (
    <section className="employees-overview" aria-labelledby="employees-overview-title">
      <div className="employees-section-heading">
        <div><span>Informe general</span><h2 id="employees-overview-title">Equipo completo</h2></div>
        <small>{records.length} personas</small>
      </div>
      <div className="employees-table-wrap">
        <table className="employees-table">
          <thead><tr><th>Empleado</th><th>Función</th><th>Usuario</th><th>Compensación</th><th>Accesos</th><th>Estado</th><th aria-label="Acciones" /></tr></thead>
          <tbody>
            {records.map((item) => {
              const user = item.users?.[0];
              const enabledPermissions = item.permissions.filter((permission) => permission.can_access).length;
              return (
                <tr key={item.id}>
                  <td><strong>{item.display_name}</strong><small>{item.email || item.phone || "Sin contacto informado"}</small></td>
                  <td>{item.functions.length ? item.functions.join(", ") : "Sin función"}</td>
                  <td>{user ? `@${user.username}` : "Sin usuario"}</td>
                  <td><span>{employeeCompensationLabels[item.compensation_type]}</span>{item.compensation_type !== "none" && item.compensation_type !== "booking_commission_only" && <small>{formatEmployeeSalary(item.salary_currency, item.salary_amount || 0)} mensual</small>}</td>
                  <td><span className="employees-access-count"><ShieldCheck size={14} />{enabledPermissions}</span></td>
                  <td><span className={`employees-status ${item.active ? "is-active" : ""}`}>{item.active ? <UserRoundCheck size={14} /> : <UserRoundX size={14} />}{item.active ? "Activo" : "Inactivo"}</span></td>
                  <td><button type="button" className="employees-row-action" onClick={() => onEdit(item)} aria-label={`Editar ${item.display_name}`} title="Editar empleado"><Pencil size={15} /></button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
