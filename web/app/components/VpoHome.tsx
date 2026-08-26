"use client";

import { useMemo } from "react";
import {
  ChevronRight,
  ReceiptText,
  Settings2,
  ShieldCheck,
  UserRoundCog,
} from "lucide-react";
import { APP_NAVIGATION_GROUPS } from "../shared/navigation/views";
import { NAVIGATION_ICONS } from "./VpoAppFrame";

type VpoHomeProps = {
  canShow: (view: string) => boolean;
  onOpen: (view: string) => void;
};

export function VpoHome({ canShow, onOpen }: VpoHomeProps) {
  const visibleGroups = useMemo(
    () => APP_NAVIGATION_GROUPS
      .map((group) => ({ ...group, modules: group.modules.filter((module) => canShow(module.view)) }))
      .filter((group) => group.modules.length > 0),
    [canShow],
  );
  const visibleModules = visibleGroups.flatMap((group) => group.modules);

  return (
    <div className="vpo-home-content">
          <section className="vpo-home-intro">
            <div>
              <span className="vpo-home-eyebrow">VPO Corp</span>
              <h2>Todo el negocio, en un solo lugar.</h2>
              <p>Elegí el área en la que querés trabajar. Vas a ver únicamente los módulos habilitados para tu usuario.</p>
            </div>
            <div className="vpo-home-summary">
              <ShieldCheck size={20} />
              <div><strong>{visibleModules.length} módulos disponibles</strong><small>Permisos verificados</small></div>
            </div>
          </section>

          {visibleGroups.map((group) => (
            <section className="vpo-home-section" key={group.key}>
              <div className="vpo-home-section-heading">
                <div><span>{group.eyebrow}</span><h2>{group.title}</h2></div>
                <small>{group.modules.length} {group.modules.length === 1 ? "módulo" : "módulos"}</small>
              </div>
              <div className="vpo-home-grid">
                {group.modules.map((module) => {
                  const ModuleIcon = NAVIGATION_ICONS[module.icon];
                  return (
                    <button
                      type="button"
                      key={module.view}
                      className={`vpo-home-card tone-${module.tone} ${module.featured ? "is-featured" : ""}`}
                      onClick={() => onOpen(module.view)}
                    >
                      <span className="vpo-home-card-icon"><ModuleIcon size={22} strokeWidth={1.8} /></span>
                      <span className="vpo-home-card-copy"><strong>{module.title}</strong><small>{module.description}</small></span>
                      <ChevronRight className="vpo-home-card-arrow" size={19} />
                    </button>
                  );
                })}
              </div>
            </section>
          ))}

          <footer className="vpo-home-footer">
            <span><Settings2 size={15} />Configuración centralizada</span>
            <span><ReceiptText size={15} />Datos operativos en Cloud SQL</span>
            <span><UserRoundCog size={15} />Acceso según permisos</span>
          </footer>
    </div>
  );
}
