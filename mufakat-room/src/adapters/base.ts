// MUFAKAT Room — SiteAdapter interface + util bersama (Claude §4).
// ATURAN KERAS: fillInput HANYA mengisi teks. TIDAK PERNAH mengklik tombol
// Kirim, men-dispatch Enter, atau submit form. TIDAK membaca cookie/token/
// localStorage situs AI. Hanya membaca DOM yang sudah tampil di layar.
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
  readLastReply(): { text: string; html: string } | null;
}

export interface SiteSelectors {
  input: string;
  sendButton?: string;
  lastMessage: string;
  generatingIndicator?: string;
  loginIndicator?: string;
  captchaIndicator?: string;
  matches: string[];
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

/** Ambil pesan asisten terakhir yang tampil di layar (DOM saja). */
export function readLastReplyGeneric(selectors: SiteSelectors): { text: string; html: string } | null {
  const messages = document.querySelectorAll(selectors.lastMessage);
  const last = messages[messages.length - 1] as HTMLElement | undefined;
  if (!last) return null;
  return { text: last.innerText ?? '', html: last.innerHTML ?? '' };
}

export function detectBlockerGeneric(selectors: SiteSelectors): Blocker {
  if (selectors.captchaIndicator && document.querySelector(selectors.captchaIndicator)) {
    return 'captcha';
  }
  if (selectors.loginIndicator && !document.querySelector(selectors.loginIndicator)) {
    return 'logged_out';
  }
  if (document.body.innerText.toLowerCase().includes('too many requests')) {
    return 'rate_limit';
  }
  return null;
}

export function isGeneratingGeneric(selectors: SiteSelectors): boolean {
  if (!selectors.generatingIndicator) return false;
  return Boolean(document.querySelector(selectors.generatingIndicator));
}
