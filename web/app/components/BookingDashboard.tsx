"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  CalendarPlus,
  ChevronDown,
  ChevronRight,
  CircleDollarSign,
  ClipboardCheck,
  LayoutDashboard,
  ListFilter,
  Pencil,
  Plus,
  Search,
  Trash2,
  Users,
} from "lucide-react";
import { BookingCalendar } from "./BookingCalendar";

export type BookingAgendaArtist = {
  artist_id: number;
  artist: string;
  position: number;
};

export type BookingAgendaDeposit = {
  id: number;
  movement_date: string;
  amount: number;
  currency: "ARS" | "USD";
  fx_rate: number;
  received_by: "indyana" | "artista" | "empleado" | "tercero";
  received_by_name?: string | null;
  payment_method: "transferencia" | "efectivo" | "otro";
  counterparty?: string | null;
  proof_refs: string[];
  notes?: string | null;
};

export type BookingAgendaEvent = {
  id: number;
  event_type: "show" | "show_group" | "availability_block" | "logistics" | "prospect";
  event_date: string;
  start_time?: string | null;
  venue: string;
  city?: string | null;
  booking_mode: "individual" | "shared";
  commercial_status: "confirmado" | "cancelado" | "prospecto" | "no_aplica";
  operational_status: "programado" | "realizado" | "bloqueado" | "informativo";
  deposit_status: "no_informada" | "sin_sena" | "sena_parcial" | "sena_recibida";
  settlement_status: "no_iniciada" | "pendiente" | "rendida" | "observada" | "cerrada" | "no_aplica";
  contracted_cachet_amount: number;
  currency: "ARS" | "USD";
  fx_rate: number;
  tour_manager?: string | null;
  seller?: string | null;
  notes?: string | null;
  artists: BookingAgendaArtist[];
  deposits: BookingAgendaDeposit[];
  deposit_total: number;
  booking_show_id?: number | null;
  composite_event_id?: number | null;
  caserio_event_id?: number | null;
  group_event_id?: number | null;
  group_position?: number | null;
  group_count: number;
  source_text?: string | null;
};

type BookingAgendaOption = {
  id: number;
  artist: string;
  can_individual: boolean;
  can_shared: boolean;
};

type PermissionState = {
  access: boolean;
  create: boolean;
  view_history: boolean;
  edit: boolean;
};

type BookingDuplicateCandidate = {
  source: "agenda" | "booking_individual" | "booking_compartido";
  id: number;
  date: string;
  venue: string;
  city?: string;
  artists: string[];
  match: "duplicado" | "conflicto_agenda";
};

type BookingDashboardProps = {
  onOpenSettlements: (mode: "individual" | "shared") => void;
  onOpenSummary: () => void;
  onOpenDetail: () => void;
  onOpenCaserio: () => void;
  onStartSettlement: (event: BookingAgendaEvent) => void;
};

type DashboardSection = "overview" | "agenda" | "new";

type AgendaEventType = BookingAgendaEvent["event_type"];

type AgendaGroupChildForm = {
  id?: number;
  eventDate: string;
  startTime: string;
  venue: string;
  city: string;
  cachet: string;
  notes: string;
};

const newGroupChild = (eventDate = localIsoDate()): AgendaGroupChildForm => ({
  eventDate,
  startTime: "",
  venue: "",
  city: "",
  cachet: "",
  notes: "",
});

const initialForm = () => ({
  eventType: "show" as AgendaEventType,
  eventDate: new Date().toISOString().slice(0, 10),
  startTime: "",
  venue: "",
  city: "",
  artists: [] as string[],
  cachet: "",
  currency: "ARS" as "ARS" | "USD",
  fxRate: "",
  tourManager: "",
  seller: "",
  hasDeposit: false,
  depositDate: new Date().toISOString().slice(0, 10),
  depositAmount: "",
  depositCurrency: "ARS" as "ARS" | "USD",
  depositFxRate: "",
  receivedBy: "indyana" as "indyana" | "artista" | "empleado" | "tercero",
  receivedByName: "",
  paymentMethod: "transferencia" as "transferencia" | "efectivo" | "otro",
  counterparty: "",
  proofRefs: "",
  depositNotes: "",
  notes: "",
  duplicateOverride: false,
  duplicateOverrideNotes: "",
  groupChildren: [] as AgendaGroupChildForm[],
});

function formatAmount(value: number, currency: "ARS" | "USD") {
  return new Intl.NumberFormat(currency === "ARS" ? "es-AR" : "en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: currency === "ARS" ? 0 : 2,
  }).format(value || 0);
}

function formatDate(value: string) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "short", year: "numeric" })
    .format(new Date(`${value}T12:00:00`));
}

function localIsoDate(value = new Date()) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function currentWeekendRange() {
  const today = new Date();
  const day = today.getDay();
  const fridayOffset = day === 6 ? -1 : day === 0 ? -2 : (5 - day + 7) % 7;
  const friday = new Date(today);
  friday.setDate(today.getDate() + fridayOffset);
  const sunday = new Date(friday);
  sunday.setDate(friday.getDate() + 2);
  return { start: localIsoDate(friday), end: localIsoDate(sunday) };
}

