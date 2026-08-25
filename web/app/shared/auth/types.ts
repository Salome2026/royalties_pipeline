export type UserRole = "viewer" | "editor" | "admin";

export type WebUser = {
  username: string;
  role: UserRole;
  canEdit: boolean;
  mustChangePassword?: boolean;
};

export type ModulePermission = {
  module_key: string;
  can_access: boolean;
  can_create: boolean;
  can_view_history: boolean;
  can_edit: boolean;
  can_approve: boolean;
  scope: Array<Record<string, string>>;
  notes: string | null;
};

export type AuthActionResult =
  | { ok: true }
  | { ok: false; error: string };
