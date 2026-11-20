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
}

export function bordaCount(rankings: string[][]): Record<string, number> {
  const scores: Record<string, number> = {};
  for (const ranking of rankings) {
    ranking.forEach((candidate, position) => {
      scores[candidate] = (scores[candidate] ?? 0) + (ranking.length - 1 - position);
    });
  }
  return scores;
}

/** Mufakat = usulan teratas didukung >= 2/3 peserta dengan approve DAN
 *  tidak ada kritik blocking yang belum dijawab. */
export function decideConsensus(votes: Vote[], critiques: Critique[]): {
  decision: 'mufakat' | 'belum_mufakat' | 'tie';
  approveRatio: number;
  blocking: number;
  borda: Record<string, number>;
  winner: string | null;
} {
  const total = votes.length;
  const approves = votes.filter((v) => v.decision === 'approve').length;
  const approveRatio = total ? approves / total : 0;
  const blocking = critiques.filter((c) => c.severity === 'blocking').length;
  const borda = bordaCount(votes.map((v) => v.ranking));
  let winner: string | null = null;
  let decision: 'mufakat' | 'belum_mufakat' | 'tie' = 'belum_mufakat';
  const entries = Object.entries(borda);
  if (entries.length) {
    const top = Math.max(...entries.map(([, score]) => score));
    const leaders = entries.filter(([, score]) => score === top).map(([name]) => name);
    if (leaders.length > 1) {
      decision = 'tie';
    } else {
      winner = leaders[0];
      decision = approveRatio >= 2 / 3 && blocking === 0 ? 'mufakat' : 'belum_mufakat';
    }
  }
  return { decision, approveRatio, blocking, borda, winner };
}

/** Anonimisasi: acak urutan usulan, beri label A/B/C, sembunyikan nama AI. */
export function anonymize<T extends { agentId: string }>(proposals: T[], seed = 0): { items: Array<Omit<T, 'agentId'> & { label: string }>; mapping: Record<string, string> } {
  const shuffled = [...proposals];
  let s = seed || 1;
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
