// MUFAKAT Room — Side Panel App (Claude §T7).
// Mode: BROWSER-ONLY + MANUAL HANDOFF (MVP). Pengguna menyalin prompt,
// mengirim sendiri di tab resmi provider, lalu menempel jawaban kembali.
// Assisted Fill DIHAPUS dari MVP (modul opt-in Fase 2, tidak aktif —
// content script + background FILL_INPUT tetap ada sebagai modul terpisah
// tapi tidak dipakai alur utama Room). Extension tidak pernah menekan Kirim.
// Alur penuh: Ide -> Usulan -> Kritik silang -> Rapat (voting Borda) ->
// Spesifikasi (dengan dissent bila ronde 3 tanpa mufakat).
import React, { useCallback, useEffect, useState } from 'react';
// Perbaikan 2026-11-20: path impor sebelumnya ('../engine/...') menunjuk ke
// src/entrypoints/engine/ yang tidak ada — side panel tidak bisa di-build.
// Path yang benar dari src/entrypoints/sidepanel/ adalah '../../engine/...'.
import { blockingFindings, scanText } from '../../engine/secretScan';
import { checkPacing, recordPrompt } from '../../engine/pacing';
import { parseReply } from '../../engine/parser';
import { anonymize, decideConsensus, type Critique, type Vote } from '../../engine/consensus';
import { checkCurrentTab, type DoctorResult } from '../../adapters/doctor';
import { db, type MessageRecord } from '../../storage/db';
import { exportRun } from '../../storage/export';
import { loadRoomMeta, loadRoomState, saveRoomMeta } from '../../storage/roomState';
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

