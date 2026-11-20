// MUFAKAT Room — Background Service Worker (orkestrator).
// State machine + penyusun prompt + pacing/limit + parser jawaban.
// TIDAK ADA auto-send: background tidak pernah mengklik tombol Kirim atau
// men-dispatch event Enter. TIDAK ADA polling background: pembacaan jawaban
// hanya terjadi saat pengguna menekan "Ambil jawaban" di side panel.
// M5: state machine disimpan PERSISTEN (chrome.storage.session + local
// via storage/roomState.ts), bukan variabel modul — SW MV3 tidur setelah
// ±30 detik idle. M8: FILL_INPUT mencari tab berdasarkan host yang cocok
// dengan site, dan menjalankan secret-scan + pacing SEBELUM meneruskan.
import { createDebateMachine, type DebateMachine } from '../engine/stateMachine';
import { parseReply } from '../engine/parser';
import { checkPacing, recordPrompt } from '../engine/pacing';
import { blockingFindings, scanText } from '../engine/secretScan';
import { loadRoomState, saveRoomState } from '../storage/roomState';
import selectorsJson from '../adapters/selectors.json';
import type { SiteSelectors } from '../adapters/base';

export interface FillRequest {
  type: 'FILL_INPUT';
  site: string;
  text: string;
}

export interface ReadRequest {
  type: 'READ_LAST_REPLY';
  site: string;
}

const SITE_MATCHES: Record<string, string[]> = Object.fromEntries(
  Object.entries(selectorsJson.sites as Record<string, SiteSelectors>).map(([id, s]) => [id, s.matches]),
);

const machine: DebateMachine = createDebateMachine();
let machineReady: Promise<void> | null = null;

function ensureMachineLoaded(): Promise<void> {
  if (!machineReady) {
    machineReady = loadRoomState()
      .then((snapshot) => {
        if (snapshot) machine.restore(snapshot);
      })
      .catch((error) => console.error('Gagal memuat state rapat:', error));
  }
  return machineReady;
}

async function persistMachine(): Promise<void> {
  await saveRoomState(machine.getSnapshot());
}

/** M8: cari tab berdasarkan host yang cocok dengan site (bukan tab aktif
 *  mana pun). Kembalikan id tab pertama yang cocok, atau null. */
async function findTabForSite(site: string): Promise<number | null> {
  const matches = SITE_MATCHES[site];
  if (!matches) return null;
  const tabs = await chrome.tabs.query({ url: matches });
  return tabs[0]?.id ?? null;
}

export default defineBackground(() => {
  void ensureMachineLoaded();

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === 'ROOM_STATE') {
      void ensureMachineLoaded().then(() => {
        sendResponse({ state: machine.getState(), round: machine.getRound(), dissent: machine.getDissent() });
      });
      return true;
    }
    if (message?.type === 'ROOM_TRANSITION') {
      void ensureMachineLoaded()
        .then(async () => {
          const next = machine.transition(String(message.event ?? ''), message.note ? String(message.note) : undefined);
          await persistMachine();
          sendResponse({ ok: true, state: next, round: machine.getRound(), dissent: machine.getDissent() });
        })
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    if (message?.type === 'SECRET_SCAN') {
      sendResponse({ findings: scanText(String(message.text ?? '')) });
      return true;
    }
    if (message?.type === 'PACING_CHECK') {
      void checkPacing(String(message.site ?? '')).then((decision) => sendResponse(decision));
      return true;
    }
    if (message?.type === 'PARSE_REPLY') {
      sendResponse(parseReply(String(message.text ?? ''), Boolean(message.repairAttempted)));
      return true;
    }
    // M8: FILL_INPUT — secret-scan + pacing di background SEBELUM
    // meneruskan ke content script tab yang host-nya cocok dengan site.
    if (message?.type === 'FILL_INPUT') {
      const site = String(message.site ?? '');
      const text = String(message.text ?? '');
      void (async () => {
        const blocking = blockingFindings(scanText(text));
        if (blocking.length) {
          sendResponse({ ok: false, error: `Diblokir secret scanner: ${blocking.map((f) => f.pattern).join(', ')}` });
          return;
        }
        const decision = await checkPacing(site);
        if (!decision.allowed) {
          sendResponse({ ok: false, error: `Pacing: ${decision.reason}` });
          return;
        }
        const tabId = await findTabForSite(site);
        if (tabId === null) {
          sendResponse({ ok: false, error: `Tidak ada tab ${site} yang terbuka. Buka situs resmi provider dulu.` });
          return;
        }
        await recordPrompt(site);
        chrome.tabs.sendMessage(tabId, message, (reply) => {
          sendResponse(reply ?? { ok: false, error: 'Content script tidak menjawab.' });
        });
      })().catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true; // respons asinkron
    }
    // READ_LAST_REPLY — ke tab yang host-nya cocok dengan site; balasan
    // content script sudah berisi Markdown via turndown (M3).
    if (message?.type === 'READ_LAST_REPLY') {
      const site = String(message.site ?? '');
      void (async () => {
        const tabId = await findTabForSite(site);
        if (tabId === null) {
          sendResponse({ ok: false, error: `Tidak ada tab ${site} yang terbuka.` });
          return;
        }
        chrome.tabs.sendMessage(tabId, message, (reply) => {
          sendResponse(reply ?? { ok: false, error: 'Content script tidak menjawab.' });
        });
      })().catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true; // respons asinkron
    }
    return false;
  });

  // Side panel dibuka lewat klik ikon ekstensi.
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((error) => console.error('sidePanel behavior gagal:', error));
});
