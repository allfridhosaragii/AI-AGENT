// MUFAKAT Room — Tabel voting Borda (UI).
import React from 'react';

export interface VoteRow {
  label: string;
  decision: string;
  ranking: string[];
}

export default function VoteTable({ votes, borda }: { votes: VoteRow[]; borda: Record<string, number> }): React.ReactElement {
  return (
    <table>
      <thead>
        <tr>
          <th>Usulan</th>
          <th>Vote</th>
          <th>Ranking</th>
          <th>Skor Borda</th>
        </tr>
      </thead>
      <tbody>
        {votes.map((vote, index) => (
          <tr key={index}>
            <td>{vote.label}</td>
            <td>{vote.decision}</td>
            <td>{vote.ranking.join(' > ')}</td>
            <td>{borda[vote.label] ?? 0}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
