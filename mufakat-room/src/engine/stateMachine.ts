// MUFAKAT Room — State machine debat -> kode -> audit (Claude §2, §T6).
// Implementasi ringan tanpa XState runtime di sini (transisi tervalidasi +
// batas ronde/iterasi); peta state sama dengan mufakat.room.state_machine (Python).
export const MAX_DEBATE_ROUNDS = 3;
export const MAX_FIX_ITERATIONS = 5;
export const MAX_TOTAL_ITERATIONS = 12;

export type DebateState =
  | 'ide'
  | 'usulan_r1'
  | 'kritik_silang'
  | 'rapat'
  | 'debat_ulang'
  | 'spesifikasi'
  | 'approve_spek'
  | 'coding'
  | 'review_silang'
  | 'terapkan_patch'
  | 'gates'
  | 'revisi'
  | 'audit_final'
  | 'approve_commit'
  | 'eskalasi'
  | 'selesai';

const TRANSITIONS: Record<string, [DebateState, DebateState]> = {
  kirim_ide: ['ide', 'usulan_r1'],
  usulan_diterima: ['usulan_r1', 'kritik_silang'],
  kritik_diterima: ['kritik_silang', 'rapat'],
  belum_mufakat: ['rapat', 'debat_ulang'],
  debat_lanjut: ['debat_ulang', 'kritik_silang'],
  mufakat_atau_juri: ['rapat', 'spesifikasi'],
  spek_selesai: ['spesifikasi', 'approve_spek'],
  spek_revisi: ['approve_spek', 'spesifikasi'],
  spek_disetujui: ['approve_spek', 'coding'],
  kode_selesai: ['coding', 'review_silang'],
  review_selesai: ['review_silang', 'terapkan_patch'],
  patch_disetujui: ['terapkan_patch', 'gates'],
  gate_gagal: ['gates', 'revisi'],
  gate_lulus: ['gates', 'audit_final'],
  gate_eskalasi: ['gates', 'eskalasi'],
  revisi_selesai: ['revisi', 'review_silang'],
  audit_bersih: ['audit_final', 'approve_commit'],
  audit_temuan: ['audit_final', 'revisi'],
  commit_disetujui: ['approve_commit', 'selesai'],
  eskalasi_selesai: ['eskalasi', 'selesai'],
};

export interface DebateMachine {
  getState(): DebateState;
  transition(event: string): DebateState;
  isTerminal(): boolean;
}

export function createDebateMachine(): DebateMachine {
  let state: DebateState = 'ide';
  let debateRound = 0;
  let fixIterations = 0;
  let totalIterations = 0;
  return {
    getState: () => state,
    transition(event: string): DebateState {
      const edge = TRANSITIONS[event];
      if (!edge) throw new Error(`Event tidak dikenal: ${event}`);
      const [from, to] = edge;
      if (state !== from) {
        throw new Error(`Event ${event} tidak valid dari state ${state} (harus dari ${from}).`);
      }
      if (event === 'debat_lanjut') {
        debateRound += 1;
        if (debateRound >= MAX_DEBATE_ROUNDS) {
          state = 'eskalasi';
          return state;
        }
      }
      if (event === 'revisi_selesai') {
        fixIterations += 1;
        totalIterations += 1;
        if (fixIterations >= MAX_FIX_ITERATIONS || totalIterations >= MAX_TOTAL_ITERATIONS) {
          state = 'eskalasi';
          return state;
        }
      }
      if (event === 'kirim_ide') debateRound = 1;
      state = to;
      return state;
    },
    isTerminal: () => state === 'selesai' || state === 'eskalasi',
  };
}
