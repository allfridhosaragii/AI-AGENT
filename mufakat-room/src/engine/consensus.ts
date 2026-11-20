// MUFAKAT Room — Konsensus (Claude §2.1, §T3).
// Anonimisasi label acak, Borda count, aturan >= 2/3 + blocking,
// pemilihan moderator (keluarga minoritas), deteksi kemiripan > 0,9
// -> devil's advocate. Porting pola dari mufakat.consensus (Python).
export type Severity = 'info' | 'minor' | 'major' | 'blocking';
export type VoteDecision = 'approve' | 'revise' | 'reject';

export interface Vote {
  agentId: string;
  decision: VoteDecision;
  ranking: string[];
}

export interface Critique {
  severity: Severity;
  text: string;
  /** M7: kritik blocking yang sudah dijawab/diatasi tidak lagi
   *  menghalangi mufakat. Tanpa ini mufakat mustahil setelah satu
   *  kritik blocking pernah muncul. */
  resolved?: boolean;
}

export function bordaCount(rankings: string[][]): Record<string, number> {
  const scores: Record<string, number> = {};
  for (const ranking of rankings) {
    // T4: satu ranking malformed (bukan array / berisi non-string) tidak
    // boleh merusak seluruh rapat — lewati ranking itu.
    if (!Array.isArray(ranking)) continue;
    ranking.forEach((candidate, position) => {
      if (typeof candidate !== 'string') return;
      scores[candidate] = (scores[candidate] ?? 0) + (ranking.length - 1 - position);
    });
  }
  return scores;
}

/** Vote hanya valid bila `ranking`-nya array string; vote malformed
 *  (mis. tanpa ranking, atau ranking berupa string) dilewati, bukan crash. */
function validVotes(votes: Vote[]): Vote[] {
  return (votes ?? []).filter(
    (v) => v && Array.isArray(v.ranking) && v.ranking.every((c) => typeof c === 'string'),
  );
}

/** Mufakat = usulan pemenang Borda didukung >= 2/3 peserta dengan approve
 *  DAN tidak ada kritik blocking yang BELUM dijawab (resolved=true tidak
 *  dihitung). approveRatio terikat ke pemenang: hanya vote 'approve' yang
 *  menaruh pemenang di peringkat pertama yang dihitung (M7). */
export function decideConsensus(votes: Vote[], critiques: Critique[]): {
  decision: 'mufakat' | 'belum_mufakat' | 'tie';
  approveRatio: number;
  blocking: number;
  borda: Record<string, number>;
  winner: string | null;
  winnerApprovals: number;
} {
  // T4: hitung hanya dari vote valid; vote malformed dilewati.
  const counted = validVotes(votes);
  const total = counted.length;
  // M7: hanya kritik blocking yang belum resolved yang menghalangi.
  const blocking = (critiques ?? []).filter((c) => c.severity === 'blocking' && !c.resolved).length;
  const borda = bordaCount(counted.map((v) => v.ranking));
  let winner: string | null = null;
  let decision: 'mufakat' | 'belum_mufakat' | 'tie' = 'belum_mufakat';
  let winnerApprovals = 0;
  let approveRatio = 0;
  const entries = Object.entries(borda);
  if (entries.length) {
    const top = Math.max(...entries.map(([, score]) => score));
    const leaders = entries.filter(([, score]) => score === top).map(([name]) => name);
    if (leaders.length > 1) {
      decision = 'tie';
    } else {
      winner = leaders[0];
      // M7: approveRatio terikat ke pemenang — approve yang ranking[0]-nya
      // BUKAN pemenang tidak menaikkan rasio pemenang.
      winnerApprovals = counted.filter((v) => v.decision === 'approve' && v.ranking[0] === winner).length;
      approveRatio = total ? winnerApprovals / total : 0;
      decision = approveRatio >= 2 / 3 && blocking === 0 ? 'mufakat' : 'belum_mufakat';
    }
  }
  return { decision, approveRatio, blocking, borda, winner, winnerApprovals };
}

/** Anonimisasi: acak urutan usulan, beri label A/B/C, sembunyikan nama AI.
 *  M6: bila seed TIDAK diberikan, seed diambil dari crypto.getRandomValues
 *  per panggilan (per ronde) — label A/B/C tidak lagi bisa ditebak
 *  (sebelumnya seed default deterministik selalu A=gemini, B=chatgpt,
 *  C=claude). Seed eksplisit tetap didukung agar hasil bisa direproduksi
 *  di test. */
export function anonymize<T extends { agentId: string }>(proposals: T[], seed?: number): { items: Array<Omit<T, 'agentId'> & { label: string }>; mapping: Record<string, string> } {
  const shuffled = [...proposals];
  let s: number;
  if (seed === undefined) {
    // Seed acak per ronde dari crypto; fallback ke waktu + Math.random
    // bila crypto tidak tersedia (bukan default deterministik).
    const buf = new Uint32Array(1);
    if (typeof globalThis.crypto?.getRandomValues === 'function') {
      globalThis.crypto.getRandomValues(buf);
      s = buf[0] || 1;
    } else {
      s = (Date.now() % 2 ** 31) + Math.floor(Math.random() * 2 ** 31) || 1;
    }
  } else {
    s = seed || 1;
  }
  const rand = () => (s = (s * 1103515245 + 12345) % 2 ** 31) / 2 ** 31;
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  const mapping: Record<string, string> = {};
  const items = shuffled.map((proposal, index) => {
    const label = String.fromCharCode(65 + index);
    mapping[label] = proposal.agentId;
    const { agentId: _agentId, ...rest } = proposal;
    return { ...rest, label };
  });
  return { items, mapping };
}

/** Kemiripan teks sederhana (Jaccard atas kata) untuk deteksi sepakat palsu. */
export function textSimilarity(a: string, b: string): number {
  const wordsA = new Set(a.toLowerCase().split(/\W+/).filter(Boolean));
  const wordsB = new Set(b.toLowerCase().split(/\W+/).filter(Boolean));
  const intersection = [...wordsA].filter((w) => wordsB.has(w)).length;
  const union = new Set([...wordsA, ...wordsB]).size;
  return union === 0 ? 1 : intersection / union;
}

export function detectFalseConsensus(texts: string[]): boolean {
  if (texts.length < 2) return false;
  for (let i = 0; i < texts.length; i++) {
    for (let j = i + 1; j < texts.length; j++) {
      if (textSimilarity(texts[i], texts[j]) <= 0.9) return false;
    }
  }
  return true;
}
