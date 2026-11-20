// MUFAKAT Room — State machine debat -> kode -> audit (Claude §2, §T6).
// Implementasi ringan tanpa XState runtime di sini (transisi tervalidasi +
// batas ronde/iterasi); peta state sama dengan mufakat.room.state_machine (Python).
// M4: ronde 3 tanpa mufakat -> 'spesifikasi' DENGAN dissent (juri memutus),
// bukan 'eskalasi' setelah 2 ronde. Eskalasi hanya untuk loop revisi/gates.
// M5: state bisa di-snapshot & di-restore agar service worker MV3 yang
// tidur tidak menghilangkan rapat — snapshot disimpan persisten oleh
// storage/roomState.ts (chrome.storage.session + chrome.storage.local).
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
  // N6 (putaran 2): side panel masuk ronde baru dari debat_ulang ke
  // usulan_r1 — sebelumnya satu-satunya jalan keluar debat_ulang adalah
  // debat_lanjut ke kritik_silang, sehingga usulan_diterima ronde
  // berikut selalu ditolak mesin (hanya valid dari usulan_r1).
  // ronde_baru menaikkan nomor ronde dan menjaga batas MAX_DEBATE_ROUNDS
  // (ronde > 3 -> spesifikasi dengan dissent, seperti debat_lanjut).
  ronde_baru: ['debat_ulang', 'usulan_r1'],
  mufakat_atau_juri: ['rapat', 'spesifikasi'],
  // M4: juri memutus di rapat (dipakai saat ronde 3 tanpa mufakat).
  juri_memutus: ['rapat', 'spesifikasi'],
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

export interface DebateSnapshot {
  state: DebateState;
  debateRound: number;
  fixIterations: number;
  totalIterations: number;
  dissent: string | null;
}

export interface DebateMachine {
  getState(): DebateState;
  getRound(): number;
  /** Dissent yang tercatat bila rapat berakhir tanpa mufakat (M4). */
  getDissent(): string | null;
  recordDissent(note: string): void;
  transition(event: string, note?: string): DebateState;
  getSnapshot(): DebateSnapshot;
  restore(snapshot: DebateSnapshot): void;
  isTerminal(): boolean;
}

export function createDebateMachine(initial?: Partial<DebateSnapshot>): DebateMachine {
  let state: DebateState = initial?.state ?? 'ide';
  let debateRound = initial?.debateRound ?? 0;
  let fixIterations = initial?.fixIterations ?? 0;
  let totalIterations = initial?.totalIterations ?? 0;
  let dissent: string | null = initial?.dissent ?? null;
  return {
    getState: () => state,
    getRound: () => debateRound,
    getDissent: () => dissent,
    recordDissent(note: string): void {
      dissent = note;
    },
    transition(event: string, note?: string): DebateState {
      // N6: 'reset' dari state APAPUN kembali ke 'ide' (dipakai tombol
      // "Mulai rapat" agar rapat kedua bisa dimulai; sebelumnya kirim_ide
      // hanya valid dari 'ide' dan tidak ada jalan reset).
      if (event === 'reset') {
        state = 'ide';
        debateRound = 0;
        fixIterations = 0;
        totalIterations = 0;
        dissent = null;
        return state;
      }
      const edge = TRANSITIONS[event];
      if (!edge) throw new Error(`Event tidak dikenal: ${event}`);
      const [from, to] = edge;
      if (state !== from) {
        throw new Error(`Event ${event} tidak valid dari state ${state} (harus dari ${from}).`);
      }
      if (event === 'debat_lanjut') {
        debateRound += 1;
        if (debateRound >= MAX_DEBATE_ROUNDS) {
          // M4: ronde 3 tanpa mufakat -> spesifikasi dengan dissent,
          // bukan eskalasi. Juri memutus berdasarkan voting terakhir.
          dissent =
            note ??
            `Ronde ${debateRound} tanpa mufakat: juri memutus berdasarkan voting terakhir. ` +
              'Keberatan minoritas dicatat di sini dan dilampirkan pada spesifikasi.';
          state = 'spesifikasi';
          return state;
        }
      }
      if (event === 'ronde_baru') {
        debateRound += 1;
        if (debateRound > MAX_DEBATE_ROUNDS) {
          // Pertahanan: ronde baru melewati batas (mis. belum_mufakat di
          // ronde 3 lolos dari UI) -> spesifikasi dengan dissent, bukan
          // ronde 4 yang tidak ada.
          dissent =
            note ??
            `Ronde ${debateRound} tanpa mufakat: juri memutus berdasarkan voting terakhir. ` +
              'Keberatan minoritas dicatat di sini dan dilampirkan pada spesifikasi.';
          state = 'spesifikasi';
          return state;
        }
      }
      if (event === 'juri_memutus') {
        dissent =
          note ??
          'Juri memutus tanpa mufakat penuh. Keberatan minoritas dicatat dan dilampirkan pada spesifikasi.';
      }
      if (event === 'mufakat_atau_juri' && note) dissent = note;
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
    getSnapshot: (): DebateSnapshot => ({ state, debateRound, fixIterations, totalIterations, dissent }),
    restore(snapshot: DebateSnapshot): void {
      state = snapshot.state;
      debateRound = snapshot.debateRound;
      fixIterations = snapshot.fixIterations;
      totalIterations = snapshot.totalIterations;
      dissent = snapshot.dissent;
    },
    isTerminal: () => state === 'selesai' || state === 'eskalasi',
  };
}
