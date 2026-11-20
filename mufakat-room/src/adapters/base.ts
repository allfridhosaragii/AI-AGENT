// MUFAKAT Room — SiteAdapter interface + util bersama (Claude §4).
// ATURAN KERAS: fillInput HANYA mengisi teks. TIDAK PERNAH mengklik tombol
// Kirim, men-dispatch Enter, atau submit form. TIDAK membaca cookie/token/
// localStorage situs AI. Hanya membaca DOM yang sudah tampil di layar.
// Modul ini adalah jalur Assisted Fill (opt-in Fase 2, TIDAK aktif di MVP
// browser-only); alur utama Room adalah Manual Handoff.
import TurndownService from 'turndown';

export type SiteId = 'chatgpt' | 'claude' | 'gemini' | 'deepseek' | 'qwen' | 'metaai';
export type Blocker = 'captcha' | 'rate_limit' | 'logged_out' | 'error' | null;

export interface SiteAdapter {
  id: SiteId;
  family: 'openai' | 'anthropic' | 'google' | 'deepseek' | 'qwen' | 'meta';
  matches: string[];
  isLoggedIn(): boolean;
  detectBlocker(): Blocker;
  fillInput(text: string): Promise<boolean>;
  isGenerating(): boolean;
  readLastReply(): { text: string; html: string; markdown: string } | null;
}

export interface SiteSelectors {
  input: string;
  sendButton?: string;
  lastMessage: string;
  generatingIndicator?: string;
  /** Selector elemen yang HANYA muncul di halaman login (mis. tombol
   *  "Log in"). M9: dibedakan dari input — loginIndicator = null berarti
   *  "belum terverifikasi, jangan klaim logged_out dari input yang hilang". */
  loginIndicator?: string | null;
  /** Selector elemen yang HANYA muncul saat sudah login (mis. avatar /
   *  menu pengguna). Null = belum terverifikasi. */
  loggedInIndicator?: string | null;
  captchaIndicator?: string | null;
  /** M9: selector banner/toast rate-limit SPESIFIK (mis. toast "Too many
   *  requests"). Null = belum terverifikasi. Jangan pernah memakai
   *  body.innerText: AI yang membahas rate limiting ikut terdeteksi. */
  rateLimitIndicator?: string | null;
  matches: string[];
}

const turndown = new TurndownService();

export function createAdapter(id: SiteId, family: SiteAdapter['family'], selectors: SiteSelectors): SiteAdapter {
  return {
    id,
    family,
    matches: selectors.matches,
    isLoggedIn: () => isLoggedInGeneric(selectors),
    detectBlocker: () => detectBlockerGeneric(selectors),
    fillInput: (text: string) => fillInputGeneric(selectors, text),
    isGenerating: () => isGeneratingGeneric(selectors),
    readLastReply: () => readLastReplyGeneric(selectors),
  };
}

function setNativeValue(element: HTMLTextAreaElement | HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set
    ?? Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event('input', { bubbles: true }));
}

/** Isi teks ke kolom input. Untuk contenteditable pakai insertText; untuk
 *  textarea/input pakai native setter + event input. TIDAK mengirim. */
export async function fillInputGeneric(selectors: SiteSelectors, text: string): Promise<boolean> {
  const input = document.querySelector<HTMLElement>(selectors.input);
  if (!input) return false;
  input.focus();
  if (input.isContentEditable) {
    return document.execCommand('insertText', false, text);
  }
  if (input instanceof HTMLTextAreaElement || input instanceof HTMLInputElement) {
    setNativeValue(input, text);
    return true;
  }
  return false;
}

/** Ambil pesan asisten terakhir yang tampil di layar (DOM saja).
 *  M3: kembalikan juga Markdown via turndown (innerText menghilangkan
 *  struktur; HTML mentah sulit diparse). */
export function readLastReplyGeneric(selectors: SiteSelectors): { text: string; html: string; markdown: string } | null {
  const messages = document.querySelectorAll(selectors.lastMessage);
  const last = messages[messages.length - 1] as HTMLElement | undefined;
  if (!last) return null;
  const html = last.innerHTML ?? '';
  return { text: last.innerText ?? '', html, markdown: turndown.turndown(html) };
}

/** M9: cek elemen banner/toast SPESIFIK, bukan body.innerText.
 *  'logged_out' hanya bila elemen halaman login ketemu; input yang hilang
 *  adalah 'error' (selector rusak / halaman belum termuat) — keduanya
 *  dibedakan agar login dan input rusak tidak tertukar. */
export function detectBlockerGeneric(selectors: SiteSelectors): Blocker {
  if (selectors.captchaIndicator && document.querySelector(selectors.captchaIndicator)) {
    return 'captcha';
  }
  if (selectors.loginIndicator && document.querySelector(selectors.loginIndicator)) {
    return 'logged_out';
  }
  if (selectors.rateLimitIndicator && document.querySelector(selectors.rateLimitIndicator)) {
    return 'rate_limit';
  }
  if (!document.querySelector(selectors.input)) {
    return 'error';
  }
  return null;
}

/** Login = indikator "sudah login" ada, ATAU (bila belum terverifikasi)
 *  tidak ada indikator halaman login dan input ditemukan. */
export function isLoggedInGeneric(selectors: SiteSelectors): boolean {
  if (selectors.loggedInIndicator) return Boolean(document.querySelector(selectors.loggedInIndicator));
  if (selectors.loginIndicator && document.querySelector(selectors.loginIndicator)) return false;
  return Boolean(document.querySelector(selectors.input));
}

export function isGeneratingGeneric(selectors: SiteSelectors): boolean {
  if (!selectors.generatingIndicator) return false;
  return Boolean(document.querySelector(selectors.generatingIndicator));
}

/** Handler pesan bersama untuk semua content script situs: FILL_INPUT,
 *  READ_LAST_REPLY, ADAPTER_STATUS (untuk Selector Doctor). */
export function registerAdapterMessages(adapter: SiteAdapter, selectors: SiteSelectors): void {
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === 'FILL_INPUT') {
      adapter
        .fillInput(String(message.text ?? ''))
        .then((ok) => sendResponse({ ok, filled: ok }))
        .catch((error: unknown) => sendResponse({ ok: false, error: String(error) }));
      return true;
    }
    if (message?.type === 'READ_LAST_REPLY') {
      const reply = adapter.readLastReply();
      sendResponse({ ok: reply !== null, reply });
      return true;
    }
    if (message?.type === 'ADAPTER_STATUS') {
      const reply = adapter.readLastReply();
      sendResponse({
        ok: true,
        id: adapter.id,
        loggedIn: adapter.isLoggedIn(),
        inputFound: Boolean(document.querySelector(selectors.input)),
        lastReplyFound: reply !== null,
        blocker: adapter.detectBlocker(),
        generating: adapter.isGenerating(),
      });
      return true;
    }
    return false;
  });
}
