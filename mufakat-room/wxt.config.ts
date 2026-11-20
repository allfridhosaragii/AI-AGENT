import { defineConfig } from 'wxt';

// MUFAKAT Room — manifest MV3, permission MINIMAL (Claude §7).
// DILARANG menambah: cookies, webRequest, declarativeNetRequest, debugger,
// scripting injeksi bebas, atau <all_urls>.
// Putaran 2 (GPT-6): host_permissions 6 domain AI DIHAPUS — content script
// tidak lagi terdaftar di MVP (modul opt-in Fase 2 di src/phase2-optin/,
// tidak aktif), jadi extension tidak butuh akses host ke situs AI.
export default defineConfig({
  // H2: entrypoints ada di src/, bukan root — tanpa ini wxt build
  // gagal "No entrypoints found".
  srcDir: 'src',
  manifest: {
    name: 'MUFAKAT Room',
    description:
      'Moderator rapat multi-AI via login browser. Semi-manual: Anda yang menekan Kirim.',
    permissions: ['sidePanel', 'storage', 'unlimitedStorage', 'clipboardWrite', 'nativeMessaging'],
    side_panel: {
      default_path: 'sidepanel.html',
    },
  },
});
