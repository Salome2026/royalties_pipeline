"use client";

import { useMemo, useState } from "react";
import { addDays, addMonths, format, isSameMonth, startOfMonth, startOfWeek, subMonths } from "date-fns";
import { es } from "date-fns/locale";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import type { BookingAgendaEvent } from "./BookingDashboard";

type BookingCalendarProps = {
  events: BookingAgendaEvent[];
  onOpenEvent: (event: BookingAgendaEvent) => void;
};

const DAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

function isoDate(value: Date) {
  return format(value, "yyyy-MM-dd");
}

function artistLabel(event: BookingAgendaEvent) {
  return event.artists.map((artist) => artist.artist).join(" + ") || "Artista sin informar";
}

function eventTone(event: BookingAgendaEvent) {
  if (event.event_type === "availability_block") return "unavailable";
  if (event.event_type === "logistics") return "logistics";
  if (event.event_type === "prospect") return "prospect";
  if (event.booking_mode === "shared") return "shared";
  return "show";
}

export function BookingCalendar({ events, onOpenEvent }: BookingCalendarProps) {
  const today = isoDate(new Date());
  const [visibleMonth, setVisibleMonth] = useState(() => startOfMonth(new Date()));
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const eventsByDate = useMemo(() => {
    const grouped = new Map<string, BookingAgendaEvent[]>();
    events.forEach((event) => {
      const dayEvents = grouped.get(event.event_date) || [];
      dayEvents.push(event);
      grouped.set(event.event_date, dayEvents);
    });
    grouped.forEach((dayEvents) => dayEvents.sort((left, right) => {
      const timeOrder = String(left.start_time || "99:99").localeCompare(String(right.start_time || "99:99"));
      return timeOrder || left.id - right.id;
    }));
    return grouped;
  }, [events]);

  const calendarDays = useMemo(() => {
    const first = startOfWeek(startOfMonth(visibleMonth), { weekStartsOn: 1 });
    return Array.from({ length: 42 }, (_, index) => addDays(first, index));
  }, [visibleMonth]);

  const selectedEvents = selectedDate ? eventsByDate.get(selectedDate) || [] : [];
  const upcomingEvents = useMemo(() => events
    .filter((event) => event.event_date >= today && event.commercial_status !== "cancelado")
    .sort((left, right) => left.event_date.localeCompare(right.event_date) || left.id - right.id)
    .slice(0, 6), [events, today]);
  const sideEvents = selectedDate ? selectedEvents : upcomingEvents;

  function selectMonth(month: Date) {
    setVisibleMonth(startOfMonth(month));
    setSelectedDate(null);
  }

  return (
    <div className="booking-calendar-layout">
      <section className="booking-calendar-surface" aria-label="Calendario mensual de Booking">
        <header className="booking-calendar-header">
          <button type="button" onClick={() => selectMonth(subMonths(visibleMonth, 1))} title="Mes anterior"><ChevronLeft size={19} /></button>
          <div>
            <span>Agenda mensual</span>
            <h2>{format(visibleMonth, "MMMM yyyy", { locale: es })}</h2>
          </div>
          <div className="booking-calendar-navigation">
            <button type="button" className="booking-calendar-today" onClick={() => selectMonth(new Date())}>Hoy</button>
            <button type="button" onClick={() => selectMonth(addMonths(visibleMonth, 1))} title="Mes siguiente"><ChevronRight size={19} /></button>
          </div>
        </header>

        <div className="booking-calendar-weekdays" aria-hidden="true">
          {DAY_NAMES.map((day) => <span key={day}>{day}</span>)}
        </div>

        <div className="booking-calendar-grid">
          {calendarDays.map((day) => {
            const dateKey = isoDate(day);
            const dayEvents = eventsByDate.get(dateKey) || [];
            const artistGroups = Array.from(dayEvents.reduce((grouped, event) => {
              const label = artistLabel(event);
              const current = grouped.get(label) || [];
              current.push(event);
              grouped.set(label, current);
              return grouped;
            }, new Map<string, BookingAgendaEvent[]>()));
            const visibleArtists = artistGroups.slice(0, 3);
            const hiddenArtists = Math.max(0, artistGroups.length - visibleArtists.length);
            const outsideMonth = !isSameMonth(day, visibleMonth);
            return (
              <button
                type="button"
                key={dateKey}
                className={`booking-calendar-day ${outsideMonth ? "outside" : ""} ${dateKey === today ? "today" : ""} ${dateKey === selectedDate ? "selected" : ""}`}
                onClick={() => setSelectedDate(dateKey)}
              >
                <span className="booking-calendar-day-number">{format(day, "d")}</span>
                <span className="booking-calendar-artists">
                  {visibleArtists.map(([label, groupedEvents]) => (
                    <span className={`booking-calendar-artist ${eventTone(groupedEvents[0])}`} key={`${dateKey}-${label}`} title={label}>
                      <i aria-hidden="true" />
                      <b>{label}</b>
                      {groupedEvents.length > 1 && <em>×{groupedEvents.length}</em>}
                    </span>
                  ))}
                  {hiddenArtists > 0 && <span className="booking-calendar-more">+{hiddenArtists} más</span>}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      <aside className="booking-calendar-side">
        <div className="booking-calendar-side-heading">
          <CalendarDays size={18} />
          <div>
            <span>{selectedDate ? "Agenda del día" : "Próximos"}</span>
            <strong>{selectedDate ? format(new Date(`${selectedDate}T12:00:00`), "d 'de' MMMM", { locale: es }) : "Shows y movimientos"}</strong>
          </div>
        </div>
        <div className="booking-calendar-side-list">
          {sideEvents.map((event) => (
            <button type="button" key={event.id} onClick={() => onOpenEvent(event)}>
              <span className={`booking-calendar-side-date ${eventTone(event)}`}>{format(new Date(`${event.event_date}T12:00:00`), "dd MMM", { locale: es })}</span>
              <strong>{artistLabel(event)}</strong>
              <ChevronRight size={16} />
            </button>
          ))}
          {!sideEvents.length && <p>No hay artistas agendados para esta fecha.</p>}
        </div>
        {selectedDate && <button type="button" className="booking-calendar-clear" onClick={() => setSelectedDate(null)}>Ver próximos</button>}
      </aside>
    </div>
  );
}
