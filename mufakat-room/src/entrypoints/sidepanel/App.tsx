// MUFAKAT Room — Side Panel App (Claude §T7).
// Mode default: MANUAL HANDOFF. Pengguna menyalin prompt, mengirim sendiri
// di tab resmi provider, lalu menempel jawaban kembali. Assisted Fill hanya
// muncul bila pengguna mengaktifkannya (opt-in Fase 2) — dan tetap TIDAK
// pernah menekan Kirim.
import React, { useState } from 'react';
import { scanText } from '../engine/secretScan';
import { checkPacing } from '../engine/pacing';

const PROVIDERS = [
  { id: 'chatgpt', name: 'ChatGPT', url: 'https://chatgpt.com/', status: 'Manual handoff only' },
  { id: 'claude', name: 'Claude', url: 'https://claude.ai/', status: 'Manual handoff only' },
  { id: 'gemini', name: 'Gemini', url: 'https://gemini.google.com/', status: 'Manual handoff only' },
  { id: 'deepseek', name: 'DeepSeek', url: 'https://chat.deepseek.com/', status: 'Manual handoff only' },
  { id: 'qwen', name: 'Qwen', url: 'https://chat.qwen.ai/', status: 'Manual handoff only' },
  { id: 'muse', name: 'Muse', url: 'https://www.meta.ai/', status: 'Needs policy review' },
];

const TOS_DISCLAIMER =
  'Mengotomasi web chat bisa melanggar Ketentuan Layanan penyedia AI. MUFAKAT Room ' +
  'dirancang semi-manual (Anda yang menekan Kirim) untuk meminimalkan risiko, tetapi ' +
  'risiko pembatasan akun tetap ada dan menjadi tanggung jawab pengguna. Gunakan akun ' +
  'sendiri, untuk proyek sendiri, dengan kecepatan wajar.';

export default function App(): React.ReactElement {
  const [idea, setIdea] = useState('');
  const [selected, setSelected] = useState<string[]>(['chatgpt', 'claude', 'gemini']);
  const [prompt, setPrompt] = useState('');
  const [imported, setImported] = useState('');
  const [notice, setNotice] = useState('');
  const [assistedFill, setAssistedFill] = useState(false);

  function toggleProvider(id: string): void {
    setSelected((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]));
  }

  function buildPrompt(): void {
    const text =
      `Kamu adalah debater dalam rapat multi-AI. Ide yang dibahas:\n${idea}\n\n` +
      'Buat usulan solusi yang konkret dan mandiri. Tulis penjelasan singkat, lalu akhiri ' +
      'dengan SATU blok ```json sesuai skema.';
    const findings = scanText(text);
    if (findings.length) {
      setNotice(`Prompt diblokir secret scanner: ${findings.map((f) => f.pattern).join(', ')}. Hapus kredensial dari ide.`);
      return;
    }
    setPrompt(text);
    setNotice('Prompt siap. Salin, tempel di tab resmi provider, dan tekan Kirim sendiri.');
  }

  async function copyPrompt(): Promise<void> {
    if (!prompt) return;
    const decision = await checkPacing(selected[0] ?? 'chatgpt');
    if (!decision.allowed) {
      setNotice(`Pacing: ${decision.reason}`);
      return;
    }
    await navigator.clipboard.writeText(prompt);
    setNotice('Prompt disalin. Tempel di tab resmi provider dan tekan Kirim sendiri.');
  }

  function openOfficialSite(url: string): void {
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: 16, maxWidth: 640 }}>
      <h1>MUFAKAT Room</h1>
      <p style={{ background: '#fff3cd', padding: 8, borderRadius: 4 }}>{TOS_DISCLAIMER}</p>
      <p>
        <strong>Mode: Manual Handoff (default).</strong> Extension tidak pernah menekan Kirim.
        Assisted Fill (isi kolom otomatis) adalah opt-in Fase 2:{' '}
        <label>
          <input type="checkbox" checked={assistedFill} onChange={(e) => setAssistedFill(e.target.checked)} /> Aktifkan Assisted Fill
        </label>
      </p>

      <h2>1. Ide</h2>
      <textarea
        value={idea}
        onChange={(e) => setIdea(e.target.value)}
        placeholder="Tulis ide / permintaan..."
        rows={4}
        style={{ width: '100%' }}
      />

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

      <h2>3. Prompt ronde ini</h2>
      <button type="button" onClick={buildPrompt}>Susun prompt</button>{' '}
      <button type="button" onClick={copyPrompt} disabled={!prompt}>Salin prompt</button>
      {prompt && <pre style={{ whiteSpace: 'pre-wrap', background: '#f5f5f5', padding: 8 }}>{prompt}</pre>}

      <h2>4. Impor jawaban (tempel dari tab resmi)</h2>
      <textarea
        value={imported}
        onChange={(e) => setImported(e.target.value)}
        placeholder="Tempel jawaban AI di sini. Jawaban disimpan dengan label 'user imported'."
        rows={6}
        style={{ width: '100%' }}
      />
      <button
        type="button"
        onClick={() => {
          if (!imported.trim()) return;
          setNotice('Jawaban disimpan sebagai "user imported" (provider, ronde, waktu impor dicatat).');
          setImported('');
        }}
      >
        Simpan jawaban impor
      </button>

      {notice && <p role="status" style={{ background: '#e7f3ff', padding: 8 }}>{notice}</p>}

      <h2>Timeline ronde</h2>
      <p>Ide → Usulan R1 → Kritik silang → Rapat → Spesifikasi → Coding → Review → Gates → Approve.</p>
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