function sendRoomTransition(event: string, note?: string): void {
  try {
    if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
      chrome.runtime.sendMessage({ type: 'ROOM_TRANSITION', event, note }).catch(() => undefined);
    }
  } catch {
    // Background tidak wajib hidup untuk Manual Handoff; fase panel tetap jalan.
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
  const [fetchingReply, setFetchingReply] = useState(false);

  const loadMessages = useCallback(async (id: string) => {
    const rows = await db.messages.where('runId').equals(id).sortBy('importedAt');
    setMessages(rows);
  }, []);

  useEffect(() => {
    void (async () => {
      const meta = await loadRoomMeta();
      if (meta) {
        setRunId(meta.runId);
        setRound(meta.round);
        setPhase(meta.phase as Phase);
        await loadMessages(meta.runId);
      }
      const room = await loadRoomState();
      if (room?.dissent) setDissent(room.dissent);
    })();
  }, [loadMessages]);

  async function persistMeta(id: string, r: number, p: Phase): Promise<void> {
    await saveRoomMeta({ runId: id, round: r, phase: p });
  }

  async function startRun(): Promise<void> {
    if (!idea.trim()) {
      setNotice('Tulis ide dulu sebelum memulai rapat.');
      return;
    }
    const id = newRunId();
    await db.runs.add({ id, idea: idea.trim(), state: 'usulan_r1', roundNo: 1, providers: selected, createdAt: Date.now() });
    setRunId(id);
    setRound(1);
    setPhase('proposal');
    setDissent(null);
    setMessages([]);
    await persistMeta(id, 1, 'proposal');
    sendRoomTransition('kirim_ide');
    setNotice(`Rapat ${id} dimulai (ronde 1, fase Usulan). Susun prompt lalu salin ke tiap provider.`);
  }

  function toggleProvider(id: string): void {
    setSelected((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]));
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
      const listed = proposals
        .map((m, i) => `Usulan ${String.fromCharCode(65 + i)} (${m.provider}):\n${m.rawText.slice(0, 1200)}`)
        .join('\n\n');
      text =
        `Kamu adalah kritikus dalam rapat multi-AI. Ide: ${idea}\n\nUsulan yang dikritik:\n${listed}\n\n` +
        'Tulis kritik silang: kelemahan, risiko, dan pertanyaan untuk tiap usulan. Akhiri dengan ' +
        'SATU blok ```json berisi daftar critiques (severity: info/minor/major/blocking).';
    } else if (phase === 'meeting') {
      const anon = anonymize(proposals.map((m) => ({ agentId: m.provider, text: m.rawText.slice(0, 800) })));
      const listed = anon.items.map((item) => `Usulan ${item.label}:\n${item.text}`).join('\n\n');
      text =
        `Kamu adalah peserta rapat multi-AI (ronde ${round}). Ide: ${idea}\n\nUsulan anonim:\n${listed}\n\n` +
        'Beri vote: ranking usulan (pakai label A/B/C) dan decision approve/revise/reject. Akhiri dengan ' +
        'SATU blok ```json berisi vote {decision, ranking}.';
    } else {
      const winner = computeConsensus();
      const winnerText = winner?.winner
        ? (proposals.find((m) => m.provider === winner.winner)?.rawText ?? '')
        : (proposals[0]?.rawText ?? '');
      text =
        `Tulis spesifikasi teknis dari usulan terpilih untuk ide: ${idea}\n\nUsulan terpilih:\n${winnerText.slice(0, 2000)}\n\n` +
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

  /** Ambil jawaban terakhir dari tab provider via background + content
   *  script (readLastReply pakai turndown -> Markdown). Hasilnya masuk ke
   *  textarea impor; penyimpanan tetap lewat tombol Simpan (dengan
   *  secret scan). */
  async function fetchLastReply(): Promise<void> {
    if (fetchingReply) return;
    setFetchingReply(true);
    try {
      const reply = await chrome.runtime.sendMessage({ type: 'READ_LAST_REPLY', site: importProvider });
      const text = reply?.reply?.markdown ?? reply?.reply?.text ?? '';
      if (reply?.ok && text) {
        setImported(text);
        setNotice(`Jawaban terakhir ${importProvider} diambil dari tab (Markdown via turndown). Periksa lalu tekan Simpan.`);
      } else {
        setNotice(reply?.error ?? `Tidak ada jawaban terakhir di tab ${importProvider}. Tempel manual.`);
      }
    } catch (error) {
      setNotice(`Gagal mengambil jawaban: ${String(error)}. Tempel manual.`);
    } finally {
      setFetchingReply(false);
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
      setPhase('critique');
      await persistMeta(runId, round, 'critique');
      sendRoomTransition('usulan_diterima');
      setNotice('Fase Kritik silang. Susun prompt kritik, salin, dan impor jawaban tiap provider.');
    } else if (phase === 'critique') {
      if (!roundMessages.some((m) => m.phase === 'critique')) {
        setNotice('Belum ada kritik yang diimpor di ronde ini. Impor minimal 1 jawaban dulu.');
        return;
      }
      setPhase('meeting');
      await persistMeta(runId, round, 'meeting');
      sendRoomTransition('kritik_diterima');
      setNotice('Fase Rapat & voting. Susun prompt rapat, salin, dan impor vote tiap provider.');
    } else if (phase === 'meeting') {
      const result = computeConsensus();
      if (!result) {
        setNotice('Belum ada vote yang bisa diparse di ronde ini. Impor jawaban rapat (blok ```json vote) dulu.');
        return;
      }
      if (result.decision === 'mufakat') {
        setPhase('spec');
        await persistMeta(runId, round, 'spec');
        sendRoomTransition('mufakat_atau_juri');
        setNotice(`Mufakat tercapai (pemenang ${result.winner}, approve ${result.winnerApprovals}/${result.votes.length}). Lanjut ke Spesifikasi.`);
      } else if (round >= 3) {
        // M4: ronde 3 tanpa mufakat -> spesifikasi dengan dissent, bukan eskalasi.
        const note = `Ronde 3 tanpa mufakat (keputusan: ${result.decision}, pemenang voting: ${result.winner ?? '—'}, blocking belum dijawab: ${result.blocking}). Juri memutus berdasarkan voting terakhir; keberatan minoritas dilampirkan pada spesifikasi.`;
        setDissent(note);
        setPhase('spec');
        await persistMeta(runId, round, 'spec');
        sendRoomTransition('juri_memutus', note);
        setNotice('Ronde 3 tanpa mufakat — juri memutus, dissent dicatat. Lanjut ke Spesifikasi.');
      } else {
        const nextRound = round + 1;
        setRound(nextRound);
        setPhase('proposal');
        await persistMeta(runId, nextRound, 'proposal');
        sendRoomTransition('belum_mufakat');
        setNotice(`Belum mufakat (keputusan: ${result.decision}). Debat ulang — ronde ${nextRound}, fase Usulan.`);
      }
    } else {
      sendRoomTransition('spek_selesai');
      setNotice('Spesifikasi selesai. Lanjutkan ke coding/review/gates di Local Runner setelah Anda menyetujui patch.');
    }
  }

  async function runDoctor(): Promise<void> {
    const site = selected[0] ?? 'chatgpt';
    setDoctor(await checkCurrentTab(site));
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
        <strong>Mode: Manual Handoff (browser-only).</strong> Extension tidak pernah menekan Kirim.
        Assisted Fill <strong>dihapus dari MVP</strong> (modul opt-in Fase 2, tidak aktif); isi kolom
        otomatis, content-script fill, dan Native Messaging bukan bagian alur utama Room.
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
      <button type="button" onClick={startRun}>Mulai rapat</button>

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
      </label>{' '}
      <button type="button" onClick={fetchLastReply} disabled={!runId || fetchingReply}>
        Ambil jawaban terakhir dari tab
      </button>
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
      <button type="button" onClick={downloadTranscript} disabled={!runId}>Unduh transkrip (.md)</button>

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
          Yang masih manual: login di situs AI, menekan Kirim, mengambil/menempel jawaban,
          menyetujui patch &amp; commit. Local Runner menjalankan gates di Docker setelah
          pengguna menyetujui patch.
        </em>
      </p>
    </div>
  );
}
