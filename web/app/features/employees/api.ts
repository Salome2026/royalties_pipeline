import type { EmployeeData, EmployeeFormState, EmployeeRecord } from "./types";
import { normalizeEmployeePermissionForSave, parseEmployeeAmount } from "./model";

async function apiError(response: Response, fallback: string) {
  const data = await response.json().catch(() => ({ error: fallback }));
  return String(data.error || fallback);
}

export async function fetchEmployees(): Promise<EmployeeData> {
  const response = await fetch("/api/employees", { cache: "no-store" });
  if (!response.ok) throw new Error(await apiError(response, "No se pudieron cargar los empleados."));
  return response.json();
}

export async function fetchEmployeeArtists(): Promise<string[]> {
  const response = await fetch("/api/booking/artists", { cache: "no-store" });
  if (!response.ok) return [];
  const data = await response.json();
  return data.items || [];
}

export async function saveEmployee(
  form: EmployeeFormState,
  employeeId: number | null,
): Promise<EmployeeRecord> {
  const response = await fetch(employeeId ? `/api/employees?id=${employeeId}` : "/api/employees", {
    method: employeeId ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      display_name: form.displayName,
      legal_name: form.displayName || null,
      cuit: form.cuit || null,
      phone: form.phone || null,
      email: form.email || null,
      address: form.address || null,
      functions: form.functions,
      compensation_type: form.compensationType,
      salary_amount: parseEmployeeAmount(form.salaryAmount),
      salary_currency: form.salaryCurrency,
      salary_frequency: form.salaryFrequency,
      salary_notes: form.salaryNotes || null,
      username: form.username || null,
      password: form.newPassword || null,
      must_change_password: form.newPassword ? form.mustChangePassword : null,
      user_role: form.userRole,
      user_active: form.userActive,
      permissions: form.permissions
        .filter((permission) => permission.module_key !== "home")
        .map(normalizeEmployeePermissionForSave),
      notes: form.notes || null,
      active: form.active,
    }),
  });
  if (!response.ok) throw new Error(await apiError(response, "No se pudo guardar el empleado."));
  const data = await response.json();
  return data.item as EmployeeRecord;
}

export async function deactivateEmployee(employeeId: number): Promise<EmployeeRecord> {
  const response = await fetch(`/api/employees?id=${employeeId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await apiError(response, "No se pudo desactivar el empleado."));
  const data = await response.json();
  return data.item as EmployeeRecord;
}

export async function setDefaultEmployeePassword(employeeId: number): Promise<EmployeeRecord> {
  const response = await fetch(`/api/employees?id=${employeeId}&action=password`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ use_default: true, must_change_password: true }),
  });
  if (!response.ok) throw new Error(await apiError(response, "No se pudo establecer la contrasena."));
  const data = await response.json();
  return data.item as EmployeeRecord;
}
