"use client";

import { useEffect, useState, type FormEvent } from "react";
import { BadgeDollarSign, Contact, KeyRound, Save, ShieldCheck, UserRound, X } from "lucide-react";
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
  const [section, setSection] = useState<"profile" | "compensation" | "access" | "permissions">("profile");

  useEffect(() => {
    setSection("profile");
  }, [editingId]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void onSubmit();
  }

  return (
    <form className="employee-editor" onSubmit={submit}>
      <header className="employee-editor-header">
        <div className="employee-editor-title">
          <span className="employee-editor-icon"><UserRound size={19} /></span>
          <div>
            <small>{editingId ? `Empleado #${editingId}` : "Nueva ficha"}</small>
            <h2>{editingId ? form.displayName || "Editar empleado" : "Nuevo empleado"}</h2>
          </div>
        </div>
        {editingId && <button className="employees-icon-button" type="button" onClick={onCancel} title="Cancelar edicion" aria-label="Cancelar edicion"><X size={17} /></button>}
      </header>

      <nav className="employee-editor-nav" aria-label="Secciones de la ficha">
        <button type="button" aria-label="Ficha" title="Ficha" className={section === "profile" ? "is-active" : ""} onClick={() => setSection("profile")}><Contact size={16} /><span>Ficha</span></button>
        <button type="button" aria-label="Función y salario" title="Función y salario" className={section === "compensation" ? "is-active" : ""} onClick={() => setSection("compensation")}><BadgeDollarSign size={16} /><span>Función y salario</span></button>
        <button type="button" aria-label="Usuario" title="Usuario" className={section === "access" ? "is-active" : ""} onClick={() => setSection("access")}><KeyRound size={16} /><span>Usuario</span></button>
        <button type="button" aria-label="Permisos" title="Permisos" className={section === "permissions" ? "is-active" : ""} onClick={() => setSection("permissions")}><ShieldCheck size={16} /><span>Permisos</span></button>
      </nav>

      <div className="employee-editor-content">
        {section === "profile" && <section className="employee-form-section employee-form-section-final">
          <div className="employee-form-section-title"><Contact size={17} /><div><h3>Datos personales</h3><span>Identificacion y contacto</span></div></div>
          <div className="employee-form-grid employee-form-grid-two">
            <div className="employee-field employee-field-wide">
              <label htmlFor="employee_display_name">Nombre</label>
              <input id="employee_display_name" value={form.displayName} onChange={(event) => onFieldChange("displayName", event.target.value)} required />
            </div>
            <div className="employee-field">
              <label htmlFor="employee_cuit">CUIT / CUIL</label>
              <input id="employee_cuit" value={form.cuit} onChange={(event) => onFieldChange("cuit", event.target.value)} />
            </div>
            <div className="employee-field">
              <label htmlFor="employee_phone">Telefono</label>
              <input id="employee_phone" value={form.phone} onChange={(event) => onFieldChange("phone", event.target.value)} />
            </div>
            <div className="employee-field">
              <label htmlFor="employee_email">Email</label>
              <input id="employee_email" type="email" value={form.email} onChange={(event) => onFieldChange("email", event.target.value)} />
            </div>
            <div className="employee-field">
              <label htmlFor="employee_address">Domicilio</label>
              <input id="employee_address" value={form.address} onChange={(event) => onFieldChange("address", event.target.value)} />
            </div>
            <div className="employee-field employee-field-wide">
              <label htmlFor="employee_notes">Notas internas</label>
              <textarea id="employee_notes" value={form.notes} onChange={(event) => onFieldChange("notes", event.target.value)} />
            </div>
            <label className="employee-toggle-field"><input type="checkbox" checked={form.active} onChange={(event) => onFieldChange("active", event.target.checked)} /><span>Empleado activo</span></label>
          </div>
        </section>}

        {section === "compensation" && <section className="employee-form-section employee-form-section-final">
          <div className="employee-form-section-title"><BadgeDollarSign size={17} /><div><h3>Funcion y compensacion</h3><span>Condicion pactada con VPO</span></div></div>
          <div className="employee-function-grid">
            {(functionOptions.length ? functionOptions : DEFAULT_EMPLOYEE_FUNCTIONS).map((functionName) => (
              <label className="employee-choice" key={functionName}>
                <input type="checkbox" checked={form.functions.includes(functionName)} onChange={() => onFunctionToggle(functionName)} />
                <span>{functionName}</span>
              </label>
            ))}
          </div>
          <div className="employee-form-grid employee-form-grid-three">
            <div className="employee-field">
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
                <div className="employee-field">
                  <label htmlFor="employee_salary_amount">Salario pactado</label>
                  <input id="employee_salary_amount" inputMode="decimal" value={form.salaryAmount} onChange={(event) => onFieldChange("salaryAmount", event.target.value)} placeholder="Importe mensual" />
                </div>
                <div className="employee-field">
                  <label htmlFor="employee_salary_currency">Moneda</label>
                  <select id="employee_salary_currency" value={form.salaryCurrency} onChange={(event) => onFieldChange("salaryCurrency", event.target.value as "ARS" | "USD")}>
                    <option value="ARS">ARS</option><option value="USD">USD</option>
                  </select>
                </div>
              </>
            )}
          </div>
          {form.compensationType !== "none" && (
            <div className="employee-field employee-field-spaced">
              <label htmlFor="employee_salary_notes">Notas de compensacion</label>
              <textarea id="employee_salary_notes" value={form.salaryNotes} onChange={(event) => onFieldChange("salaryNotes", event.target.value)} placeholder="Condiciones particulares" />
            </div>
          )}
          <p className="employee-inline-note">Los pagos reales se registran en Movimientos Financieros.</p>
        </section>}

        {section === "access" && <section className="employee-form-section employee-form-section-final">
          <div className="employee-form-section-title"><KeyRound size={17} /><div><h3>Acceso al sistema</h3><span>Usuario y seguridad</span></div></div>
          <div className="employee-form-grid employee-form-grid-three">
            <div className="employee-field">
              <label htmlFor="employee_username">Usuario</label>
              <input id="employee_username" value={form.username} onChange={(event) => onFieldChange("username", event.target.value)} placeholder="salomef" />
            </div>
            <div className="employee-field">
              <label htmlFor="employee_user_role">Rol global</label>
              <select id="employee_user_role" value={form.userRole} onChange={(event) => onFieldChange("userRole", event.target.value as EmployeeFormState["userRole"])}>
                <option value="viewer">Viewer</option><option value="editor">Editor</option><option value="admin">Admin</option>
              </select>
            </div>
            <label className="employee-toggle-field"><input type="checkbox" checked={form.userActive} onChange={(event) => onFieldChange("userActive", event.target.checked)} /><span>Usuario activo</span></label>
            <div className="employee-field">
              <label htmlFor="employee_new_password">Establecer contrasena</label>
              <input id="employee_new_password" type="password" value={form.newPassword} onChange={(event) => onFieldChange("newPassword", event.target.value)} placeholder="Sin cambios" autoComplete="new-password" />
            </div>
            <label className="employee-toggle-field"><input type="checkbox" checked={form.mustChangePassword} onChange={(event) => onFieldChange("mustChangePassword", event.target.checked)} /><span>Pedir cambio al ingresar</span></label>
          </div>
        </section>}

        {section === "permissions" && <section className="employee-form-section employee-permissions-section employee-form-section-final">
          <div className="employee-form-section-title"><ShieldCheck size={17} /><div><h3>Permisos por modulo</h3><span>Acceso y alcance por artista</span></div></div>
          <PermissionsEditor
            permissions={form.permissions}
            modules={modules}
            artists={artists}
            onLevelChange={onPermissionLevelChange}
            onArtistModeChange={onPermissionArtistModeChange}
            onArtistToggle={onPermissionArtistToggle}
          />
        </section>}
      </div>

      <footer className="employee-editor-footer">
        <span>{editingId ? "Los cambios se aplican al guardar." : "La ficha se crea con los permisos seleccionados."}</span>
        <button className="employee-save-button" type="submit" disabled={loading}><Save size={17} />{loading ? "Guardando..." : editingId ? "Guardar cambios" : "Crear empleado"}</button>
      </footer>
    </form>
  );
}
