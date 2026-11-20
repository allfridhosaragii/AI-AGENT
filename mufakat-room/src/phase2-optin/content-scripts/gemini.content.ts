// MUFAKAT Room — content script gemini (Claude §4) — OPT-IN FASE 2, TIDAK AKTIF DI MVP.
// Adapter situs: fillInput HANYA mengisi teks (TIDAK kirim), readLastReply
// hanya membaca DOM yang tampil. Selector dari selectors.json (versioned).
// Bila selector gagal -> fallback clipboard + mode Manual Copy.
// Jalur Assisted Fill (opt-in Fase 2); alur utama Room adalah Manual Handoff.
// File ini TIDAK terdaftar sebagai entrypoint WXT (di luar src/entrypoints/)
// sehingga TIDAK di-build ke manifest MVP — lihat ../README.md.
import { createAdapter, registerAdapterMessages, type SiteSelectors } from '../../adapters/base';
import selectorsJson from '../../adapters/selectors.json';

const selectors = (selectorsJson.sites as Record<string, SiteSelectors>)['gemini'];

export default defineContentScript({
  matches: selectors.matches,
  main() {
    const adapter = createAdapter('gemini', 'google', selectors);
    registerAdapterMessages(adapter, selectors);
  },
});
