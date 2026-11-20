// MUFAKAT Room — Side Panel App (Claude §T7).
// Mode: BROWSER-ONLY + MANUAL HANDOFF (MVP). Pengguna menyalin prompt,
// mengirim sendiri di tab resmi provider, lalu menempel jawaban kembali.
// Assisted Fill dan content script DIHAPUS dari MVP (modul opt-in Fase 2
// di src/phase2-optin/, tidak aktif dan tidak terdaftar di manifest).
// Extension tidak pernah menekan Kirim, tidak membaca DOM situs AI.
// Alur penuh: Ide -> Usulan -> Kritik silang -> Rapat (voting Borda) ->
// Spesifikasi (dengan dissent bila ronde 3 tanpa mufakat).
// Perbaikan putaran 2:
//  - N5: labelMap per ronde (runs.labelMap[round]) dibuat SEKALI saat
//    masuk fase kritik, dipakai di kritik/rapat/spesifikasi; pemenang
//    Borda dipetakan lewat labelMap (tanpa fallback ke usulan pertama);
//    prompt kritik tanpa nama provider.
//  - N6/GPT-1: satu sumber kebenaran = state machine background. Side
//    panel meng-await hasil transisi background dan menampilkan errornya
//    (tidak lagi .catch(()=>undefined)); ronde baru lewat ronde_baru;
//    "Mulai rapat" mengirim reset.
//  - GPT-2: buka ulang extension memulihkan ISI IDE (+ peserta, labelMap).
//  - GPT-4: secret scan SEBELUM db.runs.add; ide berkredensial tidak
//    tersimpan, pengguna memilih hapus otomatis / sunting manual.
//  - N13: jawaban AI disisipkan hanya sebagai DATA (delimiter +
//    instruksi), berisi summary/claims hasil parse.
//  - Tabel tambahan: hapus seluruh data rapat dari UI.
import React, { useCallback, useEffect, useState } from 'react';
// Perbaikan 2026-11-20: path impor sebelumnya ('../engine/...') menunjuk ke
// src/entrypoints/engine/ yang tidak ada — side panel tidak bisa di-build.
// Path yang benar dari src/entrypoints/sidepanel/ adalah '../../engine/...'.
import { blockingFindings, redactText, scanText } from '../../engine/secretScan';
import { checkPacing, recordPrompt } from '../../engine/pacing';
import { parseReply } from '../../engine/parser';
import {
  anonymize,
  decideConsensus,
  resolveWinnerProposal,
  type Critique,
  type Vote,
} from '../../engine/consensus';
import { DATA_GUARD_INSTRUCTION, listProposalsAsData, summarizeForPrompt, wrapAiData } from '../../engine/promptGuard';
import { checkActiveTab, type DoctorResult } from '../../adapters/doctor';
import { db, type MessageRecord } from '../../storage/db';
import { exportRun } from '../../storage/export';
import { clearRoomMeta, clearRoomState, loadRoomMeta, loadRoomState, saveRoomMeta } from '../../storage/roomState';
import Timeline from '../../ui/Timeline';
import VoteTable from '../../ui/VoteTable';

const PROVIDERS = [
  { id: 'chatgpt', name: 'ChatGPT', url: 'https://chatgpt.com/', status: 'Manual handoff only' },
  { id: 'claude', name: 'Claude', url: 'https://claude.ai/', status: 'Manual handoff only' },
  { id: 'gemini', name: 'Gemini', url: 'https://gemini.google.com/', status: 'Manual handoff only' },
  { id: 'deepseek', name: 'DeepSeek', url: 'https://chat.deepseek.com/', status: 'Manual handoff only' },
  { id: 'qwen', name: 'Qwen', url: 'https://chat.qwen.ai/', status: 'Manual handoff only' },
  { id: 'muse', name: 'Muse', url: 'https://www.meta.ai/', status: 'Needs policy review' },
];

const PHASES = ['proposal', 'critique', 'meeting', 'spec'] as const;
type Phase = (typeof PHASES)[number];
const PHASE_LABEL: Record<Phase, string> = {
  proposal: 'Usulan',
  critique: 'Kritik silang',
  meeting: 'Rapat & voting',
  spec: 'Spesifikasi',
};

const TOS_DISCLAIMER =
  'Mengotomasi web chat bisa melanggar Ketentuan Layanan penyedia AI. MUFAKAT Room ' +
  'dirancang semi-manual (Anda yang menekan Kirim) untuk meminimalkan risiko, tetapi ' +
  'risiko pembatasan akun tetap ada dan menjadi tanggung jawab pengguna. Gunakan akun ' +
  'sendiri, untuk proyek sendiri, dengan kecepatan wajar.';

function newRunId(): string {
  return `run-${Date.now().toString(36)}`;
}

interface RoomTransitionResponse {
  ok: boolean;
  state?: string;
  round?: number;
  dissent?: string | null;
  error?: string;
}

