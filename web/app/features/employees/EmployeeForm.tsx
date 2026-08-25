"use client";

import type { FormEvent } from "react";
import { PermissionsEditor } from "./PermissionsEditor";
import { DEFAULT_EMPLOYEE_FUNCTIONS, type PermissionLevel } from "./model";
import type { EmployeeFormState, EmployeeModuleDefinition } from "./types";

type Props = {
  form: EmployeeFormState;
  editingId: number | null;
  loading: boolean;
  functionOptions: string[];
  modules: EmployeeModuleDefinition[];
  artists: string[];
  onFieldChange: <K extends keyof EmployeeFormState>(key: K, value: EmployeeFormState[K]) => void;
  onFunctionToggle: (functionName: string) => void;
  onPermissionLevelChange: (moduleKey: string, level: PermissionLevel) => void;
  onPermissionArtistModeChange: (moduleKey: string, mode: "all" | "selected") => void;
  onPermissionArtistToggle: (moduleKey: string, artist: string) => void;
  onCancel: () => void;
  onSubmit: () => Promise<void>;
};

export function EmployeeForm({
  form,
  editingId,
  loading,
  functionOptions,
  modules,
  artists,
  onFieldChange,
  onFunctionToggle,
  onPermissionLevelChange,
  onPermissionArtistModeChange,
  onPermissionArtistToggle,
  onCancel,
  onSubmit,
}: Props) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void onSubmit();
  }

  return (
    <form className="panel" onSubmit={submit}>
      <div className="section-heading compact">
        <div>
          <h1>{editingId ? `Editando empleado #${editingId}` : "ABM de empleados"}</h1>
          <p>Equipo VPO, funciones y base para permisos por modulo.</p>
        </div>
        {editingId && <button type="button" onClick={onCancel}>Cancelar</button>}
      </div>

      <label htmlFor="employee_display_name">Nombre</label>
      <input id="employee_display_name" value={form.displayName} onChange={(event) => onFieldChange("displayName", event.target.value)} required />

      <div className="row">
        <div>
          <label htmlFor="employee_cuit">CUIT / CUIL</label>
          <input id="employee_cuit" value={form.cuit} onChange={(event) => onFieldChange("cuit", event.target.value)} />
        </div>
        <div>
          <label htmlFor="employee_phone">Telefono</label>
          <input id="employee_phone" value={form.phone} onChange={(event) => onFieldChange("phone", event.target.value)} />
        </div>
      </div>

      <label htmlFor="employee_email">Email</label>
      <input id="employee_email" type="email" value={form.email} onChange={(event) => onFieldChange("email", event.target.value)} />

      <label htmlFor="employee_address">Domicilio</label>
      <input id="employee_address" value={form.address} onChange={(event) => onFieldChange("address", event.target.value)} />

      <div className="section-heading compact"><div><h2>Funciones</h2><p>Un empleado puede tener mas de una funcion.</p></div></div>
      <div className="checkbox-grid">
        {(functionOptions.length ? functionOptions : DEFAULT_EMPLOYEE_FUNCTIONS).map((functionName) => (
          <label className="checkbox-field" key={functionName}>
            <input type="checkbox" checked={form.functions.includes(functionName)} onChange={() => onFunctionToggle(functionName)} />
            {functionName}
          </label>
        ))}
      </div>

      <div className="section-heading compact"><div><h2>Compensacion</h2><p>Esto guarda la condicion pactada. El pago real se carga en Movimientos Financieros.</p></div></div>
      <div className="row three">
        <div>
          <label htmlFor="employee_compensation_type">Modelo</label>
          <select id="employee_compensation_type" value={form.compensationType} onChange={(event) => onFieldChange("compensationType", event.target.value as EmployeeFormState["compensationType"])}>
            <option value="none">Sin compensacion fija</option>
            <option value="salary">Salario mensual</option>
            <option value="salary_plus_booking_commission">Salario + comision booking</option>
            <option value="booking_commission_only">Solo comision booking</option>
          </select>
        </div>
        {form.compensationType !== "none" && form.compensationType !== "booking_commission_only" && (
          <>
            <div>
              <label htmlFor="employee_salary_amount">Salario pactado</label>
              <input id="employee_salary_amount" inputMode="decimal" value={form.salaryAmount} onChange={(event) => onFieldChange("salaryAmount", event.target.value)} placeholder="Importe mensual" />
            </div>
            <div>
              <label htmlFor="employee_salary_currency">Moneda</label>
              <select id="employee_salary_currency" value={form.salaryCurrency} onChange={(event) => onFieldChange("salaryCurrency", event.target.value as "ARS" | "USD")}>
                <option value="ARS">ARS</option><option value="USD">USD</option>
              </select>
            </div>
          </>
        )}
      </div>
      {form.compensationType !== "none" && (
        <><label htmlFor="employee_salary_notes">Notas de compensacion</label><textarea id="employee_salary_notes" value={form.salaryNotes} onChange={(event) => onFieldChange("salaryNotes", event.target.value)} placeholder="Ej: parte fija, financiacion externa, condicion pendiente" /></>
      )}
      <p className="field-help">Las comisiones variables de booking se configuran en la tarjeta Comisiones. Este bloque no crea pagos automaticos.</p>

      <div className="section-heading compact"><div><h2>Usuario web</h2><p>Este usuario ya es la base operativa de login local/cloud.</p></div></div>
      <div className="row three">
        <div><label htmlFor="employee_username">Usuario</label><input id="employee_username" value={form.username} onChange={(event) => onFieldChange("username", event.target.value)} placeholder="salomef" /></div>
        <div>
          <label htmlFor="employee_user_role">Rol global</label>
          <select id="employee_user_role" value={form.userRole} onChange={(event) => onFieldChange("userRole", event.target.value as EmployeeFormState["userRole"])}>
            <option value="viewer">Viewer</option><option value="editor">Editor</option><option value="admin">Admin</option>
          </select>
        </div>
        <label className="checkbox-field"><input type="checkbox" checked={form.userActive} onChange={(event) => onFieldChange("userActive", event.target.checked)} />Usuario activo</label>
      </div>
      <div className="row">
        <div><label htmlFor="employee_new_password">Establecer contrasena</label><input id="employee_new_password" type="password" value={form.newPassword} onChange={(event) => onFieldChange("newPassword", event.target.value)} placeholder="Dejar vacio para no cambiar" autoComplete="new-password" /></div>
        <label className="checkbox-field"><input type="checkbox" checked={form.mustChangePassword} onChange={(event) => onFieldChange("mustChangePassword", event.target.checked)} />Pedir cambio al ingresar</label>
      </div>
      <p className="field-help">Default inicial: Indyana2026!. Si estableces esa clave, deja marcado pedir cambio.</p>

      <div className="section-heading compact"><div><h2>Permisos por modulo</h2><p>Inicio se habilita automaticamente si tiene acceso a algun modulo. Cada permiso se valida en pantalla y servidor.</p></div></div>
      <PermissionsEditor
        permissions={form.permissions}
        modules={modules}
        artists={artists}
        onLevelChange={onPermissionLevelChange}
        onArtistModeChange={onPermissionArtistModeChange}
        onArtistToggle={onPermissionArtistToggle}
      />

      <label htmlFor="employee_notes">Notas</label>
      <textarea id="employee_notes" value={form.notes} onChange={(event) => onFieldChange("notes", event.target.value)} />
      <label className="checkbox-field"><input type="checkbox" checked={form.active} onChange={(event) => onFieldChange("active", event.target.checked)} />Activo</label>
      <button type="submit" disabled={loading}>{loading ? "Guardando..." : editingId ? "Guardar cambios" : "Crear empleado"}</button>
    </form>
  );
}
