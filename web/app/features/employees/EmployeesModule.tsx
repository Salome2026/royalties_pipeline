"use client";

import { useState } from "react";
import { KeyRound, Search, UserPlus, Users, UserX } from "lucide-react";
import { EmployeeForm } from "./EmployeeForm";
import { EmployeeList } from "./EmployeeList";
import { EmployeeOverview } from "./EmployeeOverview";
import type { EmployeeRecord } from "./types";
import type { EmployeeMessage } from "./types";
import { useEmployees } from "./useEmployees";

type Props = {
  onMessage: (message: EmployeeMessage | null) => void;
};

type EmployeeMode = "directory" | "overview" | "new" | "edit";

export function EmployeesModule({ onMessage }: Props) {
  const employees = useEmployees(onMessage);
  const [mode, setMode] = useState<EmployeeMode>("directory");
  const activeEmployees = employees.records.filter((employee) => employee.active).length;
  const webUsers = employees.records.filter((employee) => employee.users?.length).length;
  const enabledPermissions = employees.records.reduce(
    (total, employee) => total + employee.permissions.filter((permission) => permission.can_access).length,
    0,
  );

  function openEmployee(employee: EmployeeRecord) {
    employees.editRecord(employee);
    setMode("edit");
  }

  function openNewEmployee() {
    employees.resetForm();
    setMode("new");
  }

  function closeEditor() {
    employees.resetForm();
    setMode("directory");
  }

  return (
    <div className="employees-workspace">
        <section className="employees-command-bar">
          <div className="employees-command-copy"><span><Users size={15} /> Equipo VPO</span><h1>Personas, accesos y compensaciones</h1><p>Entrá únicamente al módulo que necesitás.</p></div>
          <div className="employees-metrics" aria-label="Resumen de empleados">
            <div><strong>{activeEmployees}</strong><span>activos</span></div>
            <div><strong>{webUsers}</strong><span>usuarios</span></div>
            <div><strong>{enabledPermissions}</strong><span>accesos</span></div>
          </div>
        </section>

        <nav className="employees-mode-nav" aria-label="Secciones de empleados">
          <button type="button" className={mode === "directory" || mode === "edit" ? "is-active" : ""} onClick={() => { employees.setSearch(""); closeEditor(); }}><Search size={16} /><span>Directorio</span><small>Buscar una persona</small></button>
          <button type="button" className={mode === "overview" ? "is-active" : ""} onClick={() => { employees.resetForm(); setMode("overview"); }}><Users size={16} /><span>Equipo completo</span><small>Informe general</small></button>
          <button type="button" className={mode === "new" ? "is-active" : ""} onClick={openNewEmployee}><UserPlus size={16} /><span>Cargar nuevo</span><small>Crear una ficha</small></button>
        </nav>

        {mode === "directory" && <EmployeeList filteredRecords={employees.filteredRecords} search={employees.search} loading={employees.loading} onSearchChange={employees.setSearch} onRefresh={employees.loadData} onEdit={openEmployee} />}
        {mode === "overview" && <EmployeeOverview records={employees.records} onEdit={openEmployee} />}
        {(mode === "new" || mode === "edit") && (
          <section className="employees-editor-pane">
            {mode === "edit" && employees.editingId && (
              <div className="employees-record-tools">
                <span>Acciones de la ficha</span>
                <button type="button" onClick={() => void employees.resetPassword(employees.records.find((item) => item.id === employees.editingId)!)} disabled={employees.loading}><KeyRound size={15} />Restablecer clave</button>
                {employees.form.active && employees.form.displayName.toLowerCase() !== "ruben elkowich" && <button type="button" className="is-danger" onClick={() => void employees.deactivateRecord(employees.records.find((item) => item.id === employees.editingId)!)} disabled={employees.loading}><UserX size={15} />Desactivar</button>}
              </div>
            )}
            <EmployeeForm form={employees.form} editingId={employees.editingId} loading={employees.loading} functionOptions={employees.functionOptions} modules={employees.modules} artists={employees.artists} onFieldChange={employees.updateField} onFunctionToggle={employees.toggleFunction} onPermissionLevelChange={employees.setPermissionLevel} onPermissionArtistModeChange={employees.setPermissionArtistMode} onPermissionArtistToggle={employees.togglePermissionArtist} onCancel={closeEditor} onSubmit={async () => { if (await employees.submit()) setMode("directory"); }} />
          </section>
        )}
    </div>
  );
}