interface RoomStateResponse {
  state?: string;
  round?: number;
  dissent?: string | null;
}

/** GPT-1 (putaran 2): state machine background adalah SATU-SATUNYA sumber
 *  kebenaran fase/ronde/dissent. Side panel TIDAK menyimpan fase sendiri
 *  lalu mengabaikan hasil background — setiap transisi di-await dan
 *  hasilnya diterapkan ke UI; error transisi DITAMPILKAN ke pengguna
 *  (dulu ditelan .catch(()=>undefined)). */
async function requestRoomTransition(event: string, note?: string): Promise<RoomTransitionResponse> {
  try {
    if (typeof chrome === 'undefined' || !chrome.runtime?.sendMessage) {
      return { ok: false, error: 'Background tidak tersedia (chrome.runtime tidak ada).' };
    }
    const resp = (await chrome.runtime.sendMessage({ type: 'ROOM_TRANSITION', event, note })) as
      | RoomTransitionResponse
      | undefined;
    if (!resp) return { ok: false, error: 'Background tidak menjawab transisi.' };
    return resp;
  } catch (error) {
    return { ok: false, error: String(error) };
  }
}

async function fetchRoomState(): Promise<RoomStateResponse | null> {
  try {
    if (typeof chrome === 'undefined' || !chrome.runtime?.sendMessage) return null;
    const resp = (await chrome.runtime.sendMessage({ type: 'ROOM_STATE' })) as RoomStateResponse | undefined;
    return resp?.state ? resp : null;
  } catch {
    return null;
  }
}

/** Petakan state mesin background ke fase UI (UI hanya punya 4 fase;
 *  state sesudah spesifikasi — approve_spek, coding, dst. — tetap
 *  ditampilkan sebagai Spesifikasi). */
function machineStateToPhase(state: string): Phase {
  switch (state) {
    case 'ide':
    case 'usulan_r1':
    case 'debat_ulang':
      return 'proposal';
    case 'kritik_silang':
      return 'critique';
    case 'rapat':
      return 'meeting';
    default:
      return 'spec';
  }
}

