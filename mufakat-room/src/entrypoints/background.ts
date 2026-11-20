// MUFAKAT Room — Background Service Worker (orkestrator).
// State machine + penyusun prompt + pacing/limit + parser jawaban.
// TIDAK ADA auto-send: background tidak pernah mengklik tombol Kirim atau
// men-dispatch event Enter. TIDAK ADA polling background: pembacaan jawaban
// hanya terjadi saat pengguna menekan "Ambil jawaban" di side panel.
import { createDebateMachine } from '../engine/stateMachine';
import { parseReply } from '../engine/parser';
import { checkPacing } from '../engine/pacing';
import { scanText } from '../engine/secretScan';

export interface FillRequest {
  type: 'FILL_INPUT';
  site: string;
  text: string;
}

export interface ReadRequest {
  type: 'READ_LAST_REPLY';
  site: string;
}

const machine = createDebateMachine();

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'ROOM_STATE') {
    sendResponse({ state: machine.getState() });
    return true;
  }
  if (message?.type === 'SECRET_SCAN') {
    sendResponse({ findings: scanText(String(message.text ?? '')) });
    return true;
  }
  if (message?.type === 'PACING_CHECK') {
    sendResponse(checkPacing(String(message.site ?? '')));
    return true;
  }
  if (message?.type === 'PARSE_REPLY') {
    sendResponse(parseReply(String(message.text ?? ''), Boolean(message.repairAttempted)));
    return true;
  }
  // FILL_INPUT / READ_LAST_REPLY diteruskan ke content script tab aktif;
  // content script yang mengeksekusi fillInput/readLastReply di halaman.
  if (message?.type === 'FILL_INPUT' || message?.type === 'READ_LAST_REPLY') {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tabId = tabs[0]?.id;
      if (tabId === undefined) {
        sendResponse({ ok: false, error: 'Tidak ada tab aktif.' });
        return;
      }
      chrome.tabs.sendMessage(tabId, message, (reply) => {
        sendResponse(reply ?? { ok: false, error: 'Content script tidak menjawab.' });
      });
    });
    return true; // respons asinkron
  }
  return false;
});

// Side panel dibuka lewat klik ikon ekstensi.
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error('sidePanel behavior gagal:', error));
