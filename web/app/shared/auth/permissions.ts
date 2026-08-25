import type { ModulePermission } from "./types";

const ARTIST_SCOPED_MODULES = new Set([
  "booking",
  "booking_detail",
  "booking_summary",
  "booking_commissions",
  "artist_finance",
  "finance_movements",
]);

export function artistScopeKey(value: string) {
  return String(value || "")
    .trim()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

export function permissionHasAllArtists(permission: ModulePermission) {
  if (!permission.scope || permission.scope.length === 0) return true;
  return permission.scope.some((item) => item.scope_type === "all" && item.scope_ref === "*");
}

export function permissionUsesArtistScope(permission: ModulePermission) {
  return ARTIST_SCOPED_MODULES.has(permission.module_key);
}

export function permissionArtistNames(permission: ModulePermission) {
  if (permissionHasAllArtists(permission)) return [];
  return (permission.scope || [])
    .filter((item) => item.scope_type === "artist" && item.scope_ref)
    .map((item) => item.scope_ref);
}
