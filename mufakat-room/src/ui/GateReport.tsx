// MUFAKAT Room — Laporan gate dari Local Runner (UI).
import React from 'react';

export interface GateRow {
  tool: string;
  passed: boolean;
  findings: Array<{ severity: string; file: string; line: number; rule: string; msg: string }>;
}

export default function GateReport({ verdict, gates }: { verdict: string; gates: GateRow[] }): React.ReactElement {
  return (
    <div>
      <h3>Verdict gates: {verdict}</h3>
      <ul>
        {gates.map((gate) => (
          <li key={gate.tool}>
            {gate.tool}: {gate.passed ? 'lulus' : 'gagal'} ({gate.findings.length} temuan)
          </li>
        ))}
      </ul>
      <p>
        <em>
          Kebenaran ditentukan tool deterministik (test &amp; audit), bukan suara AI.
          Commit/push hanya setelah pengguna menekan Approve.
        </em>
      </p>
    </div>
  );
}