function statusLabel(value: string) {
  const labels: Record<string, string> = {
    confirmado: "Confirmado",
    cancelado: "Cancelado",
    prospecto: "Prospecto",
    no_aplica: "No aplica",
    programado: "Programado",
    realizado: "Realizado",
    bloqueado: "No trabaja",
    informativo: "Logística",
    sin_sena: "Sin seña",
    no_informada: "Seña no informada",
    sena_parcial: "Seña parcial",
    sena_recibida: "Seña recibida",
    no_iniciada: "Sin liquidar",
    pendiente: "Liquidación pendiente",
    rendida: "Rendida",
    observada: "Observada",
    cerrada: "Cerrada",
  };
  return labels[value] || value;
}

export function BookingDashboard({
  onOpenSettlements,
  onOpenSummary,
  onOpenDetail,
  onOpenCaserio,
  onStartSettlement,
}: BookingDashboardProps) {
  const [section, setSection] = useState<DashboardSection>("overview");
  const [events, setEvents] = useState<BookingAgendaEvent[]>([]);
  const [summary, setSummary] = useState({ total: 0, upcoming: 0, with_deposit: 0, pending_settlement: 0, not_started: 0 });
  const [options, setOptions] = useState<BookingAgendaOption[]>([]);
  const [permissions, setPermissions] = useState<{ individual: PermissionState; shared: PermissionState } | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "ok" | "error"; text: string } | null>(null);
  const [duplicateCandidates, setDuplicateCandidates] = useState<BookingDuplicateCandidate[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("upcoming");
  const [overviewMode, setOverviewMode] = useState<"list" | "calendar">("calendar");
  const [artistToAdd, setArtistToAdd] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<number[]>([]);
  const [editingEventId, setEditingEventId] = useState<number | null>(null);
  const [form, setForm] = useState(initialForm);

  async function loadDashboard() {
    setLoading(true);
    try {
      const [eventsResponse, optionsResponse] = await Promise.all([
        fetch("/api/booking/events?limit=1000", { cache: "no-store" }),
        fetch("/api/booking/events/options", { cache: "no-store" }),
      ]);
      if (!eventsResponse.ok || !optionsResponse.ok) throw new Error("No se pudo cargar Booking.");
      const eventsData = await eventsResponse.json();
      const optionsData = await optionsResponse.json();
      setEvents(eventsData.items || []);
      setSummary(eventsData.summary || summary);
      setOptions(optionsData.artists || []);
      setPermissions(optionsData.permissions || null);
    } catch (error) {
      setMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo cargar Booking." });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  const mode = form.artists.length > 1 ? "shared" : "individual";
  const canCreate = mode === "individual" ? permissions?.individual.create : permissions?.shared.create;
  const canEdit = mode === "individual" ? permissions?.individual.edit : permissions?.shared.edit;
  const canSave = editingEventId ? canEdit : canCreate;
  const selectableArtists = useMemo(() => options.filter((option) => {
    if (form.artists.includes(option.artist)) return false;
    if (form.artists.length === 0) return option.can_individual || option.can_shared;
    return option.can_shared && form.artists.every((artist) => options.find((item) => item.artist === artist)?.can_shared);
  }), [form.artists, options]);

  const topLevelEvents = useMemo(() => events.filter((event) => !event.group_event_id), [events]);
  const childrenByGroup = useMemo(() => {
    const grouped = new Map<number, BookingAgendaEvent[]>();
    events.forEach((event) => {
      if (!event.group_event_id) return;
      const children = grouped.get(event.group_event_id) || [];
      children.push(event);
      grouped.set(event.group_event_id, children);
    });
    grouped.forEach((children) => children.sort((left, right) => (left.group_position || 0) - (right.group_position || 0)));
    return grouped;
  }, [events]);

  const filteredEvents = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("es");
    const today = localIsoDate();
    const weekend = currentWeekendRange();
    return topLevelEvents
      .filter((event) => {
        if (statusFilter === "upcoming" && event.commercial_status === "cancelado") return false;
        if (statusFilter === "upcoming" && event.event_date < today) return false;
        if (statusFilter === "weekend" && (event.event_date < weekend.start || event.event_date > weekend.end || event.commercial_status === "cancelado")) return false;
        if (statusFilter === "pending" && event.event_type !== "show") return false;
        if (statusFilter === "pending" && (event.event_date > today || event.settlement_status === "cerrada" || event.commercial_status === "cancelado")) return false;
        if (statusFilter === "history" && event.event_date >= today) return false;
        if (!query) return true;
        return [
          event.venue,
          event.city,
          event.tour_manager,
          event.seller,
          ...event.artists.map((artist) => artist.artist),
        ].some((value) => String(value || "").toLocaleLowerCase("es").includes(query));
      })
      .sort((left, right) => {
        if (statusFilter === "history") {
          return right.event_date.localeCompare(left.event_date) || right.id - left.id;
        }
        return left.event_date.localeCompare(right.event_date) || left.id - right.id;
      });
  }, [topLevelEvents, search, statusFilter]);

  const upcoming = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return topLevelEvents
      .filter((event) => ["show", "show_group"].includes(event.event_type))
      .filter((event) => event.event_date >= today && event.operational_status === "programado" && event.commercial_status !== "cancelado")
      .sort((left, right) => left.event_date.localeCompare(right.event_date))
      .slice(0, 6);
  }, [topLevelEvents]);

  const calendarEvents = useMemo(
    () => events.filter((event) => event.event_type !== "show_group"),
    [events],
  );

  function addArtist() {
    if (!artistToAdd || form.artists.includes(artistToAdd)) return;
    setForm((current) => ({ ...current, artists: [...current.artists, artistToAdd] }));
    setArtistToAdd("");
  }

  function removeArtist(artist: string) {
    setForm((current) => ({ ...current, artists: current.artists.filter((value) => value !== artist) }));
  }

  function startNewEntry(eventType: AgendaEventType = "show") {
    const next = initialForm();
    next.eventType = eventType;
    if (eventType === "show_group") {
      next.groupChildren = [newGroupChild(next.eventDate), newGroupChild(next.eventDate)];
    }
    setEditingEventId(null);
    setForm(next);
    setDuplicateCandidates([]);
    setMessage(null);
    setSection("new");
  }

  function startEditEvent(event: BookingAgendaEvent) {
    const linked = Boolean(event.booking_show_id || event.composite_event_id || event.caserio_event_id);
    if (linked) {
      if (event.caserio_event_id) onOpenCaserio();
      else onOpenSettlements(event.booking_mode);
      return;
    }
    const children = childrenByGroup.get(event.id) || [];
    setEditingEventId(event.id);
    setForm({
      ...initialForm(),
      eventType: event.event_type,
      eventDate: event.event_date,
      startTime: event.start_time || "",
      venue: event.venue,
      city: event.city || "",
      artists: event.artists.map((artist) => artist.artist),
      cachet: event.contracted_cachet_amount ? String(event.contracted_cachet_amount) : "",
      currency: event.currency,
      fxRate: event.fx_rate ? String(event.fx_rate) : "",
      tourManager: event.tour_manager || "",
      seller: event.seller || "",
      notes: event.notes || "",
      groupChildren: children.map((child) => ({
        id: child.id,
        eventDate: child.event_date,
        startTime: child.start_time || "",
        venue: child.venue,
        city: child.city || "",
        cachet: child.contracted_cachet_amount ? String(child.contracted_cachet_amount) : "",
        notes: child.notes || "",
      })),
    });
    setDuplicateCandidates([]);
    setMessage(null);
    setSection("new");
  }

  function updateGroupChild(index: number, patch: Partial<AgendaGroupChildForm>) {
    setForm((current) => ({
      ...current,
      groupChildren: current.groupChildren.map((child, childIndex) => childIndex === index ? { ...child, ...patch } : child),
    }));
  }

  function removeGroupChild(index: number) {
    setForm((current) => {
      const remaining = current.groupChildren.filter((_, childIndex) => childIndex !== index);
      if (remaining.length === 1) {
        const show = remaining[0];
        return {
          ...current,
          eventType: "show",
          eventDate: show.eventDate,
          startTime: show.startTime,
          venue: show.venue,
          city: show.city,
          cachet: show.cachet,
          notes: show.notes,
          groupChildren: [],
          hasDeposit: false,
        };
      }
      return { ...current, groupChildren: remaining };
    });
    if (form.groupChildren.length === 2) {
      setMessage({ type: "ok", text: "Quedó una sola presentación. Al guardar, el grupo se convertirá en un show." });
    }
  }

  async function submitEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setDuplicateCandidates([]);
    if (!form.artists.length) {
      setMessage({ type: "error", text: "Elegí al menos un artista." });
      return;
    }
    if (form.eventType === "show_group" && form.groupChildren.length < 2) {
      setMessage({ type: "error", text: "Agregá al menos dos shows al grupo." });
      return;
    }
    if (!canSave) {
      setMessage({ type: "error", text: `No tenés permiso para ${editingEventId ? "editar" : "crear"} Booking ${mode === "shared" ? "compartido" : "individual"}.` });
      return;
    }
    setSaving(true);
    const response = await fetch(editingEventId ? `/api/booking/events/${editingEventId}` : "/api/booking/events", {
      method: editingEventId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: form.eventType,
        event_date: form.eventDate,
        start_time: form.startTime || null,
        venue: form.venue,
        city: form.city || null,
        artists: form.artists,
        contracted_cachet_amount: Number(form.cachet || 0),
        currency: form.currency,
        fx_rate: form.fxRate ? Number(form.fxRate) : null,
        tour_manager: form.tourManager || null,
        seller: form.seller || null,
        duplicate_override: form.duplicateOverride,
        duplicate_override_notes: form.duplicateOverrideNotes || null,
        notes: form.notes || null,
        deposit: !editingEventId && form.eventType === "show" && form.hasDeposit ? {
          movement_date: form.depositDate,
          amount: Number(form.depositAmount || 0),
          currency: form.depositCurrency,
          fx_rate: form.depositFxRate ? Number(form.depositFxRate) : null,
          received_by: form.receivedBy,
          received_by_name: form.receivedByName || null,
          payment_method: form.paymentMethod,
          counterparty: form.counterparty || null,
          proof_refs: form.proofRefs.split(/\r?\n/).map((value) => value.trim()).filter(Boolean),
          notes: form.depositNotes || null,
        } : null,
        group_children: form.eventType === "show_group" ? form.groupChildren.map((child) => ({
          id: child.id || null,
          event_date: child.eventDate,
          start_time: child.startTime || null,
          venue: child.venue,
          city: child.city || null,
          contracted_cachet_amount: Number(child.cachet || 0),
          notes: child.notes || null,
        })) : [],
      }),
    });
    const payload = await response.json().catch(() => ({}));
    setSaving(false);
    if (!response.ok) {
      setDuplicateCandidates(Array.isArray(payload.candidates) ? payload.candidates : []);
      setMessage({ type: "error", text: payload.error || "No se pudo guardar el show." });
      return;
    }
    const wasEditing = Boolean(editingEventId);
    setEditingEventId(null);
    setForm(initialForm());
    setDuplicateCandidates([]);
    setMessage({ type: "ok", text: wasEditing ? "Entrada de Agenda actualizada." : form.eventType === "show_group" ? "Grupo de shows creado." : "Entrada de Agenda guardada." });
    setSection("agenda");
    await loadDashboard();
  }

  async function deleteAgendaEvent(event: BookingAgendaEvent) {
    if (!window.confirm(`Eliminar ${event.venue} de la Agenda?`)) return;
    setMessage(null);
    const response = await fetch(`/api/booking/events/${event.id}`, { method: "DELETE" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMessage({ type: "error", text: payload.error || "No se pudo eliminar la entrada." });
      return;
    }
    setMessage({ type: "ok", text: "Entrada eliminada de Agenda." });
    await loadDashboard();
  }

  function renderEventRow(event: BookingAgendaEvent) {
    const linked = Boolean(event.booking_show_id || event.composite_event_id || event.caserio_event_id);
    const isShow = event.event_type === "show";
    const isGroup = event.event_type === "show_group";
    const children = childrenByGroup.get(event.id) || [];
    const expanded = expandedGroups.includes(event.id);
    const canEditEvent = event.booking_mode === "individual" ? permissions?.individual.edit : permissions?.shared.edit;
    const typeLabels: Record<BookingAgendaEvent["event_type"], string> = {
      show: event.booking_mode === "shared" ? "Show compartido" : "Show",
      show_group: `${event.group_count || children.length} shows`,
      availability_block: "No trabaja",
      logistics: "Logística",
      prospect: "Prospecto",
    };
    return (
      <div className={`booking-agenda-entry ${event.event_type}`} key={event.id}>
        <article className="booking-agenda-row">
          <div className="booking-date-tile">
            <strong>{new Date(`${event.event_date}T12:00:00`).getDate()}</strong>
            <span>{new Intl.DateTimeFormat("es-AR", { month: "short" }).format(new Date(`${event.event_date}T12:00:00`))}</span>
          </div>
          <div className="booking-agenda-main">
            <div className="booking-agenda-title">
              <strong>{isShow ? event.artists.map((artist) => artist.artist).join(" + ") : event.venue}</strong>
              <span className={`booking-event-type ${event.event_type}`}>{typeLabels[event.event_type]}</span>
            </div>
            <span>{isShow ? event.venue : event.artists.map((artist) => artist.artist).join(" + ")}{event.city ? ` · ${event.city}` : ""}{event.start_time ? ` · ${event.start_time}` : ""}</span>
            <small>{event.tour_manager ? `Tour manager: ${event.tour_manager}` : isShow ? "Tour manager no informado" : statusLabel(event.operational_status)}</small>
          </div>
          <div className="booking-agenda-money">
            {isShow || isGroup ? (
              <>
                <strong>{event.contracted_cachet_amount > 0 ? formatAmount(event.contracted_cachet_amount, event.currency) : "Caché pendiente"}</strong>
                <span className={`booking-deposit-state ${event.deposit_status}`}>{isGroup ? "Total del grupo" : statusLabel(event.deposit_status)}</span>
              </>
            ) : <span className={`booking-status-chip ${event.commercial_status}`}>{statusLabel(event.commercial_status)}</span>}
          </div>
          <div className="booking-row-actions">
            {canEditEvent && (
              <button type="button" className="booking-row-action" onClick={() => startEditEvent(event)} title={linked ? "Editar en liquidaciones" : "Editar entrada"}>
                <Pencil size={17} />
              </button>
            )}
            {canEditEvent && !linked && !event.group_event_id && (
              <button type="button" className="booking-row-action danger" onClick={() => deleteAgendaEvent(event)} title="Eliminar entrada">
                <Trash2 size={17} />
              </button>
            )}
            {(isShow || isGroup) && (
              <button
                type="button"
                className="booking-row-action"
                onClick={() => {
                  if (isGroup) {
                    setExpandedGroups((current) => current.includes(event.id) ? current.filter((id) => id !== event.id) : [...current, event.id]);
                  } else if (event.caserio_event_id) {
                    onOpenCaserio();
                  } else if (linked) {
                    onOpenSettlements(event.booking_mode);
                  } else {
                    onStartSettlement(event);
                  }
                }}
                title={isGroup ? "Ver shows del grupo" : linked ? "Abrir liquidaciones" : "Iniciar liquidación"}
              >
                {isGroup && expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
              </button>
            )}
          </div>
        </article>
        {isGroup && expanded && (
          <div className="booking-group-children">
            {children.map((child) => renderEventRow(child))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="booking-dashboard-shell">
      <aside className="booking-dashboard-sidebar">
        <div className="booking-dashboard-brand">
          <span>VPO</span>
          <strong>BOOKING</strong>
        </div>
        <nav aria-label="Navegación Booking">
          <button type="button" className={section === "overview" ? "active" : ""} onClick={() => setSection("overview")}><LayoutDashboard size={18} />Inicio</button>
          <button type="button" className={section === "agenda" ? "active" : ""} onClick={() => setSection("agenda")}><CalendarDays size={18} />Agenda</button>
          <button type="button" className={section === "new" ? "active" : ""} onClick={() => startNewEntry()}><CalendarPlus size={18} />Nueva entrada</button>
          <button type="button" onClick={() => onOpenSettlements("individual")}><ClipboardCheck size={18} />Liquidaciones</button>
          <button type="button" onClick={onOpenSummary}><CircleDollarSign size={18} />Resumen</button>
          <button type="button" onClick={onOpenDetail}><ListFilter size={18} />Detalle</button>
        </nav>
        <div className="booking-dashboard-side-note">
          <span>Operación viva</span>
          <strong>Cloud SQL</strong>
        </div>
      </aside>

      <div className="booking-dashboard-stage">
        <header className="booking-dashboard-header">
          <div>
            <span className="booking-eyebrow">VPO Corp · Booking</span>
            <h1>{section === "overview" ? "Centro de booking" : section === "agenda" ? "Agenda de shows" : editingEventId ? "Editar agenda" : "Nueva entrada de agenda"}</h1>
          </div>
          <button type="button" className="booking-primary-action" onClick={() => startNewEntry()}><CalendarPlus size={17} />Nueva entrada</button>
        </header>

        {message && <div className={`booking-dashboard-message ${message.type}`}>{message.text}</div>}

        {section === "overview" && (
          <div className="booking-overview">
            <div className="booking-kpi-grid">
              <div><span>Shows cargados</span><strong>{summary.total}</strong><small>agenda operativa</small></div>
              <div><span>Próximos</span><strong>{summary.upcoming}</strong><small>confirmados</small></div>
              <div><span>Con seña</span><strong>{summary.with_deposit}</strong><small>caja registrada</small></div>
              <div><span>Sin liquidar</span><strong>{summary.not_started}</strong><small>requieren seguimiento</small></div>
            </div>
            <div className="booking-overview-toolbar">
              <div>
                <span>Agenda</span>
                <h2>{overviewMode === "calendar" ? "Calendario de artistas" : "Próximos shows"}</h2>
              </div>
              <div className="booking-view-switch" role="tablist" aria-label="Vista de agenda">
                <button type="button" role="tab" aria-selected={overviewMode === "list"} className={overviewMode === "list" ? "active" : ""} onClick={() => setOverviewMode("list")}><ListFilter size={16} />Lista</button>
                <button type="button" role="tab" aria-selected={overviewMode === "calendar"} className={overviewMode === "calendar" ? "active" : ""} onClick={() => setOverviewMode("calendar")}><CalendarDays size={16} />Calendario</button>
              </div>
            </div>
            {loading && <p className="booking-empty">Cargando agenda...</p>}
            {!loading && overviewMode === "calendar" && <BookingCalendar events={calendarEvents} onOpenEvent={startEditEvent} />}
            {!loading && overviewMode === "list" && (
              <div className="booking-dashboard-columns booking-list-overview">
                <section className="booking-upcoming-block">
                  {!upcoming.length && <p className="booking-empty">No hay próximos shows cargados.</p>}
                  <div className="booking-agenda-list">{upcoming.map(renderEventRow)}</div>
                </section>
                <aside className="booking-quick-panel">
                  <span>Acciones rápidas</span>
                  <button type="button" onClick={() => startNewEntry()}><CalendarPlus size={20} /><div><strong>Cargar agenda</strong><small>Show, grupo o bloqueo</small></div><ChevronRight size={17} /></button>
                  <button type="button" onClick={() => onOpenSettlements("individual")}><ClipboardCheck size={20} /><div><strong>Liquidar</strong><small>Individual o compartido</small></div><ChevronRight size={17} /></button>
                  <button type="button" onClick={onOpenSummary}><CircleDollarSign size={20} /><div><strong>Ver resultados</strong><small>Ingresos y comisiones</small></div><ChevronRight size={17} /></button>
                </aside>
              </div>
            )}
          </div>
        )}

        {section === "agenda" && (
          <section className="booking-dashboard-block booking-agenda-page">
            <div className="booking-agenda-toolbar">
              <label><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar artista, lugar, ciudad o responsable" /></label>
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="upcoming">Próximos</option>
                <option value="weekend">Este fin de semana</option>
                <option value="pending">Pendientes de cierre</option>
                <option value="history">Historial</option>
                <option value="all">Toda la agenda</option>
              </select>
            </div>
            {loading && <p className="booking-empty">Cargando agenda...</p>}
            {!loading && filteredEvents.length === 0 && <p className="booking-empty">No hay shows para este filtro.</p>}
            <div className="booking-agenda-list">{filteredEvents.map(renderEventRow)}</div>
          </section>
        )}

        {section === "new" && (
          <form className="booking-new-form" onSubmit={submitEvent}>
            <section className="booking-dashboard-block">
              <div className="booking-form-section-title"><span>1</span><div><h2>Qué querés agendar</h2><p>La pantalla muestra solamente los campos necesarios.</p></div></div>
              <div className="booking-entry-type-picker">
                <button type="button" className={form.eventType === "show" ? "active" : ""} onClick={() => setForm((current) => ({ ...current, eventType: "show", groupChildren: [], hasDeposit: current.hasDeposit }))}>Un show</button>
                <button type="button" className={form.eventType === "show_group" ? "active" : ""} onClick={() => setForm((current) => ({
                  ...current,
                  eventType: "show_group",
                  hasDeposit: false,
                  groupChildren: current.groupChildren.length >= 2 ? current.groupChildren : [
                    {
                      eventDate: current.eventDate,
                      startTime: current.startTime,
                      venue: current.venue,
                      city: current.city,
                      cachet: current.cachet,
                      notes: current.notes,
                    },
                    newGroupChild(current.eventDate),
                  ],
                }))}>Varios shows</button>
                <button type="button" className={form.eventType === "availability_block" ? "active" : ""} onClick={() => setForm((current) => ({ ...current, eventType: "availability_block", groupChildren: [], hasDeposit: false }))}>No trabaja</button>
                <button type="button" className={form.eventType === "logistics" ? "active" : ""} onClick={() => setForm((current) => ({ ...current, eventType: "logistics", groupChildren: [], hasDeposit: false }))}>Logística</button>
                <button type="button" className={form.eventType === "prospect" ? "active" : ""} onClick={() => setForm((current) => ({ ...current, eventType: "prospect", groupChildren: [], hasDeposit: false }))}>Prospecto</button>
              </div>
            </section>
            <section className="booking-dashboard-block">
              <div className="booking-form-section-title"><span>2</span><div><h2>{form.eventType === "show_group" ? "Nombre del grupo" : "Cuándo y dónde"}</h2><p>{form.eventType === "show_group" ? "Ejemplo: Teodolina las 2. Los shows se detallan más abajo." : "Los datos mínimos para ubicar la entrada."}</p></div></div>
              <div className="booking-form-grid four">
                {form.eventType !== "show_group" && <label>Fecha<input type="date" value={form.eventDate} onChange={(event) => setForm((current) => ({ ...current, eventDate: event.target.value, depositDate: current.depositDate || event.target.value }))} required /></label>}
                {form.eventType !== "show_group" && <label>Hora<input type="time" value={form.startTime} onChange={(event) => setForm((current) => ({ ...current, startTime: event.target.value }))} /></label>}
                <label>{form.eventType === "show_group" ? "Nombre del grupo" : form.eventType === "availability_block" ? "Motivo" : form.eventType === "logistics" ? "Vuelo / traslado" : "Lugar / evento"}<input value={form.venue} onChange={(event) => setForm((current) => ({ ...current, venue: event.target.value }))} required placeholder={form.eventType === "show_group" ? "Ej. Teodolina las 2" : "Nombre breve"} /></label>
                {form.eventType !== "show_group" && <label>Ciudad<input value={form.city} onChange={(event) => setForm((current) => ({ ...current, city: event.target.value }))} placeholder="Opcional" /></label>}
              </div>
            </section>

            <section className="booking-dashboard-block">
              <div className="booking-form-section-title"><span>3</span><div><h2>Artista</h2><p>La selección respeta los permisos del usuario.</p></div></div>
              <div className="booking-artist-picker">
                <select value={artistToAdd} onChange={(event) => setArtistToAdd(event.target.value)}>
                  <option value="">Elegir artista</option>
                  {selectableArtists.map((option) => <option key={option.id} value={option.artist}>{option.artist}</option>)}
                </select>
                <button type="button" onClick={addArtist} disabled={!artistToAdd}>Agregar</button>
              </div>
              <div className="booking-selected-artists">
                {form.artists.map((artist) => <button type="button" key={artist} onClick={() => removeArtist(artist)}>{artist}<span>×</span></button>)}
                {!form.artists.length && <span className="booking-empty-inline">Todavía no elegiste artistas.</span>}
              </div>
              {form.artists.length > 0 && <div className="booking-mode-result"><Users size={17} /><strong>{mode === "individual" ? "Booking individual" : "Booking compartido"}</strong><span>{mode === "individual" ? "1 artista" : `${form.artists.length} artistas`}</span></div>}
            </section>

            {form.eventType === "show_group" && (
              <section className="booking-dashboard-block">
                <div className="booking-form-section-title"><span>4</span><div><h2>Shows del grupo</h2><p>Cada uno podrá liquidarse de manera independiente.</p></div></div>
                <div className="booking-group-editor">
                  {form.groupChildren.map((child, index) => (
                    <article key={child.id || `new-${index}`}>
                      <div className="booking-group-editor-heading">
                        <strong>Show {index + 1}</strong>
                        {form.groupChildren.length > 1 && <button type="button" onClick={() => removeGroupChild(index)} title="Quitar show"><Trash2 size={16} /></button>}
                      </div>
                      <div className="booking-form-grid four">
                        <label>Fecha<input type="date" value={child.eventDate} onChange={(event) => updateGroupChild(index, { eventDate: event.target.value })} required /></label>
                        <label>Hora<input type="time" value={child.startTime} onChange={(event) => updateGroupChild(index, { startTime: event.target.value })} /></label>
                        <label>Lugar<input value={child.venue} onChange={(event) => updateGroupChild(index, { venue: event.target.value })} required placeholder="Venue" /></label>
                        <label>Ciudad<input value={child.city} onChange={(event) => updateGroupChild(index, { city: event.target.value })} placeholder="Opcional" /></label>
                        <label>Caché<input inputMode="decimal" value={child.cachet} onChange={(event) => updateGroupChild(index, { cachet: event.target.value })} placeholder="0" /></label>
                      </div>
                    </article>
                  ))}
                  <button type="button" className="booking-add-group-child" onClick={() => setForm((current) => ({ ...current, groupChildren: [...current.groupChildren, newGroupChild(current.groupChildren.at(-1)?.eventDate || current.eventDate)] }))}><Plus size={17} />Agregar otro show</button>
                  <div className="booking-group-total"><span>Total del grupo</span><strong>{formatAmount(form.groupChildren.reduce((total, child) => total + Number(child.cachet || 0), 0), form.currency)}</strong></div>
                </div>
              </section>
            )}

            {(form.eventType === "show" || form.eventType === "show_group") && <section className="booking-dashboard-block">
              <div className="booking-form-section-title"><span>{form.eventType === "show_group" ? "5" : "4"}</span><div><h2>Condiciones comerciales</h2><p>Podés completar solo lo confirmado hoy.</p></div></div>
              <div className="booking-form-grid four">
                {form.eventType === "show" && <label>Caché pactado<input inputMode="decimal" value={form.cachet} onChange={(event) => setForm((current) => ({ ...current, cachet: event.target.value }))} placeholder="0" /></label>}
                <label>Moneda<select value={form.currency} onChange={(event) => setForm((current) => ({ ...current, currency: event.target.value as "ARS" | "USD", depositCurrency: event.target.value as "ARS" | "USD" }))}><option value="ARS">ARS</option><option value="USD">USD</option></select></label>
                {form.currency === "USD" && <label>Tipo de cambio<input inputMode="decimal" value={form.fxRate} onChange={(event) => setForm((current) => ({ ...current, fxRate: event.target.value }))} required /></label>}
                <label>Tour manager<input value={form.tourManager} onChange={(event) => setForm((current) => ({ ...current, tourManager: event.target.value }))} placeholder="Opcional" /></label>
                <label>Vendedor<input value={form.seller} onChange={(event) => setForm((current) => ({ ...current, seller: event.target.value }))} placeholder="Opcional" /></label>
              </div>
              {form.eventType === "show" && !editingEventId && <label className="booking-toggle-line"><input type="checkbox" checked={form.hasDeposit} onChange={(event) => setForm((current) => ({ ...current, hasDeposit: event.target.checked, depositDate: current.eventDate }))} /><span>Ya recibimos una seña</span></label>}
              {form.hasDeposit && (
                <div className="booking-deposit-panel">
                  <div className="booking-form-grid four">
                    <label>Fecha de seña<input type="date" value={form.depositDate} onChange={(event) => setForm((current) => ({ ...current, depositDate: event.target.value }))} required /></label>
                    <label>Importe<input inputMode="decimal" value={form.depositAmount} onChange={(event) => setForm((current) => ({ ...current, depositAmount: event.target.value }))} required /></label>
                    <label>Moneda<select value={form.depositCurrency} onChange={(event) => setForm((current) => ({ ...current, depositCurrency: event.target.value as "ARS" | "USD" }))}><option value="ARS">ARS</option><option value="USD">USD</option></select></label>
                    {form.depositCurrency === "USD" && <label>Tipo de cambio<input inputMode="decimal" value={form.depositFxRate} onChange={(event) => setForm((current) => ({ ...current, depositFxRate: event.target.value }))} required /></label>}
                    <label>Quién la recibió<select value={form.receivedBy} onChange={(event) => setForm((current) => ({ ...current, receivedBy: event.target.value as typeof current.receivedBy }))}><option value="indyana">Indyana</option><option value="artista">Artista</option><option value="empleado">Empleado</option><option value="tercero">Tercero</option></select></label>
                    {(form.receivedBy === "empleado" || form.receivedBy === "tercero") && <label>Nombre<input value={form.receivedByName} onChange={(event) => setForm((current) => ({ ...current, receivedByName: event.target.value }))} required /></label>}
                    <label>Medio<select value={form.paymentMethod} onChange={(event) => setForm((current) => ({ ...current, paymentMethod: event.target.value as typeof current.paymentMethod }))}><option value="transferencia">Transferencia</option><option value="efectivo">Efectivo</option><option value="otro">Otro</option></select></label>
                    <label>Quién entregó<input value={form.counterparty} onChange={(event) => setForm((current) => ({ ...current, counterparty: event.target.value }))} placeholder="Cliente o venue" /></label>
                  </div>
                  <label>Comprobante<textarea value={form.proofRefs} onChange={(event) => setForm((current) => ({ ...current, proofRefs: event.target.value }))} placeholder="Link, uno por línea" /></label>
                </div>
              )}
              <label>Notas<textarea value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} placeholder="Información útil para el equipo" /></label>
            </section>}

            {form.eventType !== "show" && form.eventType !== "show_group" && (
              <section className="booking-dashboard-block">
                <div className="booking-form-section-title"><span>4</span><div><h2>Detalle</h2><p>Información breve para que el equipo entienda la entrada.</p></div></div>
                <div className="booking-form-grid four">
                  <label>Responsable<input value={form.tourManager} onChange={(event) => setForm((current) => ({ ...current, tourManager: event.target.value }))} placeholder="Opcional" /></label>
                </div>
                <label>Notas<textarea value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} placeholder="Información útil para el equipo" /></label>
              </section>
            )}

            {duplicateCandidates.length > 0 && (
              <section className="booking-duplicate-list" aria-label="Shows encontrados">
                <strong>Ya encontramos un show con estos datos</strong>
                {duplicateCandidates.map((candidate) => (
                  <div key={`${candidate.source}-${candidate.id}`}>
                    <span>{formatDate(candidate.date)} · {candidate.artists.join(" + ")} · {candidate.venue}{candidate.city ? `, ${candidate.city}` : ""}</span>
                    <button
                      type="button"
                      onClick={() => {
                        if (candidate.source === "agenda") {
                          setSearch(candidate.venue || candidate.artists[0] || "");
                          setStatusFilter("all");
                          setSection("agenda");
                        } else {
                          onOpenSettlements(candidate.source === "booking_compartido" ? "shared" : "individual");
                        }
                      }}
                    >
                      {candidate.source === "agenda" ? "Ver en agenda" : "Abrir liquidaciones"}
                    </button>
                  </div>
                ))}
              </section>
            )}

            {message?.type === "error" && message.text.toLocaleLowerCase("es").includes("duplicado") && (
              <section className="booking-duplicate-confirm">
                <label><input type="checkbox" checked={form.duplicateOverride} onChange={(event) => setForm((current) => ({ ...current, duplicateOverride: event.target.checked }))} />Confirmo que es otro show</label>
                {form.duplicateOverride && <textarea value={form.duplicateOverrideNotes} onChange={(event) => setForm((current) => ({ ...current, duplicateOverrideNotes: event.target.value }))} placeholder="Explicá brevemente la diferencia" required />}
              </section>
            )}

            <div className="booking-form-actions">
              <button type="button" onClick={() => { setEditingEventId(null); setForm(initialForm()); setSection("agenda"); }}>Cancelar</button>
              <button type="submit" className="booking-primary-action" disabled={saving || !canSave}>{saving ? "Guardando..." : editingEventId ? "Guardar cambios" : form.eventType === "show_group" ? "Crear grupo" : "Guardar en agenda"}</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
