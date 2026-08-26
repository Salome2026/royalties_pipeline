"use client";

import Image from "next/image";
import { useMemo, useState, type ComponentType, type ReactNode } from "react";
import {
  BarChart3,
  BookOpenCheck,
  CalendarDays,
  ChartNoAxesCombined,
  CircleDollarSign,
  ClipboardList,
  FileChartColumn,
  FileSpreadsheet,
  FolderKanban,
  Gauge,
  Landmark,
  LayoutDashboard,
  Library,
  LogOut,
  Menu,
  MonitorCog,
  Music2,
  SlidersHorizontal,
  UsersRound,
  WalletCards,
  X,
} from "lucide-react";
import { APP_NAVIGATION_GROUPS, navigationPresentationForView, type NavigationIcon, type View } from "../shared/navigation/views";

type Icon = ComponentType<{ size?: number; strokeWidth?: number; "aria-hidden"?: boolean }>;

export const NAVIGATION_ICONS: Record<NavigationIcon, Icon> = {
  booking: CalendarDays,
  commissions: CircleDollarSign,
  "booking-load": ClipboardList,
  caserio: FolderKanban,
  "royalties-dashboard": Gauge,
  statement: FileChartColumn,
  royalties: FileSpreadsheet,
  "custom-reports": BookOpenCheck,
  "digital-income": ChartNoAxesCombined,
  participation: BarChart3,
  catalog: Library,
  "source-monitor": MonitorCog,
  "distributor-config": SlidersHorizontal,
  "finance-movements": WalletCards,
  "artist-finance": Landmark,
  artists: Music2,
  employees: UsersRound,
};

type Props = {
  currentView: View;
  username: string;
  role: string;
  eyebrow: string;
  title: string;
  canShow: (view: string) => boolean;
  onOpen: (view: string) => void;
  onLogout: () => void;
  children: ReactNode;
};

export function VpoAppFrame({ currentView, username, role, eyebrow, title, canShow, onOpen, onLogout, children }: Props) {
  const [navigationOpen, setNavigationOpen] = useState(false);
  const visibleGroups = useMemo(
    () => APP_NAVIGATION_GROUPS
      .map((group) => ({ ...group, modules: group.modules.filter((module) => canShow(module.view)) }))
      .filter((group) => group.modules.length > 0),
    [canShow],
  );
  const activeView = navigationPresentationForView(currentView)?.activeView || currentView;

  function openModule(view: string) {
    setNavigationOpen(false);
    onOpen(view);
  }

  return (
    <div className={`vpo-app-shell vpo-app-frame vpo-view-${currentView}`}>
      <button type="button" className={`vpo-app-scrim ${navigationOpen ? "is-open" : ""}`} aria-label="Cerrar navegación" onClick={() => setNavigationOpen(false)} />

      <aside className={`vpo-app-sidebar ${navigationOpen ? "is-open" : ""}`}>
        <div className="vpo-app-brand">
          <Image className="vpo-app-brand-image" src="/vpo-logo.png" alt="VPO Corp" width={2539} height={1298} priority />
          <button type="button" className="vpo-app-nav-close" aria-label="Cerrar menú" onClick={() => setNavigationOpen(false)}><X size={19} /></button>
        </div>
        <nav aria-label="Navegación principal">
          <button type="button" className={currentView === "menu" ? "is-active" : ""} onClick={() => openModule("menu")}><LayoutDashboard size={18} />Inicio</button>
          {visibleGroups.map((group) => (
            <div className="vpo-app-nav-group" key={group.key}>
              <span>{group.eyebrow}</span>
              {group.modules.map((module) => {
                const ModuleIcon = NAVIGATION_ICONS[module.icon];
                return <button type="button" className={activeView === module.view ? "is-active" : ""} key={module.view} onClick={() => openModule(module.view)}><ModuleIcon size={17} />{module.title}</button>;
              })}
            </div>
          ))}
        </nav>
        <div className="vpo-app-account">
          <span className="vpo-app-avatar">{username.slice(0, 1).toUpperCase()}</span>
          <div><strong>{username}</strong><small>{role}</small></div>
          <button type="button" aria-label="Cerrar sesión" title="Cerrar sesión" onClick={onLogout}><LogOut size={17} /></button>
        </div>
      </aside>

      <div className="vpo-app-stage">
        <header className="vpo-app-header">
          <button type="button" className="vpo-app-menu-button" aria-label="Abrir menú" onClick={() => setNavigationOpen(true)}><Menu size={21} /></button>
          <div><span>{eyebrow}</span><h1>{title}</h1></div>
          <div className="vpo-app-live"><i />Operación viva</div>
        </header>
        {children}
      </div>
    </div>
  );
}
