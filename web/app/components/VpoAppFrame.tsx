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

type Icon = ComponentType<{ size?: number; strokeWidth?: number; "aria-hidden"?: boolean }>;

export type HomeModule = {
  view: string;
  title: string;
  description: string;
  icon: Icon;
  tone: "cyan" | "blue" | "green" | "amber" | "coral";
  featured?: boolean;
};

export type HomeGroup = {
  key: string;
  title: string;
  eyebrow: string;
  modules: HomeModule[];
};

export const HOME_GROUPS: HomeGroup[] = [
  {
    key: "booking",
    title: "Booking y operación",
    eyebrow: "Shows",
    modules: [
      { view: "booking", title: "Booking Indyana", description: "Agenda, shows, liquidaciones y seguimiento operativo.", icon: CalendarDays, tone: "cyan", featured: true },
      { view: "commissions", title: "Comisiones", description: "Configuración y liquidación por empleado.", icon: CircleDollarSign, tone: "amber" },
      { view: "booking-lab", title: "Carga de shows", description: "Flujos especiales y eventos compartidos.", icon: ClipboardList, tone: "blue" },
      { view: "caserio", title: "El Caserío", description: "Eventos, artistas externos y shows vinculados.", icon: FolderKanban, tone: "coral" },
    ],
  },
  {
    key: "royalties",
    title: "Regalías e inteligencia",
    eyebrow: "Digital",
    modules: [
      { view: "royalties-dashboard", title: "Dashboard Regalías", description: "Lectura ejecutiva de ingresos y catálogo.", icon: Gauge, tone: "cyan", featured: true },
      { view: "statement", title: "Reporte por statement", description: "Histórico por artista y distribuidora.", icon: FileChartColumn, tone: "blue" },
      { view: "royalties", title: "Reporte de regalías", description: "Búsquedas y entregables por período.", icon: FileSpreadsheet, tone: "green" },
      { view: "custom-reports", title: "Reportes personalizados", description: "Plantillas especiales guardadas.", icon: BookOpenCheck, tone: "amber" },
      { view: "digital-income", title: "Ingresos digitales", description: "Ingresos reales por cuenta y artista.", icon: ChartNoAxesCombined, tone: "coral" },
      { view: "participation", title: "Participación", description: "Distribución de ingresos entre fuentes.", icon: BarChart3, tone: "green" },
    ],
  },
  {
    key: "catalog",
    title: "Catálogo y distribución",
    eyebrow: "Activos",
    modules: [
      { view: "catalog", title: "Catálogo general", description: "Temas, artistas, ISRC, labels y metadata.", icon: Library, tone: "cyan", featured: true },
      { view: "source-monitor", title: "Control de distribuidoras", description: "Statements, pendientes y alertas.", icon: MonitorCog, tone: "amber" },
      { view: "distributor-config", title: "Configurador", description: "Políticas, cuentas y reglas vigentes.", icon: SlidersHorizontal, tone: "blue" },
    ],
  },
  {
    key: "finance",
    title: "Finanzas y administración",
    eyebrow: "Empresa",
    modules: [
      { view: "finance-movements", title: "Movimientos financieros", description: "Gastos, pagos, cobros y documentos.", icon: WalletCards, tone: "green", featured: true },
      { view: "artist-finance", title: "Finanzas artista", description: "Cuenta corriente, proyectos y recuperables.", icon: Landmark, tone: "cyan" },
      { view: "artists", title: "Artistas", description: "Fichas y datos operativos.", icon: Music2, tone: "coral" },
      { view: "employees", title: "Empleados", description: "Equipo, funciones, salarios y permisos.", icon: UsersRound, tone: "blue" },
    ],
  },
];

type Props = {
  currentView: string;
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
    () => HOME_GROUPS
      .map((group) => ({ ...group, modules: group.modules.filter((module) => canShow(module.view)) }))
      .filter((group) => group.modules.length > 0),
    [canShow],
  );

  function openModule(view: string) {
    setNavigationOpen(false);
    onOpen(view);
  }

  return (
    <div className={`vpo-home-shell vpo-app-frame vpo-view-${currentView}`}>
      <button type="button" className={`vpo-home-scrim ${navigationOpen ? "is-open" : ""}`} aria-label="Cerrar navegación" onClick={() => setNavigationOpen(false)} />

      <aside className={`vpo-home-sidebar ${navigationOpen ? "is-open" : ""}`}>
        <div className="vpo-home-brand">
          <Image className="vpo-home-brand-image" src="/vpo-logo.png" alt="VPO Corp" width={2539} height={1298} priority />
          <button type="button" className="vpo-home-nav-close" aria-label="Cerrar menú" onClick={() => setNavigationOpen(false)}><X size={19} /></button>
        </div>
        <nav aria-label="Navegación principal">
          <button type="button" className={currentView === "menu" ? "is-active" : ""} onClick={() => openModule("menu")}><LayoutDashboard size={18} />Inicio</button>
          {visibleGroups.map((group) => (
            <div className="vpo-home-nav-group" key={group.key}>
              <span>{group.eyebrow}</span>
              {group.modules.map((module) => {
                const ModuleIcon = module.icon;
                return <button type="button" className={currentView === module.view ? "is-active" : ""} key={module.view} onClick={() => openModule(module.view)}><ModuleIcon size={17} />{module.title}</button>;
              })}
            </div>
          ))}
        </nav>
        <div className="vpo-home-account">
          <span className="vpo-home-avatar">{username.slice(0, 1).toUpperCase()}</span>
          <div><strong>{username}</strong><small>{role}</small></div>
          <button type="button" aria-label="Cerrar sesión" title="Cerrar sesión" onClick={onLogout}><LogOut size={17} /></button>
        </div>
      </aside>

      <div className="vpo-home-stage">
        <header className="vpo-home-header">
          <button type="button" className="vpo-home-menu-button" aria-label="Abrir menú" onClick={() => setNavigationOpen(true)}><Menu size={21} /></button>
          <div><span>{eyebrow}</span><h1>{title}</h1></div>
          <div className="vpo-home-live"><i />Operación viva</div>
        </header>
        {children}
      </div>
    </div>
  );
}
