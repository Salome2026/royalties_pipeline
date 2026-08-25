import type { ModulePermission } from "../../shared/auth/types";

export type EmployeeCompensationType =
  | "none"
  | "salary"
  | "salary_plus_booking_commission"
  | "booking_commission_only";

export const employeeCompensationLabels: Record<EmployeeCompensationType, string> = {
  none: "Sin compensacion fija",
  salary: "Salario mensual",
  salary_plus_booking_commission: "Salario + comision booking",
  booking_commission_only: "Solo comision booking",
};

export type EmployeeUser = {
  id: number;
  username: string;
  global_role: "viewer" | "editor" | "admin";
  active: boolean;
  auth_source: string;
  has_password?: boolean;
  must_change_password?: boolean;
  last_login_at?: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type EmployeeRecord = {
  id: number;
  display_name: string;
  legal_name: string | null;
  cuit: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  compensation_type: EmployeeCompensationType;
  salary_amount: number;
  salary_currency: "ARS" | "USD";
  salary_frequency: "monthly";
  salary_notes: string | null;
  notes: string | null;
  active: boolean;
  functions: string[];
  users: EmployeeUser[];
  permissions: ModulePermission[];
  created_at: string;
  updated_at: string;
};

export type EmployeeModuleDefinition = {
  module_key: string;
  label: string;
};

export type EmployeeFormState = {
  displayName: string;
  cuit: string;
  phone: string;
  email: string;
  address: string;
  functions: string[];
  compensationType: EmployeeCompensationType;
  salaryAmount: string;
  salaryCurrency: "ARS" | "USD";
  salaryFrequency: "monthly";
  salaryNotes: string;
  username: string;
  newPassword: string;
  mustChangePassword: boolean;
  userRole: "viewer" | "editor" | "admin";
  userActive: boolean;
  permissions: ModulePermission[];
  notes: string;
  active: boolean;
};

export type EmployeeMessage = {
  type: "ok" | "error";
  text: string;
};

export type EmployeeData = {
  items: EmployeeRecord[];
  function_options: string[];
  modules: EmployeeModuleDefinition[];
};
