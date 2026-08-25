"use client";

import { ShieldCheck, UserPlus, Users } from "lucide-react";
import { EmployeeForm } from "./EmployeeForm";
import { EmployeeList } from "./EmployeeList";
import type { EmployeeMessage } from "./types";
import { useEmployees } from "./useEmployees";

type Props = {
  onMessage: (message: EmployeeMessage | null) => void;
};

export function EmployeesModule({ onMessage }: Props) {
  const employees = useEmployees(onMessage);
  const activeEmployees = employees.records.filter((employee) => employee.active).length;
  const webUsers = employees.records.filter((employee) => employee.users?.length).length;
  const enabledPermissions = employees.records.reduce(
    (total, employee) => total + employee.permissions.filter((permission) => permission.can_access).length,
    0,
  );

  function openEmployee(employee: Parameters<typeof employees.editRecord>[0]) {
    employees.editRecord(employee);
    if (typeof window !== "undefined" && window.innerWidth <= 860) {
      window.setTimeout(() => document.querySelector(".employees-editor-pane")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
    }
  }

  return (
    <div className="employees-workspace">
      <header className="employees-hero">
        <div className="employees-hero-copy">
          <span className="employees-eyebrow"><Users size={15} /> VPO Corp</span>
          <h1>Equipo y accesos</h1>
          <p>Personas, funciones, compensaciones y permisos operativos.</p>
        </div>
        <div className="employees-hero-actions">
          <div className="employees-metrics" aria-label="Resumen de empleados">
            <div><strong>{activeEmployees}</strong><span>activos</span></div>
            <div><strong>{webUsers}</strong><span>usuarios</span></div>
            <div><strong>{enabledPermissions}</strong><span>accesos</span></div>
          </div>
          <button className="employees-primary-action" type="button" onClick={employees.resetForm}>
            <UserPlus size={17} /> Nuevo empleado
          </button>
        </div>
      </header>

      <div className="employees-layout">
        <EmployeeList
          records={employees.records}
          filteredRecords={employees.filteredRecords}
          moduleCount={employees.modules.length}
          editingId={employees.editingId}
          search={employees.search}
          loading={employees.loading}
          onSearchChange={employees.setSearch}
          onRefresh={employees.loadData}
          onEdit={openEmployee}
          onResetPassword={employees.resetPassword}
          onDeactivate={employees.deactivateRecord}
        />
        <div className="employees-editor-pane">
          <div className="employees-editor-accent"><ShieldCheck size={18} /><span>Configuracion operativa</span></div>
          <EmployeeForm
            form={employees.form}
            editingId={employees.editingId}
            loading={employees.loading}
            functionOptions={employees.functionOptions}
            modules={employees.modules}
            artists={employees.artists}
            onFieldChange={employees.updateField}
            onFunctionToggle={employees.toggleFunction}
            onPermissionLevelChange={employees.setPermissionLevel}
            onPermissionArtistModeChange={employees.setPermissionArtistMode}
            onPermissionArtistToggle={employees.togglePermissionArtist}
            onCancel={employees.resetForm}
            onSubmit={employees.submit}
          />
        </div>
      </div>
    </div>
  );
}
