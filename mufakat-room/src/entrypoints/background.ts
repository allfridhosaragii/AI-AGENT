// MUFAKAT Room — Background Service Worker (orkestrator).
// State machine + penyusun prompt + pacing/limit + parser jawaban.
// TIDAK ADA auto-send: background tidak pernah mengklik tombol Kirim atau
// men-dispatch event Enter. TIDAK ADA polling background.
// M5: state machine disimpan PERSISTEN (chrome.storage.session + local
// via storage/roomState.ts), bukan variabel modul — SW MV3 tidur setelah
// ±30 detik idle.
// Putaran 2 (GPT-6): handler FILL_INPUT dan READ_LAST_REPLY DIHAPUS dari
// MVP — content script tidak lagi terdaftar (modul opt-in Fase 2 di
// src/phase2-optin/, tidak aktif), jadi background tidak pernah membaca
// DOM situs AI atau mengisi input. Jalur MVP: Manual Handoff saja.
// Tabel tambahan (putaran 2): ROOM_TRANSITION hanya diterima dari halaman
// extension (side panel) — pesan dari content script (sender.tab) DITOLAK
// via isTrustedRoomSender.
import { createDebateMachine, type DebateMachine } from '../engine/stateMachine';
import { parseReply } from '../engine/parser';
import { checkPacing } from '../engine/pacing';
import { scanText } from '../engine/secretScan';
import { isTrustedRoomSender } from '../engine/senderGuard';
import { loadRoomState, saveRoomState } from '../storage/roomState';

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

export default defineBackground(() => {
  void ensureMachineLoaded();

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type === 'ROOM_STATE') {
      void ensureMachineLoaded().then(() => {
        sendResponse({ state: machine.getState(), round: machine.getRound(), dissent: machine.getDissent() });
      });
      return true;
    }
    if (message?.type === 'ROOM_TRANSITION') {
      // Validasi sender: hanya halaman extension (side panel) yang boleh
      // menggerakkan state machine; content script di situs AI ditolak.
      if (!isTrustedRoomSender(sender)) {
        sendResponse({
          ok: false,
          error: 'ROOM_TRANSITION ditolak: hanya halaman extension yang boleh mengirim transisi (bukan content script).',
        });
        return true;
      }
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
    return false;
  });

  // Side panel dibuka lewat klik ikon ekstensi.
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((error) => console.error('sidePanel behavior gagal:', error));
});
