// MUFAKAT Room — Native Messaging client (Claude §5).
// Jembatan aman ekstensi <-> Local Runner via chrome.runtime.connectNative.
// TIDAK membuka port jaringan. Host hanya menerima perintah dari ID
// ekstensi yang terdaftar (allowed_origins di manifest host).
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
