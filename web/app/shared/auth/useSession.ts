"use client";

import { useCallback, useEffect, useState } from "react";
import type { AuthActionResult, ModulePermission, WebUser } from "./types";

const adminPermission = (moduleKey: string): ModulePermission => ({
  module_key: moduleKey,
  can_access: true,
  can_create: true,
  can_view_history: true,
  can_edit: true,
  can_approve: true,
  scope: [{ scope_type: "all", scope_ref: "*" }],
  notes: null,
});

async function responseError(response: Response, fallback: string) {
  const data = await response.json().catch(() => ({ error: fallback }));
  return String(data.error || fallback);
}

export function useSession() {
  const [currentUser, setCurrentUser] = useState<WebUser | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [moduleAccess, setModuleAccess] = useState<string[] | null>(null);
  const [permissions, setPermissions] = useState<ModulePermission[] | null>(null);

  useEffect(() => {
    let active = true;

    fetch("/api/session", { cache: "no-store" })
      .then((response) => response.json())
      .then((data) => {
        if (!active) return;
        setCurrentUser(data.authenticated ? data.user || null : null);
      })
      .catch(() => {
        if (active) setCurrentUser(null);
      })
      .finally(() => {
        if (active) setCheckingSession(false);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    if (!currentUser) {
      setModuleAccess(null);
      setPermissions(null);
      return () => {
        active = false;
      };
    }

    if (currentUser.role === "admin") {
      setModuleAccess(["*"]);
      setPermissions(null);
      return () => {
        active = false;
      };
    }

    setModuleAccess(null);
    setPermissions(null);
    fetch("/api/me/permissions", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("permissions");
        return response.json();
      })
      .then((data) => {
        if (!active) return;
        const nextPermissions = (data.permissions || []) as ModulePermission[];
        const nextAccess = nextPermissions
          .filter((permission) => permission.can_access)
          .map((permission) => permission.module_key)
          .filter((moduleKey) => moduleKey !== "home");
        setPermissions(nextPermissions);
        setModuleAccess(nextAccess);
      })
      .catch(() => {
        if (!active) return;
        setPermissions([]);
        setModuleAccess([]);
      });

    return () => {
      active = false;
    };
  }, [currentUser]);

  const login = useCallback(async (username: string, password: string): Promise<AuthActionResult> => {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    if (!response.ok) {
      return { ok: false, error: await responseError(response, "No se pudo ingresar.") };
    }

    const data = await response.json();
    setCurrentUser(data.user || null);
    return { ok: true };
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/logout", { method: "POST" }).catch(() => null);
    setCurrentUser(null);
    setModuleAccess(null);
    setPermissions(null);
  }, []);

  const changePassword = useCallback(async (
    currentPassword: string,
    newPassword: string,
  ): Promise<AuthActionResult> => {
    const response = await fetch("/api/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ currentPassword, newPassword }),
    });

    if (!response.ok) {
      return { ok: false, error: await responseError(response, "No se pudo cambiar la contrasena.") };
    }

    const data = await response.json();
    setCurrentUser((user) => data.user || (user ? { ...user, mustChangePassword: false } : null));
    return { ok: true };
  }, []);

  const canAccessModule = useCallback((moduleKey: string) => {
    if (currentUser?.role === "admin") return true;
    const allowed = moduleAccess ?? [];
    return allowed.includes("*") || allowed.includes(moduleKey);
  }, [currentUser?.role, moduleAccess]);

  const currentModulePermission = useCallback((moduleKey: string) => {
    if (currentUser?.role === "admin") return adminPermission(moduleKey);
    return (permissions || []).find((permission) => permission.module_key === moduleKey) || null;
  }, [currentUser?.role, permissions]);

  const canCreateModule = useCallback(
    (moduleKey: string) => Boolean(currentModulePermission(moduleKey)?.can_create),
    [currentModulePermission],
  );
  const canEditModule = useCallback(
    (moduleKey: string) => Boolean(currentModulePermission(moduleKey)?.can_edit),
    [currentModulePermission],
  );
  const canApproveModule = useCallback(
    (moduleKey: string) => Boolean(currentModulePermission(moduleKey)?.can_approve),
    [currentModulePermission],
  );

  return {
    authenticated: Boolean(currentUser),
    checkingSession,
    currentUser,
    moduleAccess,
    permissions,
    login,
    logout,
    changePassword,
    canAccessModule,
    currentModulePermission,
    canCreateModule,
    canEditModule,
    canApproveModule,
  };
}
