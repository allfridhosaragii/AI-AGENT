// MUFAKAT Room — content script chatgpt (Claude §4).
// Adapter situs: fillInput HANYA mengisi teks (TIDAK kirim), readLastReply
// hanya membaca DOM yang tampil. Selector dari selectors.json (versioned).
// Bila selector gagal -> fallback clipboard + mode Manual Copy.
import {
  detectBlockerGeneric,
  fillInputGeneric,
  isGeneratingGeneric,
  readLastReplyGeneric,
  type SiteAdapter,
  type SiteSelectors,
} from '../adapters/base';
import selectorsJson from '../adapters/selectors.json';

const selectors = (selectorsJson.sites as Record<string, SiteSelectors>)['chatgpt'];

export const adapter: SiteAdapter = {
  id: 'chatgpt',
  family: 'openai',
  matches: selectors.matches,
  isLoggedIn: () => detectBlockerGeneric(selectors) !== 'logged_out',
  detectBlocker: () => detectBlockerGeneric(selectors),
  fillInput: (text: string) => fillInputGeneric(selectors, text),
  isGenerating: () => isGeneratingGeneric(selectors),
  readLastReply: () => readLastReplyGeneric(selectors),
};

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
    sendResponse({
      ok: true,
      id: adapter.id,
      loggedIn: adapter.isLoggedIn(),
      blocker: adapter.detectBlocker(),
      generating: adapter.isGenerating(),
    });
    return true;
  }
  return false;
});
