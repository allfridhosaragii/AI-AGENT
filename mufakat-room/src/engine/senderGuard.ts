// MUFAKAT Room — Sender Guard (tabel tambahan ChatGPT, putaran 2).
// Listener chrome.runtime.onMessage di background WAJIB memvalidasi sender:
// pesan ROOM_TRANSITION (dan dulu FILL_INPUT) hanya boleh datang dari
// halaman extension (side panel) — BUKAN dari content script di situs AI.
// Content script selalu membawa `sender.tab`; halaman extension tidak.
// Pesan dari tab (content script) ditolak agar situs AI / skrip yang
// disuntikkan ke halaman tidak bisa menggerakkan state machine rapat.
export interface MessageSenderLike {
  id?: string;
  tab?: unknown;
  url?: string;
  origin?: string;
}

export function isTrustedRoomSender(sender: MessageSenderLike | undefined | null): boolean {
  if (!sender) return false;
  // Content script (dan halaman web biasa) selalu punya sender.tab.
  if (sender.tab) return false;
  // Halaman extension punya url chrome-extension:// (atau moz-extension://).
  // sender.url kosong (mis. dari background sendiri) tetap diizinkan.
  if (typeof sender.url === 'string' && sender.url !== '') {
    if (!sender.url.startsWith('chrome-extension://') && !sender.url.startsWith('moz-extension://')) {
      return false;
    }
  }
  return true;
}
