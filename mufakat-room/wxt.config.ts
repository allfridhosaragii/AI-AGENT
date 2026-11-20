import { defineConfig } from 'wxt';

// MUFAKAT Room — manifest MV3, permission MINIMAL (Claude §7).
// DILARANG menambah: cookies, webRequest, declarativeNetRequest, debugger,
// scripting injeksi bebas, atau <all_urls>. Host permissions hanya 6 domain.
export default defineConfig({
  // H2: entrypoints ada di src/, bukan root — tanpa ini wxt build
  // gagal "No entrypoints found".
  srcDir: 'src',
  manifest: {
    name: 'MUFAKAT Room',
    description:
      'Moderator rapat multi-AI via login browser. Semi-manual: Anda yang menekan Kirim.',
    permissions: ['sidePanel', 'storage', 'unlimitedStorage', 'clipboardWrite', 'nativeMessaging'],
    host_permissions: [
      'https://chatgpt.com/*',
      'https://claude.ai/*',
      'https://gemini.google.com/*',
      'https://chat.deepseek.com/*',
      'https://chat.qwen.ai/*',
      'https://www.meta.ai/*',
    ],
    side_panel: {
      default_path: 'sidepanel.html',
    },
  },
});
