// MUFAKAT Room — Native Messaging client (Claude §5).
// Jembatan aman ekstensi <-> Local Runner via chrome.runtime.connectNative.
// TIDAK membuka port jaringan. Host hanya menerima perintah dari ID
// ekstensi yang terdaftar (allowed_origins di manifest host).
//
// Alur persetujuan commit (audit putaran 2, N3/GPT 3) — token HANYA
// terbit setelah manusia terlibat DI LUAR kanal ekstensi:
//   1. requestApproval(port, runId) -> host menampilkan kode 6 digit
//      lewat dialog OS / terminal host (bukan lewat kanal ini) +
//      mengembalikan approval_id + diff_hash + diff_stat.
//   2. Manusia membaca kode dari dialog OS dan mengetiknya di side
//      panel -> confirmApproval(port, runId, approvalId, code).
//   3. issueApprovalToken(port, runId, diffHash) -> token sekali pakai
//      terikat hash diff + branch + worktree.
//   4. commit(port, runId, message, token).
// `register_repo` TIDAK ADA di kanal ini: repo hanya didaftarkan lewat
// CLI lokal `mufakat-room-runner register <nama> <path>`.
// Side panel (App.tsx) BELUM memanggil helper ini — penyambungan UI
// (tampilkan diff_stat + input kode 6 digit) masih pekerjaan lanjutan.
const HOST_NAME = 'com.mufakat.runner';

export interface RunnerResponse {
  ok: boolean;
  error?: string;
  [key: string]: unknown;
}

export function connectRunner(onMessage: (message: RunnerResponse) => void): chrome.runtime.Port {
  const port = chrome.runtime.connectNative(HOST_NAME);
  port.onMessage.addListener((message: RunnerResponse) => onMessage(message));
  port.onDisconnect.addListener(() => {
    const error = chrome.runtime.lastError?.message ?? 'Runner terputus.';
    onMessage({ ok: false, error });
  });
  return port;
}

export function sendToRunner(port: chrome.runtime.Port, message: Record<string, unknown>): void {
  port.postMessage(message);
}

/** Langkah 1: minta persetujuan — host menampilkan kode 6 digit di dialog OS. */
export function requestApproval(port: chrome.runtime.Port, runId: string): void {
  port.postMessage({ command: 'request_approval', run_id: runId });
}

/** Langkah 2: manusia mengetik kode 6 digit dari dialog OS di side panel. */
export function confirmApproval(
  port: chrome.runtime.Port,
  runId: string,
  approvalId: string,
  code: string,
): void {
  port.postMessage({ command: 'confirm_approval', run_id: runId, approval_id: approvalId, code });
}

/** Langkah 3: terbitkan token sekali pakai (hanya setelah confirm_approval). */
export function issueApprovalToken(port: chrome.runtime.Port, runId: string, diffHash: string): void {
  port.postMessage({ command: 'issue_approval_token', run_id: runId, diff_hash: diffHash });
}

/** Langkah 4: commit dengan token sekali pakai. */
export function commitWithApproval(
  port: chrome.runtime.Port,
  runId: string,
  message: string,
  approvalToken: string,
): void {
  port.postMessage({ command: 'commit', run_id: runId, message, approval_token: approvalToken });
}
