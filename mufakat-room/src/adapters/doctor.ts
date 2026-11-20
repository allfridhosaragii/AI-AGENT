// MUFAKAT Room — Selector Doctor (Claude §4, §T10).
// Halaman tes di side panel: mengecek tiap adapter di tab yang sedang
// dibuka (input ketemu? pesan terakhir terbaca?) dan menandai adapter
// rusak -> otomatis pakai mode Manual Copy. Doctor TIDAK mengirim apa pun
// dan TIDAK membaca di background; pengecekan hanya di tab aktif pengguna.
// Perbaikan audit: lastReplyFound HARUS hasil pemeriksaan nyata dari
// content script (ADAPTER_STATUS), bukan hardcode true.
export type AdapterHealth = 'ok' | 'rusak' | 'belum_dicek';

export interface DoctorResult {
  site: string;
  health: AdapterHealth;
  inputFound: boolean;
  lastReplyFound: boolean;
  blocker: string | null;
  detail: string;
}

/** Minta content script tab aktif melaporkan status adapter-nya. */
export async function checkCurrentTab(site: string): Promise<DoctorResult> {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tabId = tabs[0]?.id;
  if (tabId === undefined) {
    return { site, health: 'belum_dicek', inputFound: false, lastReplyFound: false, blocker: null, detail: 'Tidak ada tab aktif.' };
  }
  try {
    const reply = await chrome.tabs.sendMessage(tabId, { type: 'ADAPTER_STATUS' });
    // Hasil pemeriksaan nyata: inputFound & lastReplyFound dari DOM tab.
    // lastReplyFound=false BUKAN rusak — wajar bila belum ada percakapan;
    // health 'rusak' hanya bila input hilang atau ada blocker.
    const inputFound = Boolean(reply?.inputFound ?? reply?.loggedIn);
    const lastReplyFound = Boolean(reply?.lastReplyFound);
    const blocker = reply?.blocker ?? null;
    const health: AdapterHealth = blocker ? 'rusak' : inputFound ? 'ok' : 'rusak';
    return {
      site,
      health,
      inputFound,
      lastReplyFound,
      blocker,
      detail: blocker
        ? `Blocker terdeteksi: ${blocker}. Run dihentikan untuk situs ini.`
        : inputFound
          ? lastReplyFound
            ? 'Adapter OK (input ditemukan, jawaban terakhir terbaca, tidak ada blocker).'
            : 'Adapter OK (input ditemukan, tidak ada blocker). Belum ada jawaban terakhir di tab ini — wajar bila percakapan baru.'
          : 'Input tidak ditemukan — selector mungkin sudah berubah. Pakai Manual Copy.',
    };
  } catch {
    return {
      site,
      health: 'rusak',
      inputFound: false,
      lastReplyFound: false,
      blocker: null,
      detail: 'Content script tidak menjawab (tab bukan situs AI / extension belum dimuat). Pakai Manual Copy.',
    };
  }
}