export default function App(): React.ReactElement {
  const [idea, setIdea] = useState('');
  const [selected, setSelected] = useState<string[]>(['chatgpt', 'claude', 'gemini']);
  const [prompt, setPrompt] = useState('');
  const [imported, setImported] = useState('');
  const [importProvider, setImportProvider] = useState('chatgpt');
  const [notice, setNotice] = useState('');
  const [copying, setCopying] = useState(false);
  const [savingImport, setSavingImport] = useState(false);
  const [runId, setRunId] = useState<string>('');
  const [round, setRound] = useState(1);
  const [phase, setPhase] = useState<Phase>('proposal');
  const [messages, setMessages] = useState<MessageRecord[]>([]);
  const [dissent, setDissent] = useState<string | null>(null);
  const [doctor, setDoctor] = useState<DoctorResult | null>(null);
  const [resolvedCritiques, setResolvedCritiques] = useState<Set<string>>(new Set());
  // N5: labelMap per ronde (ronde -> label A/B/C -> provider), dibuat
  // SEKALI saat masuk fase kritik dan dipulihkan dari Dexie saat panel
  // dibuka ulang. Dipakai di kritik, rapat, dan spesifikasi.
  const [labelMaps, setLabelMaps] = useState<Record<number, Record<string, string>>>({});
  // GPT-4: ide yang diblokir secret scan — belum tersimpan; pengguna
  // memilih hapus kredensial otomatis atau sunting manual.
  const [ideaBlocked, setIdeaBlocked] = useState(false);
  const [blockedPatterns, setBlockedPatterns] = useState<string[]>([]);
  const [clearingData, setClearingData] = useState(false);

  const loadMessages = useCallback(async (id: string) => {
    const rows = await db.messages.where('runId').equals(id).sortBy('importedAt');
    setMessages(rows);
  }, []);

  /** Terapkan hasil transisi background ke UI (satu sumber kebenaran). */
  const applyMachineState = useCallback((resp: RoomTransitionResponse | RoomStateResponse) => {
    if (resp.state) setPhase(machineStateToPhase(resp.state));
    if (typeof resp.round === 'number') setRound(resp.round);
    setDissent(resp.dissent ?? null);
  }, []);

  useEffect(() => {
    void (async () => {
      const meta = await loadRoomMeta();
      if (meta) {
        setRunId(meta.runId);
        setRound(meta.round);
        setPhase(meta.phase as Phase);
        // GPT awal 2: pulihkan juga ISI IDE (+ peserta + labelMap) dari
        // data rapat — dulu hanya ID dan pesan yang dipulihkan sehingga
        // prompt berikutnya kehilangan konteks ide.
        const run = await db.runs.get(meta.runId);
        if (run) {
          setIdea(run.idea);
          setSelected(run.providers);
          setLabelMaps(run.labelMap ?? {});
        }
        await loadMessages(meta.runId);
      }
      // GPT awal 1: sinkronkan fase/ronde/dissent dari state machine
      // background (sumber kebenaran); meta lokal hanya jangkar runId.
      const synced = await fetchRoomState();
      if (synced) {
        applyMachineState(synced);
      } else {
        const room = await loadRoomState();
        if (room?.dissent) setDissent(room.dissent);
      }
    })();
  }, [loadMessages, applyMachineState]);

  async function persistMeta(id: string, r: number, p: Phase): Promise<void> {
    await saveRoomMeta({ runId: id, round: r, phase: p });
  }

  /** N5: ambil labelMap ronde ini; bila belum ada, buat SEKALI dari
   *  usulan ronde itu (anonymize, seed acak) dan simpan ke Dexie +
   *  state. Dipanggil saat masuk fase kritik DAN saat menyusun prompt
   *  (untuk run lama yang belum punya labelMap) — label yang sama
   *  dipakai di kritik, rapat, dan spesifikasi. */
  function getOrCreateLabelMap(roundNo: number): Record<string, string> | null {
    const existing = labelMaps[roundNo];
    if (existing) return existing;
    const proposals = messages.filter((m) => m.round === roundNo && m.phase === 'proposal');
    if (!proposals.length) return null;
    const { mapping } = anonymize(proposals.map((m) => ({ agentId: m.provider, text: m.rawText })));
    const next = { ...labelMaps, [roundNo]: mapping };
    setLabelMaps(next);
    if (runId) void db.runs.update(runId, { labelMap: next });
    return mapping;
  }

  async function startRun(ideaOverride?: string): Promise<void> {
    const text = (ideaOverride ?? idea).trim();
    if (!text) {
      setNotice('Tulis ide dulu sebelum memulai rapat.');
      return;
    }
    // GPT-4: secret scan SEBELUM db.runs.add() — ide yang mengandung
    // kredensial TIDAK BOLEH tersimpan. Notice hanya menyebut NAMA POLA,
    // tidak pernah nilai/preview kredensial.
    const findings = blockingFindings(scanText(text));
    if (findings.length) {
      setIdeaBlocked(true);
      setBlockedPatterns(findings.map((f) => f.pattern));
      setNotice(
        `Ide diblokir secret scanner: ${findings.map((f) => f.pattern).join(', ')}. Kredensial TIDAK disimpan. Pilih: hapus kredensial otomatis, atau sunting manual.`,
      );
      return;
    }
    setIdeaBlocked(false);
    setBlockedPatterns([]);
    const id = newRunId();
    // N6: reset mesin dulu agar rapat kedua bisa dimulai (kirim_ide hanya
    // valid dari 'ide'); keduanya di-await dan hasilnya diterapkan ke UI.
    const reset = await requestRoomTransition('reset');
    if (!reset.ok) {
      setNotice(`Gagal mereset rapat lama: ${reset.error}. Rapat baru tidak dimulai.`);
      return;
    }
    await db.runs.add({ id, idea: text, state: 'usulan_r1', roundNo: 1, providers: selected, createdAt: Date.now() });
    setRunId(id);
    setRound(1);
    setPhase('proposal');
    setDissent(null);
    setMessages([]);
    setLabelMaps({});
    await persistMeta(id, 1, 'proposal');
    const started = await requestRoomTransition('kirim_ide');
    if (!started.ok) {
      setNotice(`Rapat ${id} tersimpan, tapi transisi kirim_ide gagal: ${started.error}. Tekan "Mulai rapat" lagi.`);
      return;
    }
    applyMachineState(started);
    setNotice(`Rapat ${id} dimulai (ronde 1, fase Usulan). Susun prompt lalu salin ke tiap provider.`);
  }

  /** GPT-4: hapus kredensial dari ide (redact -> [REDACTED:<pola>]) lalu
   *  mulai rapat dengan teks yang sudah bersih. */
  function redactIdeaAndStart(): void {
    const redacted = redactText(idea);
    setIdea(redacted);
    setIdeaBlocked(false);
    setBlockedPatterns([]);
    void startRun(redacted);
  }

  function toggleProvider(id: string): void {
    setSelected((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]));
  }

  /** Daftar usulan ronde ini sebagai blok DATA anonim (label A/B/C dari
   *  labelMap, TANPA nama provider — N5) dan hanya berisi ringkasan/
   *  claims hasil parse (N13). */
  function listRoundProposalsAsData(roundNo: number): string | null {
    const map = getOrCreateLabelMap(roundNo);
    if (!map) return null;
    const proposals = messages.filter((m) => m.round === roundNo && m.phase === 'proposal');
    return listProposalsAsData(map, proposals);
  }

  function buildPrompt(): void {
    if (!runId) {
      setNotice('Mulai rapat dulu (tombol "Mulai rapat") sebelum menyusun prompt.');
      return;
    }
    const roundMessages = messages.filter((m) => m.round === round);
    const proposals = roundMessages.filter((m) => m.phase === 'proposal');
    let text: string;
    if (phase === 'proposal') {
      text =
        `Kamu adalah debater dalam rapat multi-AI. Ide yang dibahas:\n${idea}\n\n` +
        'Buat usulan solusi yang konkret dan mandiri. Tulis penjelasan singkat, lalu akhiri ' +
        'dengan SATU blok ```json sesuai skema.';
    } else if (phase === 'critique') {
      // N5: label dari labelMap (sama dengan fase rapat), TANPA nama
      // provider. N13: isi usulan hanya summary/claims, dalam delimiter.
      const listed = listRoundProposalsAsData(round);
      if (!listed) {
        setNotice('Belum ada usulan yang diimpor di ronde ini. Impor minimal 1 jawaban dulu.');
        return;
      }
      text =
        `Kamu adalah kritikus dalam rapat multi-AI. Ide: ${idea}\n\n${DATA_GUARD_INSTRUCTION}\n\n` +
        `Usulan yang dikritik (label anonim, nama AI disembunyikan):\n${listed}\n\n` +
        'Tulis kritik silang: kelemahan, risiko, dan pertanyaan untuk tiap usulan. Akhiri dengan ' +
        'SATU blok ```json berisi daftar critiques (severity: info/minor/major/blocking).';
    } else if (phase === 'meeting') {
      const listed = listRoundProposalsAsData(round);
      if (!listed) {
        setNotice('Belum ada usulan yang diimpor di ronde ini. Impor minimal 1 jawaban dulu.');
        return;
      }
      text =
        `Kamu adalah peserta rapat multi-AI (ronde ${round}). Ide: ${idea}\n\n${DATA_GUARD_INSTRUCTION}\n\n` +
        `Usulan anonim:\n${listed}\n\n` +
        'Beri vote: ranking usulan (pakai label A/B/C) dan decision approve/revise/reject. Akhiri dengan ' +
        'SATU blok ```json berisi vote {decision, ranking}.';
    } else {
      // N5: pemenang Borda (label A/B/C) dipetakan lewat labelMap ke
      // proposal yang benar. TANPA labelMap / pemenang tak terpetakan,
      // spesifikasi DITOLAK — JANGAN fallback ke usulan pertama.
      const winner = computeConsensus();
      const winnerProposal = resolveWinnerProposal(labelMaps[round], winner?.winner ?? null, proposals);
      if (!winner || !winnerProposal) {
        setNotice(
          winner?.winner
            ? `Pemenang voting (${winner.winner}) tidak bisa dipetakan ke usulan — labelMap ronde ${round} hilang. Jangan pakai usulan pertama sebagai gantinya; ulangi voting atau mulai rapat baru.`
            : 'Belum ada vote yang bisa diparse di ronde ini — tidak ada pemenang untuk spesifikasi.',
        );
        return;
      }
      const winnerText = summarizeForPrompt(winnerProposal.rawText, 2000);
      text =
        `Tulis spesifikasi teknis dari usulan terpilih untuk ide: ${idea}\n\n${DATA_GUARD_INSTRUCTION}\n\n` +
        `Usulan terpilih:\n${wrapAiData(`Usulan ${winner.winner}`, winnerText)}\n\n` +
        (dissent ? `Catatan dissent (keberatan minoritas, WAJIB dilampirkan): ${dissent}\n\n` : '') +
        'Akhiri dengan SATU blok ```json berisi spec.';
    }
    const findings = scanText(text);
    const blocking = blockingFindings(findings);
    if (blocking.length) {
      setNotice(`Prompt diblokir secret scanner: ${blocking.map((f) => f.pattern).join(', ')}. Hapus kredensial dari ide.`);
      return;
    }
    setPrompt(text);
    setNotice(
      findings.length
        ? `Prompt siap (peringatan secret scanner: ${findings.map((f) => f.pattern).join(', ')} — bukan blokir). Salin, tempel di tab resmi provider, dan tekan Kirim sendiri.`
        : 'Prompt siap. Salin, tempel di tab resmi provider, dan tekan Kirim sendiri.',
    );
  }

  async function copyPrompt(): Promise<void> {
    if (!prompt || copying) return;
    // T3: cek pacing PER situs yang dipilih (bukan hanya yang pertama),
    // dan catat pemakaian SETELAH salin berhasil agar batas 20 detik /
    // 40-per-hari benar-benar ditegakkan. Tombol di-disable selama proses
    // agar klik ganda tidak menggandakan pencatatan.
    setCopying(true);
    try {
      const sites = selected.length ? selected : ['chatgpt'];
      for (const site of sites) {
        const decision = await checkPacing(site);
        if (!decision.allowed) {
          setNotice(`Pacing: ${decision.reason}`);
          return;
        }
      }
      await navigator.clipboard.writeText(prompt);
      await Promise.all(sites.map((site) => recordPrompt(site)));
      setNotice('Prompt disalin. Tempel di tab resmi provider dan tekan Kirim sendiri.');
    } finally {
      setCopying(false);
    }
  }

  // T2/H5: impor jawaban benar-benar disimpan. Urutan: secret scan dulu
  // (blokir hanya bila ada temuan 'block'; '.env' hanya peringatan),
  // lalu parse (status parse dicatat), lalu simpan ke IndexedDB dengan
  // provider/ronde/fase tercatat. Notice "disimpan" HANYA ditampilkan
  // SETELAH db.messages.add() berhasil — sebelumnya tombol ini hanya
  // menampilkan notice lalu membuang teks.
  async function saveImported(): Promise<void> {
    if (!imported.trim() || savingImport) return;
    if (!runId) {
      setNotice('Mulai rapat dulu sebelum mengimpor jawaban.');
      return;
    }
    setSavingImport(true);
    try {
      const findings = scanText(imported);
      const blocking = blockingFindings(findings);
      if (blocking.length) {
        setNotice(
          `Impor diblokir secret scanner: ${blocking.map((f) => f.pattern).join(', ')}. Hapus kredensial dari jawaban sebelum menyimpan.`,
        );
        return;
      }
      const parsed = parseReply(imported);
      await db.messages.add({
        runId,
        round,
        phase,
        provider: importProvider,
        source: 'user imported',
        rawText: imported,
        parseStatus: parsed.status,
        importedAt: Date.now(),
      });
      await loadMessages(runId);
      const warn = findings.filter((f) => f.severity === 'warn');
      setNotice(
        (parsed.status === 'ok'
          ? `Jawaban ${importProvider} disimpan (ronde ${round}, fase ${PHASE_LABEL[phase]}, parse ok).`
          : `Jawaban ${importProvider} disimpan (ronde ${round}, fase ${PHASE_LABEL[phase]}, parse: ${parsed.status}${parsed.error ? ` — ${parsed.error}` : ''}).`) +
          (warn.length ? ` Peringatan: ${warn.map((f) => f.pattern).join(', ')}.` : ''),
      );
      setImported('');
    } catch (error) {
      setNotice(`Gagal menyimpan jawaban impor: ${String(error)}. Teks tetap ada, coba lagi.`);
    } finally {
      setSavingImport(false);
    }
  }

  function computeConsensus(): ReturnType<typeof decideConsensus> & { votes: Vote[]; critiques: Array<Critique & { key: string }> } | null {
    const roundMessages = messages.filter((m) => m.round === round);
    const meetingMessages = roundMessages.filter((m) => m.phase === 'meeting');
    const votes: Vote[] = [];
    for (const m of meetingMessages) {
      const parsed = parseReply(m.rawText);
      if (parsed.status === 'ok' && parsed.payload?.vote) {
        votes.push({ agentId: m.provider, decision: parsed.payload.vote.decision, ranking: parsed.payload.vote.ranking });
      }
    }
    const critiques: Array<Critique & { key: string }> = [];
    for (const m of roundMessages.filter((m) => m.phase === 'critique')) {
      const parsed = parseReply(m.rawText);
      for (const c of parsed.payload?.critiques ?? []) {
        if (!c.severity || !c.text) continue;
        const key = `${m.id ?? m.importedAt}:${c.text}`;
        critiques.push({ severity: c.severity, text: c.text, key, resolved: resolvedCritiques.has(key) });
      }
    }
    if (!votes.length) return null;
    const result = decideConsensus(votes, critiques);
    return { ...result, votes, critiques };
  }

  async function advancePhase(): Promise<void> {
    if (!runId) return;
    const roundMessages = messages.filter((m) => m.round === round);
    if (phase === 'proposal') {
      if (!roundMessages.some((m) => m.phase === 'proposal')) {
        setNotice('Belum ada usulan yang diimpor di ronde ini. Impor minimal 1 jawaban dulu.');
        return;
      }
      // N5: buat labelMap ronde ini SEKALI, sebelum masuk fase kritik.
      if (!getOrCreateLabelMap(round)) {
        setNotice('Gagal membuat label anonim ronde ini (tidak ada usulan).');
        return;
      }
      const resp = await requestRoomTransition('usulan_diterima');
      if (!resp.ok) {
        setNotice(`Transisi gagal (usulan_diterima): ${resp.error}. Fase tidak berubah — coba lagi.`);
        return;
      }
      applyMachineState(resp);
      await persistMeta(runId, round, 'critique');
      setNotice('Fase Kritik silang. Susun prompt kritik, salin, dan impor jawaban tiap provider.');
    } else if (phase === 'critique') {
      if (!roundMessages.some((m) => m.phase === 'critique')) {
        setNotice('Belum ada kritik yang diimpor di ronde ini. Impor minimal 1 jawaban dulu.');
        return;
      }
      const resp = await requestRoomTransition('kritik_diterima');
      if (!resp.ok) {
        setNotice(`Transisi gagal (kritik_diterima): ${resp.error}. Fase tidak berubah — coba lagi.`);
        return;
      }
      applyMachineState(resp);
      await persistMeta(runId, round, 'meeting');
      setNotice('Fase Rapat & voting. Susun prompt rapat, salin, dan impor vote tiap provider.');
    } else if (phase === 'meeting') {
      // N6: bila mesin masih di debat_ulang (ronde_baru sebelumnya gagal),
      // lanjutkan ronde itu dulu — jangan kirim belum_mufakat dari rapat
      // karena mesin sudah tidak di rapat.
      const synced = await fetchRoomState();
      if (synced?.state === 'debat_ulang') {
        const resumed = await requestRoomTransition('ronde_baru');
        if (!resumed.ok) {
          setNotice(`Transisi gagal (ronde_baru): ${resumed.error}. Tekan "Lanjut" lagi untuk mencoba.`);
          return;
        }
        applyMachineState(resumed);
        await persistMeta(runId, resumed.round ?? round, 'proposal');
        setNotice(`Debat ulang dilanjutkan — ronde ${resumed.round ?? round}, fase Usulan.`);
        return;
      }
      const result = computeConsensus();
      if (!result) {
        setNotice('Belum ada vote yang bisa diparse di ronde ini. Impor jawaban rapat (blok ```json vote) dulu.');
        return;
      }
      if (result.decision === 'mufakat') {
        const resp = await requestRoomTransition('mufakat_atau_juri');
        if (!resp.ok) {
          setNotice(`Transisi gagal (mufakat_atau_juri): ${resp.error}. Fase tidak berubah — coba lagi.`);
          return;
        }
        applyMachineState(resp);
        await persistMeta(runId, round, 'spec');
        setNotice(`Mufakat tercapai (pemenang ${result.winner}, approve ${result.winnerApprovals}/${result.votes.length}). Lanjut ke Spesifikasi.`);
      } else if (round >= 3) {
        // M4: ronde 3 tanpa mufakat -> spesifikasi dengan dissent, bukan eskalasi.
        const note = `Ronde 3 tanpa mufakat (keputusan: ${result.decision}, pemenang voting: ${result.winner ?? '—'}, blocking belum dijawab: ${result.blocking}). Juri memutus berdasarkan voting terakhir; keberatan minoritas dilampirkan pada spesifikasi.`;
        const resp = await requestRoomTransition('juri_memutus', note);
        if (!resp.ok) {
          setNotice(`Transisi gagal (juri_memutus): ${resp.error}. Fase tidak berubah — coba lagi.`);
          return;
        }
        applyMachineState(resp);
        await persistMeta(runId, round, 'spec');
        setNotice('Ronde 3 tanpa mufakat — juri memutus, dissent dicatat. Lanjut ke Spesifikasi.');
      } else {
        // N6: belum_mufakat (rapat -> debat_ulang) DILANJUTKAN ronde_baru
        // (debat_ulang -> usulan_r1, ronde +1) dalam satu langkah pengguna.
        // Tanpa ronde_baru, usulan_diterima ronde berikut ditolak mesin.
        const first = await requestRoomTransition('belum_mufakat');
        if (!first.ok) {
          setNotice(`Transisi gagal (belum_mufakat): ${first.error}. Fase tidak berubah — coba lagi.`);
          return;
        }
        const second = await requestRoomTransition('ronde_baru');
        if (!second.ok) {
          // Mesin sudah di debat_ulang; UI mengikuti mesin (sumber
          // kebenaran). Tekan "Lanjut" lagi untuk mencoba ronde_baru.
          applyMachineState(first);
          setNotice(`Belum mufakat tercatat, tapi lanjut ronde gagal: ${second.error}. Tekan "Lanjut" lagi untuk mencoba ronde_baru.`);
          return;
        }
        applyMachineState(second);
        await persistMeta(runId, second.round ?? round + 1, 'proposal');
        setNotice(`Belum mufakat (keputusan: ${result.decision}). Debat ulang — ronde ${second.round ?? round + 1}, fase Usulan.`);
      }
    } else {
      const resp = await requestRoomTransition('spek_selesai');
      if (!resp.ok) {
        setNotice(`Transisi gagal (spek_selesai): ${resp.error}. Coba lagi.`);
        return;
      }
      applyMachineState(resp);
      setNotice('Spesifikasi selesai. Lanjutkan ke coding/review/gates di Local Runner setelah Anda menyetujui patch.');
    }
  }

  async function runDoctor(): Promise<void> {
    // Situs diambil dari URL tab AKTIF yang benar-benar dicek, bukan
    // selected[0] (tabel tambahan putaran 2).
    setDoctor(await checkActiveTab());
  }

  /** Tabel tambahan (putaran 2): hapus SELURUH data rapat dari UI —
   *  semua run/pesan/gate/pemakaian di Dexie, meta + snapshot di
   *  chrome.storage, dan reset state machine background. */
  async function clearAllData(): Promise<void> {
    if (
      !window.confirm(
        'Hapus SELURUH data rapat (semua run, pesan impor, hasil gate, pemakaian, dan state tersimpan)? Tindakan ini tidak bisa dibatalkan.',
      )
    ) {
      return;
    }
    setClearingData(true);
    try {
      await db.messages.clear();
      await db.gateResults.clear();
      await db.usage.clear();
      await db.runs.clear();
      await clearRoomState();
      await clearRoomMeta();
      await requestRoomTransition('reset');
      setRunId('');
      setRound(1);
      setPhase('proposal');
      setMessages([]);
      setDissent(null);
      setLabelMaps({});
      setPrompt('');
      setImported('');
      setDoctor(null);
      setNotice('Seluruh data rapat dihapus (Dexie + chrome.storage + state machine).');
    } catch (error) {
      setNotice(`Gagal menghapus data: ${String(error)}.`);
    } finally {
      setClearingData(false);
    }
  }

  async function downloadTranscript(): Promise<void> {
    if (!runId) return;
    const { markdown } = await exportRun(runId, idea);
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${runId}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function openOfficialSite(url: string): void {
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  const consensus = phase === 'meeting' || phase === 'spec' ? computeConsensus() : null;
  const roundMessages = messages.filter((m) => m.round === round);

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: 16, maxWidth: 640 }}>
      <h1>MUFAKAT Room</h1>
      <p style={{ background: '#fff3cd', padding: 8, borderRadius: 4 }}>{TOS_DISCLAIMER}</p>
      <p>
        <strong>Mode: Manual Handoff (browser-only).</strong> Extension tidak pernah menekan Kirim,
        tidak membaca DOM situs AI, dan tidak mengisi input. Content script &amp; Assisted Fill{' '}
        <strong>dihapus dari MVP</strong> (modul opt-in Fase 2 di <code>src/phase2-optin/</code>,
        tidak aktif dan tidak terdaftar di manifest).
      </p>
      <p style={{ background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
        <strong>Privasi data:</strong> data rapat (ide, jawaban impor, state) tersimpan{' '}
        <strong>tanpa enkripsi aplikasi</strong> di IndexedDB &amp; chrome.storage lokal browser
        (risiko terbuka — lihat README). Jangan masukkan kredensial (secret scanner memblokir).
        Hapus semua data kapan saja dengan tombol "Hapus seluruh data rapat" di bawah.
      </p>
      {runId && (
        <p>
          Rapat: <code>{runId}</code> — Ronde {round} — Fase: <strong>{PHASE_LABEL[phase]}</strong>
          {dissent && (
            <span style={{ display: 'block', background: '#ffe8e8', padding: 6, marginTop: 4 }}>Dissent: {dissent}</span>
          )}
        </p>
      )}

      <h2>1. Ide</h2>
      <textarea
        value={idea}
        onChange={(e) => setIdea(e.target.value)}
        placeholder="Tulis ide / permintaan..."
        rows={4}
        style={{ width: '100%' }}
      />
      <button type="button" onClick={() => void startRun()}>Mulai rapat</button>
      {ideaBlocked && (
        <div style={{ background: '#ffe8e8', padding: 8, marginTop: 8, borderRadius: 4 }}>
          <p>
            Ide mengandung kredensial ({blockedPatterns.join(', ')}) dan <strong>tidak disimpan</strong>.
            Nilai kredensial tidak ditampilkan di mana pun.
          </p>
          <button type="button" onClick={redactIdeaAndStart}>
            Hapus kredensial otomatis &amp; mulai rapat
          </button>{' '}
          <button
            type="button"
            onClick={() => {
              setIdeaBlocked(false);
              setBlockedPatterns([]);
              setNotice('Sunting ide di atas untuk menghapus kredensial, lalu tekan "Mulai rapat" lagi.');
            }}
          >
            Sunting manual
          </button>
        </div>
      )}

      <h2>2. Pilih AI peserta</h2>
      {PROVIDERS.map((provider) => (
        <div key={provider.id}>
          <label>
            <input type="checkbox" checked={selected.includes(provider.id)} onChange={() => toggleProvider(provider.id)} />{' '}
            {provider.name} — <em>{provider.status}</em>
          </label>{' '}
          <button type="button" onClick={() => openOfficialSite(provider.url)}>
            Buka situs resmi ({new URL(provider.url).hostname})
          </button>
        </div>
      ))}
      <p>
        <button type="button" onClick={runDoctor}>Cek adapter tab aktif (Selector Doctor)</button>
        {doctor && (
          <span style={{ display: 'block', marginTop: 4 }}>
            {doctor.site}: {doctor.health} — {doctor.detail} (input: {doctor.inputFound ? 'ketemu' : 'hilang'}, jawaban
            terakhir: {doctor.lastReplyFound ? 'terbaca' : 'belum ada'})
          </span>
        )}
      </p>

      <h2>3. Prompt ronde {round} — {PHASE_LABEL[phase]}</h2>
      <button type="button" onClick={buildPrompt} disabled={!runId}>Susun prompt</button>{' '}
      <button type="button" onClick={copyPrompt} disabled={!prompt || copying}>Salin prompt</button>
      {prompt && <pre style={{ whiteSpace: 'pre-wrap', background: '#f5f5f5', padding: 8 }}>{prompt}</pre>}

      <h2>4. Impor jawaban (tempel dari tab resmi)</h2>
      <label>
        Provider jawaban ini:{' '}
        <select value={importProvider} onChange={(e) => setImportProvider(e.target.value)}>
          {PROVIDERS.map((provider) => (
            <option key={provider.id} value={provider.id}>
              {provider.name}
            </option>
          ))}
        </select>
      </label>
      <textarea
        value={imported}
        onChange={(e) => setImported(e.target.value)}
        placeholder="Tempel jawaban AI di sini. Jawaban disimpan dengan label 'user imported'."
        rows={6}
        style={{ width: '100%' }}
      />
      <button type="button" onClick={saveImported} disabled={!imported.trim() || savingImport}>
        Simpan jawaban impor
      </button>
      <p style={{ color: '#555' }}>
        Jawaban diimpor: {roundMessages.length} di ronde {round} (
        {PHASES.map((p) => `${PHASE_LABEL[p]}: ${roundMessages.filter((m) => m.phase === p).length}`).join(', ')}).
      </p>

      {consensus && (
        <div>
          <h2>Hasil voting ronde {round}</h2>
          <p>
            Keputusan: <strong>{consensus.decision}</strong> — pemenang: {consensus.winner ?? '—'} — approve
            pemenang: {consensus.winnerApprovals}/{consensus.votes.length} (
            {Math.round(consensus.approveRatio * 100)}%) — blocking belum dijawab: {consensus.blocking}
          </p>
          <VoteTable
            votes={consensus.votes.map((v) => ({ label: v.agentId, decision: v.decision, ranking: v.ranking }))}
            borda={consensus.borda}
          />
          {consensus.critiques.filter((c) => c.severity === 'blocking').length > 0 && (
            <div>
              <h3>Kritik blocking</h3>
              {consensus.critiques
                .filter((c) => c.severity === 'blocking')
                .map((c, i) => {
                  const key = c.key;
                  return (
                    <label key={i} style={{ display: 'block' }}>
                      <input
                        type="checkbox"
                        checked={resolvedCritiques.has(key)}
                        onChange={() =>
                          setResolvedCritiques((prev) => {
                            const next = new Set(prev);
                            if (next.has(key)) next.delete(key);
                            else next.add(key);
                            return next;
                          })
                        }
                      />{' '}
                      Sudah dijawab: {c.text}
                    </label>
                  );
                })}
              <p style={{ color: '#555' }}>Centang kritik yang sudah dijawab agar tidak lagi menghalangi mufakat.</p>
            </div>
          )}
        </div>
      )}

      <button type="button" onClick={advancePhase} disabled={!runId}>
        {phase === 'spec' ? 'Tandai spesifikasi selesai' : `Lanjut: ${phase === 'proposal' ? 'Kritik silang' : phase === 'critique' ? 'Rapat & voting' : 'Keputusan rapat'}`}
      </button>{' '}
      <button type="button" onClick={downloadTranscript} disabled={!runId}>Unduh transkrip (.md)</button>{' '}
      <button type="button" onClick={() => void clearAllData()} disabled={clearingData}>
        Hapus seluruh data rapat
      </button>

      {notice && <p role="status" style={{ background: '#e7f3ff', padding: 8 }}>{notice}</p>}

      <h2>Timeline ronde</h2>
      <Timeline
        events={messages.map((m) => ({
          round: m.round,
          phase: PHASE_LABEL[m.phase as Phase] ?? m.phase,
          text: `${m.provider} (${m.source}, parse ${m.parseStatus}): ${m.rawText.slice(0, 200)}`,
        }))}
      />
      <p>
        <em>
          Yang masih manual: login di situs AI, menekan Kirim, menempel jawaban,
          menyetujui patch &amp; commit. Local Runner menjalankan gates di Docker setelah
          pengguna menyetujui patch.
        </em>
      </p>
    </div>
  );
}
