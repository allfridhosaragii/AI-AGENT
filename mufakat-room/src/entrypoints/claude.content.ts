// MUFAKAT Room — content script claude (Claude §4).
// Adapter situs: fillInput HANYA mengisi teks (TIDAK kirim), readLastReply
// hanya membaca DOM yang tampil. Selector dari selectors.json (versioned).
// Bila selector gagal -> fallback clipboard + mode Manual Copy.
// Jalur Assisted Fill (opt-in Fase 2, TIDAK aktif di MVP browser-only);
// alur utama Room adalah Manual Handoff.
import { createAdapter, registerAdapterMessages, type SiteSelectors } from '../adapters/base';
import selectorsJson from '../adapters/selectors.json';

const selectors = (selectorsJson.sites as Record<string, SiteSelectors>)['claude'];

export default defineContentScript({
  matches: selectors.matches,
  main() {
    const adapter = createAdapter('claude', 'anthropic', selectors);
    registerAdapterMessages(adapter, selectors);
  },
});
