export type View =
  | "menu"
  | "statement"
  | "royalties"
  | "custom-reports"
  | "participation"
  | "digital-income"
  | "royalties-dashboard"
  | "source-monitor"
  | "catalog"
  | "distributor-config"
  | "booking"
  | "booking-lab"
  | "booking-summary"
  | "commissions"
  | "booking-artist-summary"
  | "artist-finance"
  | "finance-movements"
  | "artists"
  | "employees"
  | "caserio";

export type BookingWorkspaceMode = "individual" | "shared";
export type NavigationTone = "cyan" | "blue" | "green" | "amber" | "coral";
export type NavigationIcon = "booking" | "commissions" | "booking-load" | "caserio" | "royalties-dashboard" | "statement" | "royalties" | "custom-reports" | "digital-income" | "participation" | "catalog" | "source-monitor" | "distributor-config" | "finance-movements" | "artist-finance" | "artists" | "employees";

export type NavigationModule = {
  view: View;
  moduleKey: string;
  title: string;
  description: string;
  icon: NavigationIcon;
  tone: NavigationTone;
  featured?: boolean;
};

export type NavigationGroup = {
  key: string;
  title: string;
  eyebrow: string;
  modules: NavigationModule[];
};

export const APP_NAVIGATION_GROUPS: NavigationGroup[] = [
  {
    key: "booking", title: "Booking y operación", eyebrow: "Shows",
    modules: [
      { view: "booking", moduleKey: "booking", title: "Booking Indyana", description: "Agenda, shows, liquidaciones y seguimiento operativo.", icon: "booking", tone: "cyan", featured: true },
      { view: "commissions", moduleKey: "booking_commissions", title: "Comisiones", description: "Configuración y liquidación por empleado.", icon: "commissions", tone: "amber" },
      { view: "booking-lab", moduleKey: "booking_lab", title: "Carga de shows", description: "Flujos especiales y eventos compartidos.", icon: "booking-load", tone: "blue" },
      { view: "caserio", moduleKey: "caserio", title: "El Caserío", description: "Eventos, artistas externos y shows vinculados.", icon: "caserio", tone: "coral" },
    ],
  },
  {
    key: "royalties", title: "Regalías e inteligencia", eyebrow: "Digital",
    modules: [
      { view: "royalties-dashboard", moduleKey: "royalties_dashboard", title: "Dashboard Regalías", description: "Lectura ejecutiva de ingresos y catálogo.", icon: "royalties-dashboard", tone: "cyan", featured: true },
      { view: "statement", moduleKey: "statement_reports", title: "Reporte por statement", description: "Histórico por artista y distribuidora.", icon: "statement", tone: "blue" },
      { view: "royalties", moduleKey: "royalty_reports", title: "Reporte de regalías", description: "Búsquedas y entregables por período.", icon: "royalties", tone: "green" },
      { view: "custom-reports", moduleKey: "custom_reports", title: "Reportes personalizados", description: "Plantillas especiales guardadas.", icon: "custom-reports", tone: "amber" },
      { view: "digital-income", moduleKey: "digital_income", title: "Ingresos digitales", description: "Ingresos reales por cuenta y artista.", icon: "digital-income", tone: "coral" },
      { view: "participation", moduleKey: "participation", title: "Participación", description: "Distribución de ingresos entre fuentes.", icon: "participation", tone: "green" },
    ],
  },
  {
    key: "catalog", title: "Catálogo y distribución", eyebrow: "Activos",
    modules: [
      { view: "catalog", moduleKey: "catalog", title: "Catálogo general", description: "Temas, artistas, ISRC, labels y metadata.", icon: "catalog", tone: "cyan", featured: true },
      { view: "source-monitor", moduleKey: "source_monitor", title: "Control de distribuidoras", description: "Statements, pendientes y alertas.", icon: "source-monitor", tone: "amber" },
      { view: "distributor-config", moduleKey: "distributor_config", title: "Configurador", description: "Políticas, cuentas y reglas vigentes.", icon: "distributor-config", tone: "blue" },
    ],
  },
  {
    key: "finance", title: "Finanzas y administración", eyebrow: "Empresa",
    modules: [
      { view: "finance-movements", moduleKey: "finance_movements", title: "Movimientos financieros", description: "Gastos, pagos, cobros y documentos.", icon: "finance-movements", tone: "green", featured: true },
      { view: "artist-finance", moduleKey: "artist_finance", title: "Finanzas artista", description: "Cuenta corriente, proyectos y recuperables.", icon: "artist-finance", tone: "cyan" },
      { view: "artists", moduleKey: "artists", title: "Artistas", description: "Fichas y datos operativos.", icon: "artists", tone: "coral" },
      { view: "employees", moduleKey: "employees", title: "Empleados", description: "Equipo, funciones, salarios y permisos.", icon: "employees", tone: "blue" },
    ],
  },
];

const INTERNAL_VIEWS: Array<{ view: View; moduleKey: string; title: string; eyebrow: string; parentView: View }> = [
  { view: "booking-summary", moduleKey: "booking_summary", title: "Resumen Booking", eyebrow: "Shows", parentView: "booking" },
  { view: "booking-artist-summary", moduleKey: "booking_detail", title: "Detalle Booking", eyebrow: "Shows", parentView: "booking" },
];

const navigationModules = APP_NAVIGATION_GROUPS.flatMap((group) => group.modules);

export const VIEW_MODULE_KEYS: Partial<Record<View, string>> = Object.fromEntries([
  ...navigationModules.map((module) => [module.view, module.moduleKey]),
  ...INTERNAL_VIEWS.map((module) => [module.view, module.moduleKey]),
]);

export function moduleForBookingMode(mode: BookingWorkspaceMode) {
  return mode === "individual" ? "booking" : "composite_booking";
}

export function navigationGroupForView(view: View) {
  return APP_NAVIGATION_GROUPS.find((group) => group.modules.some((module) => module.view === view)) || null;
}

export function navigationModuleForView(view: View) {
  return navigationModules.find((module) => module.view === view) || null;
}

export function navigationPresentationForView(view: View) {
  const group = navigationGroupForView(view);
  const module = navigationModuleForView(view);
  if (group && module) return { eyebrow: group.eyebrow, title: module.title, activeView: module.view };
  const internal = INTERNAL_VIEWS.find((item) => item.view === view);
  return internal ? { eyebrow: internal.eyebrow, title: internal.title, activeView: internal.parentView } : null;
}

export function canShowView(view: View, canAccessModule: (moduleKey: string) => boolean) {
  if (view === "menu") return true;
  if (view === "booking") {
    return canAccessModule("booking_agenda")
      || canAccessModule(moduleForBookingMode("individual"))
      || canAccessModule(moduleForBookingMode("shared"));
  }
  const moduleKey = VIEW_MODULE_KEYS[view];
  return moduleKey ? canAccessModule(moduleKey) : false;
}
