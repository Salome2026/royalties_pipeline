"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ModulePermission } from "../../shared/auth/types";
import {
  deactivateEmployee,
  fetchEmployeeArtists,
  fetchEmployees,
  saveEmployee,
  setDefaultEmployeePassword,
} from "./api";
import {
  employeeFormFromRecord,
  initialEmployeeForm,
  permissionWithArtistMode,
  permissionWithLevel,
  permissionWithToggledArtist,
} from "./model";
import type {
  EmployeeFormState,
  EmployeeMessage,
  EmployeeModuleDefinition,
  EmployeeRecord,
} from "./types";

export function useEmployees(onMessage: (message: EmployeeMessage | null) => void) {
  const [records, setRecords] = useState<EmployeeRecord[]>([]);
  const [functionOptions, setFunctionOptions] = useState<string[]>([]);
  const [modules, setModules] = useState<EmployeeModuleDefinition[]>([]);
  const [artists, setArtists] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<EmployeeFormState>(() => initialEmployeeForm());

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [employeeData, artistItems] = await Promise.all([
        fetchEmployees(),
        fetchEmployeeArtists(),
      ]);
      setRecords(employeeData.items || []);
      setFunctionOptions(employeeData.function_options || []);
      setModules(employeeData.modules || []);
      setArtists(artistItems);
      setForm((current) => (
        current.permissions.length === 0
          ? initialEmployeeForm(employeeData.modules || [])
          : current
      ));
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudieron cargar los empleados." });
    } finally {
      setLoading(false);
    }
  }, [onMessage]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const filteredRecords = useMemo(() => {
    const term = search.trim().toLocaleLowerCase("es");
    if (!term) return records;
    return records.filter((item) => [
      item.display_name,
      item.legal_name,
      item.cuit,
      item.phone,
      item.email,
      item.address,
      item.notes,
      item.functions.join(" "),
      item.users?.[0]?.username,
      item.active ? "activo" : "inactivo",
    ].some((value) => String(value || "").toLocaleLowerCase("es").includes(term)));
  }, [records, search]);

  function updateField<K extends keyof EmployeeFormState>(key: K, value: EmployeeFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updatePermission(moduleKey: string, transform: (permission: ModulePermission) => ModulePermission) {
    setForm((current) => {
      const permissions = current.permissions.length ? current.permissions : initialEmployeeForm(modules).permissions;
      return {
        ...current,
        permissions: permissions.map((permission) => (
          permission.module_key === moduleKey ? transform(permission) : permission
        )),
      };
    });
  }

  function setPermissionLevel(moduleKey: string, level: "none" | "view" | "create" | "edit" | "admin") {
    updatePermission(moduleKey, (permission) => permissionWithLevel(permission, level));
  }

  function setPermissionArtistMode(moduleKey: string, mode: "all" | "selected") {
    updatePermission(moduleKey, (permission) => permissionWithArtistMode(permission, mode));
  }

  function togglePermissionArtist(moduleKey: string, artist: string) {
    updatePermission(moduleKey, (permission) => permissionWithToggledArtist(permission, artist));
  }

  function toggleFunction(functionName: string) {
    setForm((current) => ({
      ...current,
      functions: current.functions.includes(functionName)
        ? current.functions.filter((item) => item !== functionName)
        : [...current.functions, functionName],
    }));
  }

  function resetForm() {
    setEditingId(null);
    setForm(initialEmployeeForm(modules));
  }

  function editRecord(item: EmployeeRecord) {
    setEditingId(item.id);
    setForm(employeeFormFromRecord(item, modules));
  }

  async function submit() {
    setLoading(true);
    onMessage(null);
    const wasEditing = editingId !== null;
    try {
      const item = await saveEmployee(form, editingId);
      setRecords((current) => (
        wasEditing
          ? current.map((record) => (record.id === item.id ? item : record))
          : [item, ...current]
      ));
      resetForm();
      onMessage({ type: "ok", text: wasEditing ? "Empleado actualizado correctamente." : "Empleado creado correctamente." });
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo guardar el empleado." });
    } finally {
      setLoading(false);
    }
  }

  async function deactivateRecord(item: EmployeeRecord) {
    setLoading(true);
    onMessage(null);
    try {
      const updated = await deactivateEmployee(item.id);
      setRecords((current) => current.map((record) => (record.id === updated.id ? updated : record)));
      if (editingId === updated.id) resetForm();
      onMessage({ type: "ok", text: "Empleado desactivado. Sigue guardado para historial y auditoria." });
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo desactivar el empleado." });
    } finally {
      setLoading(false);
    }
  }

  async function resetPassword(item: EmployeeRecord) {
    setLoading(true);
    onMessage(null);
    try {
      const updated = await setDefaultEmployeePassword(item.id);
      setRecords((current) => current.map((record) => (record.id === updated.id ? updated : record)));
      if (editingId === updated.id) setForm(employeeFormFromRecord(updated, modules));
      onMessage({ type: "ok", text: `Contrasena default establecida para ${item.display_name}.` });
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo establecer la contrasena." });
    } finally {
      setLoading(false);
    }
  }

  return {
    records,
    filteredRecords,
    functionOptions,
    modules,
    artists,
    search,
    loading,
    editingId,
    form,
    setSearch,
    updateField,
    setPermissionLevel,
    setPermissionArtistMode,
    togglePermissionArtist,
    toggleFunction,
    resetForm,
    editRecord,
    submit,
    deactivateRecord,
    resetPassword,
    loadData,
  };
}
