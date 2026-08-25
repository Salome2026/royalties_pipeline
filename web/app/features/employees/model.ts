import type { ModulePermission } from "../../shared/auth/types";
import {
  permissionArtistNames,
  permissionHasAllArtists,
  permissionUsesArtistScope,
} from "../../shared/auth/permissions";
import type { EmployeeFormState, EmployeeModuleDefinition, EmployeeRecord } from "./types";

export type PermissionLevel = "none" | "view" | "create" | "edit" | "admin";

export const DEFAULT_EMPLOYEE_FUNCTIONS = [
  "Tour Manager",
  "Project Manager",
  "Label",
  "Digitales",
  "Administracion",
  "Presidente",
  "Vice Presidente",
];

export function defaultEmployeePermission(module: EmployeeModuleDefinition): ModulePermission {
  const agendaView = module.module_key === "booking_agenda";
  return {
    module_key: module.module_key,
    can_access: agendaView,
    can_create: false,
    can_view_history: agendaView,
    can_edit: false,
    can_approve: false,
    scope: agendaView ? [{ scope_type: "all", scope_ref: "*" }] : [],
    notes: agendaView ? "Acceso inicial de lectura a la Agenda Booking." : null,
  };
}

export function defaultEmployeePermissions(modules: EmployeeModuleDefinition[]) {
  return modules
    .filter((module) => module.module_key !== "home")
    .map(defaultEmployeePermission);
}

export function mergedEmployeePermissions(modules: EmployeeModuleDefinition[], employee?: EmployeeRecord) {
  const existing = new Map((employee?.permissions || []).map((permission) => [permission.module_key, permission]));
  return modules
    .filter((module) => module.module_key !== "home")
    .map((module) => existing.get(module.module_key) || defaultEmployeePermission(module));
}

export function initialEmployeeForm(modules: EmployeeModuleDefinition[] = []): EmployeeFormState {
  return {
    displayName: "",
    cuit: "",
    phone: "",
    email: "",
    address: "",
    functions: [],
    compensationType: "none",
    salaryAmount: "",
    salaryCurrency: "ARS",
    salaryFrequency: "monthly",
    salaryNotes: "",
    username: "",
    newPassword: "",
    mustChangePassword: true,
    userRole: "viewer",
    userActive: true,
    permissions: defaultEmployeePermissions(modules),
    notes: "",
    active: true,
  };
}

export function amountToEmployeeInput(value: number | null | undefined) {
  if (!value || !Number.isFinite(value)) return "";
  return Number.isInteger(value) ? String(value) : value.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
}

export function employeeFormFromRecord(
  employee: EmployeeRecord,
  modules: EmployeeModuleDefinition[],
): EmployeeFormState {
  const primaryUser = employee.users?.[0];
  return {
    displayName: employee.display_name,
    cuit: employee.cuit || "",
    phone: employee.phone || "",
    email: employee.email || "",
    address: employee.address || "",
    functions: employee.functions || [],
    compensationType: employee.compensation_type || "none",
    salaryAmount: amountToEmployeeInput(employee.salary_amount || 0),
    salaryCurrency: employee.salary_currency || "ARS",
    salaryFrequency: employee.salary_frequency || "monthly",
    salaryNotes: employee.salary_notes || "",
    username: primaryUser?.username || "",
    newPassword: "",
    mustChangePassword: primaryUser?.must_change_password ?? true,
    userRole: primaryUser?.global_role || "viewer",
    userActive: primaryUser?.active ?? true,
    permissions: mergedEmployeePermissions(modules, employee),
    notes: employee.notes || "",
    active: employee.active,
  };
}

export function employeePermissionLevel(permission: ModulePermission): PermissionLevel {
  if (permission.can_approve && permission.can_edit && permission.can_create && permission.can_view_history && permission.can_access) return "admin";
  if (permission.can_edit) return "edit";
  if (permission.can_create) return "create";
  if (permission.can_access || permission.can_view_history) return "view";
  return "none";
}

export { permissionArtistNames, permissionHasAllArtists, permissionUsesArtistScope };

export function normalizeEmployeePermissionForSave(permission: ModulePermission) {
  if (!permission.can_access || !permissionUsesArtistScope(permission)) return permission;
  if (permissionHasAllArtists(permission)) {
    return { ...permission, scope: [{ scope_type: "all", scope_ref: "*" }] };
  }
  if (permissionArtistNames(permission).length === 0) {
    return { ...permission, scope: [{ scope_type: "none", scope_ref: "*" }] };
  }
  return permission;
}

export function permissionWithLevel(permission: ModulePermission, level: PermissionLevel) {
  const next = {
    ...permission,
    can_access: level !== "none",
    can_create: ["create", "edit", "admin"].includes(level),
    can_view_history: ["view", "edit", "admin"].includes(level)
      || (permission.module_key === "booking_agenda" && level === "create"),
    can_edit: ["edit", "admin"].includes(level),
    can_approve: level === "admin",
  };
  if (next.can_access && permissionUsesArtistScope(next) && (!next.scope || next.scope.length === 0)) {
    return { ...next, scope: [{ scope_type: "all", scope_ref: "*" }] };
  }
  return next;
}

export function permissionWithArtistMode(permission: ModulePermission, mode: "all" | "selected") {
  return {
    ...permission,
    scope: mode === "all"
      ? [{ scope_type: "all", scope_ref: "*" }]
      : [{ scope_type: "none", scope_ref: "*" }],
  };
}

export function permissionWithToggledArtist(permission: ModulePermission, artist: string) {
  const artists = new Set(permissionArtistNames(permission));
  if (artists.has(artist)) artists.delete(artist);
  else artists.add(artist);
  return {
    ...permission,
    scope: artists.size === 0
      ? [{ scope_type: "none", scope_ref: "*" }]
      : Array.from(artists)
        .sort((left, right) => left.localeCompare(right))
        .map((scope_ref) => ({ scope_type: "artist", scope_ref })),
  };
}

export function parseEmployeeAmount(value: string) {
  const raw = String(value || "").replace(/\s/g, "").replace(/\$/g, "").trim();
  if (!raw) return 0;
  const lastComma = raw.lastIndexOf(",");
  const lastDot = raw.lastIndexOf(".");
  let normalized = raw;
  if (lastComma >= 0 && lastDot >= 0) {
    const decimalSeparator = lastComma > lastDot ? "," : ".";
    const thousandsSeparator = decimalSeparator === "," ? "." : ",";
    normalized = raw.replace(new RegExp(`\\${thousandsSeparator}`, "g"), "").replace(decimalSeparator, ".");
  } else if (lastComma >= 0) {
    normalized = raw.replace(/\./g, "").replace(",", ".");
  } else if (lastDot >= 0) {
    const dotCount = (raw.match(/\./g) || []).length;
    const decimals = raw.length - lastDot - 1;
    normalized = dotCount === 1 && decimals > 0 && decimals <= 2 ? raw : raw.replace(/\./g, "");
  }
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function formatEmployeeSalary(currency: "ARS" | "USD", value: number) {
  return new Intl.NumberFormat(currency === "USD" ? "en-US" : "es-AR", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value || 0);
}
