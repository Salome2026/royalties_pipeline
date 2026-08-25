"use client";

import type { ModulePermission } from "../../shared/auth/types";
import {
  employeePermissionLevel,
  permissionArtistNames,
  permissionHasAllArtists,
  permissionUsesArtistScope,
  type PermissionLevel,
} from "./model";
import type { EmployeeModuleDefinition } from "./types";

type Props = {
  permissions: ModulePermission[];
  modules: EmployeeModuleDefinition[];
  artists: string[];
  onLevelChange: (moduleKey: string, level: PermissionLevel) => void;
  onArtistModeChange: (moduleKey: string, mode: "all" | "selected") => void;
  onArtistToggle: (moduleKey: string, artist: string) => void;
};

function permissionHelp(moduleKey: string, level: PermissionLevel) {
  if (moduleKey === "booking_agenda") {
    return {
      none: "No puede abrir la Agenda.",
      view: "Puede ver toda la Agenda.",
      create: "Puede ver y cargar entradas.",
      edit: "Puede ver, cargar y editar entradas.",
      admin: "Puede administrar toda la Agenda.",
    }[level];
  }
  return {
    none: "No puede abrir el modulo.",
    view: "Puede entrar y ver historial.",
    create: "Puede entrar y cargar nuevo, sin historial amplio.",
    edit: "Puede ver historial, cargar y editar.",
    admin: "Puede hacer todo, incluyendo aprobar/cerrar.",
  }[level];
}

export function PermissionsEditor({
  permissions,
  modules,
  artists,
  onLevelChange,
  onArtistModeChange,
  onArtistToggle,
}: Props) {
  return (
    <div className="permission-level-list">
      {permissions.map((permission) => {
        const moduleLabel = modules.find((module) => module.module_key === permission.module_key)?.label || permission.module_key;
        const level = employeePermissionLevel(permission);
        const usesArtistScope = permissionUsesArtistScope(permission);
        const allArtists = permissionHasAllArtists(permission);
        const selectedArtists = permissionArtistNames(permission);
        return (
          <div className="permission-level-row" key={permission.module_key}>
            <div>
              <strong>{moduleLabel}</strong>
              <span>{permissionHelp(permission.module_key, level)}</span>
            </div>
            <select
              value={level}
              onChange={(event) => onLevelChange(permission.module_key, event.target.value as PermissionLevel)}
            >
              <option value="none">Sin acceso</option>
              <option value="view">Ver</option>
              <option value="create">Cargar</option>
              <option value="edit">Editar</option>
              <option value="admin">Admin</option>
            </select>
            {usesArtistScope && level !== "none" && (
              <div className="permission-scope-box">
                <div className="permission-scope-header">
                  <strong>Artistas</strong>
                  <span>{allArtists ? "Todos" : `${selectedArtists.length} seleccionado(s)`}</span>
                </div>
                <div className="permission-scope-mode">
                  <label className="check-row">
                    <input
                      type="radio"
                      name={`artist_scope_${permission.module_key}`}
                      checked={allArtists}
                      onChange={() => onArtistModeChange(permission.module_key, "all")}
                    />
                    <span>Todos los artistas</span>
                  </label>
                  <label className="check-row">
                    <input
                      type="radio"
                      name={`artist_scope_${permission.module_key}`}
                      checked={!allArtists}
                      onChange={() => onArtistModeChange(permission.module_key, "selected")}
                    />
                    <span>Solo seleccionados</span>
                  </label>
                </div>
                {!allArtists && (
                  <div className="permission-artist-grid">
                    {artists.map((artist) => (
                      <label className="checkbox-field compact" key={`${permission.module_key}_${artist}`}>
                        <input
                          type="checkbox"
                          checked={selectedArtists.includes(artist)}
                          onChange={() => onArtistToggle(permission.module_key, artist)}
                        />
                        {artist}
                      </label>
                    ))}
                    {artists.length === 0 && (
                      <p className="field-help">No hay artistas cargados para seleccionar.</p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
