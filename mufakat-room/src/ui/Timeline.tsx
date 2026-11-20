// MUFAKAT Room — Timeline ronde (UI).
import React from 'react';

export interface TimelineEvent {
  round: number;
  phase: string;
  text: string;
}

export default function Timeline({ events }: { events: TimelineEvent[] }): React.ReactElement {
  return (
    <ol>
      {events.map((event, index) => (
        <li key={index}>
          <strong>Ronde {event.round} — {event.phase}:</strong> {event.text}
        </li>
      ))}
      {events.length === 0 && <li>Belum ada ronde. Mulai dari ide di atas.</li>}
    </ol>
  );
}
