# MUFAKAT Room — Chrome Extension (Browser-Only, Manual Handoff)

> **Status (20 Nov 2026, setelah perbaikan audit):** ekstensi **bisa di-build dan
> lolos typecheck + test** — lihat "Hasil verifikasi" di bawah untuk perintah,
> versi, dan output apa adanya. Mode utama adalah **Manual Handoff**
> (browser-only): pengguna menyalin prompt, menempel di tab resmi provider,
> mengirim sendiri, lalu menempel jawaban kembali ke side panel.
>
> **Assisted Fill DIHAPUS dari MVP.** Checkbox "Aktifkan Assisted Fill" sudah
> dihapus dari UI utama. Content script fill, `FILL_INPUT`, dan Native
> Messaging tetap ada di repo sebagai **modul opsional/legacy Fase 2 yang
> tidak aktif** — tidak dipakai alur utama Room. Alur utama tidak memanggil
> `FILL_INPUT` sama sekali.
>
> **Yang BELUM terverifikasi:** selector situs (`selectors.json`,
> `lastVerified: "belum terverifikasi"`) — belum pernah diuji di situs AI
> asli, dan tidak ada Chrome + login provider di VM ini untuk mengujinya.
> Sampai terverifikasi, extension jatuh ke mode Manual Copy bila Selector
> Doctor menandai adapter rusak. Jangan menganggap flow end-to-end di situs
> asli sudah jalan sebelum diuji di Chrome sungguhan dengan login provider.

## Hasil verifikasi (dijalankan 20 Nov 2026, 12:45 UTC)

Lingkungan: Node v24.22.1, npm 10.9.4, WXT 0.19.29, TypeScript 5.x, vitest 2.1.9.
`pnpm` tidak tersedia di VM ini — dipakai `npm` (sesuai tugas).

| Perintah | Hasil |
|---|---|
| `npm install` (sebelum perbaikan) | ❌ `ETARGET: No matching version found for @types/turndown@^4.0.0` |
| `npm install` (setelah `@types/turndown` → `^5.0.5`) | ✅ `added 540 packages`; lockfile `package-lock.json` dibuat (275 KB) |
| `npm run typecheck` (`wxt prepare && tsc --noEmit`) | ✅ exit 0, tanpa error |
| `npm test` (`vitest run`) | ✅ `Test Files 2 passed (2)`, `Tests 33 passed (33)` — 13 lama + 20 regresi audit baru |
| `npm run build` (`wxt build`) | ✅ `Built extension in 4.7 s`, total 554.88 kB; manifest MV3 + 6 content script + side panel + background SW |

## Perbaikan audit 2026-11-20 (ringkas; detail per file di bawah)

- **H2:** `@types/turndown` → `^5.0.5`; `srcDir: 'src'` di `wxt.config.ts`;
  `tsconfig.json` extends `./.wxt/tsconfig.json` (+ `jsx: react-jsx`); semua
  `*.content.ts` dibungkus `export default defineContentScript({ matches, main })`;
  `background.ts` dibungkus `export default defineBackground(...)`; CI job
  `extension` di root `.github/workflows/ci.yml` (pakai `npm ci` + Node 24).
  File workflow di root repo **tidak bisa di-push via API** (GitHub memblokir
  upload workflow untuk App tanpa izin workflows) — tambahkan manual via web
  GitHub bila belum ada.
- **H5:** side panel tersambung penuh — alur Ide → Usulan → Kritik silang →
  Rapat & voting (Borda) → Spesifikasi; tombol Simpan jawaban menyimpan ke
  Dexie (`db.messages.add`) dengan provider/ronde/fase tercatat dan baru
  menampilkan "disimpan" setelah `add` berhasil; `recordPrompt` per provider
  saat prompt disalin; "Ambil jawaban terakhir dari tab" memakai turndown.
- **M2:** secret scanner TS disamakan dengan Python + JWT; `.env` hanya
  peringatan (`severity: 'warn'`), bukan blokir; impor jawaban di-scan
  SEBELUM disimpan.
- **M3:** parser mengizinkan `\s*` setelah `json` dan fallback objek `{...}`
  terakhir yang valid (innerText tanpa pagar); `readLastReply` memakai turndown.
- **M4:** ronde 3 tanpa mufakat → `spesifikasi` dengan `dissent`, bukan eskalasi.
- **M5:** state machine disimpan persisten di `chrome.storage.session` +
  `chrome.storage.local` (`storage/roomState.ts`), bukan variabel modul SW.
- **M6:** seed anonimisasi dari `crypto.getRandomValues` per ronde bila seed
  tidak diberikan.
- **M7:** kritik blocking punya status `resolved`; `approveRatio` terikat ke
  pemenang Borda.
- **M8:** `FILL_INPUT` di background mencari tab berdasarkan host yang cocok
  dengan `site`, menjalankan secret-scan + pacing sebelum meneruskan.
- **M9:** `detectBlocker` cek elemen banner/toast spesifik (`rateLimitIndicator`),
  bukan `body.innerText`; `loginIndicator` (elemen halaman login) dibedakan
  dari input rusak (input hilang → blocker `error`).
- **Selector Doctor:** `lastReplyFound` hasil pemeriksaan nyata dari content
  script, bukan hardcode `true`.

## Disclaimer ToS (Claude §0.4)

> "Mengotomasi web chat bisa melanggar Ketentuan Layanan penyedia AI. MUFAKAT Room
> dirancang semi-manual (Anda yang menekan Kirim) untuk meminimalkan risiko, tetapi
> risiko pembatasan akun tetap ada dan menjadi tanggung jawab pengguna. Gunakan akun
> sendiri, untuk proyek sendiri, dengan kecepatan wajar."

## Instalasi

```bash
cd mufakat-room
npm install   # atau: npm ci   (bila package-lock.json sudah ada)
npm run dev   # membuka Chrome dengan side panel "MUFAKAT Room"
```

Lalu **Load unpacked** folder `.output/chrome-mv3` di `chrome://extensions`.

## Permission manifest (final, tidak boleh ditambah tanpa alasan tertulis)

`sidePanel`, `storage`, `unlimitedStorage`, `clipboardWrite`, `nativeMessaging`,
plus host_permissions HANYA 6 domain: `chatgpt.com`, `claude.ai`,
`gemini.google.com`, `chat.deepseek.com`, `chat.qwen.ai`, `www.meta.ai`.
DILARANG: `cookies`, `webRequest`, `declarativeNetRequest`, `debugger`,
`scripting` injeksi bebas, `<all_urls>`.

## Struktur

```text
src/
  entrypoints/
    background.ts        # orkestrator (state machine persisten + pacing + parser + FILL_INPUT per situs)
    sidepanel/           # React app (App.tsx) — UI Manual Handoff (alur penuh)
    chatgpt.content.ts   # adapter per situs (defineContentScript; delegasi ke adapters/base.ts)
    claude.content.ts
    gemini.content.ts
    deepseek.content.ts
    qwen.content.ts
    metaai.content.ts
  adapters/
    base.ts              # interface SiteAdapter + fillInput/readLastReply (turndown) + detectBlocker
    selectors.json       # selector per situs (versioned; lastVerified = belum terverifikasi)
    doctor.ts            # Selector Doctor (lastReplyFound nyata)
  engine/
    stateMachine.ts      # alur Claude §2 (ronde 3 -> spesifikasi + dissent; snapshot/restore)
    prompts/*.md         # template per peran & fase
    parser.ts            # blok ```json terakhir + fallback objek {...} terakhir
    consensus.ts         # anonimisasi (seed acak), Borda, 2/3, blocking resolved
    pacing.ts            # jeda 20 dtk/situs, batas harian default 40
    antiLoop.ts          # hash diff+temuan
    secretScan.ts        # blok kredensial sebelum kirim/simpan (+ JWT; .env = warn)
  storage/
    db.ts                # Dexie: runs, messages, gateResults, usage
    roomState.ts         # state rapat persisten (chrome.storage.session + local)
    export.ts            # ekspor transkrip .md / .json
  native/
    runnerClient.ts      # chrome.runtime.connectNative('com.mufakat.runner') — legacy Fase 2
  ui/                    # Timeline, VoteTable, GateReport
tests/
  engine.test.ts         # vitest: parser, konsensus, pacing, anti-loop, secret scan
  audit-regressions.test.ts  # vitest: regresi M2-M9 + pacing recordPrompt (20 test)
```

## Selector

Semua selector CSS ada di `src/adapters/selectors.json` (bukan hardcode), dengan
`version` dan `lastVerified`. Nilai `lastVerified` saat ini
**"belum terverifikasi"** — selector HARUS diverifikasi manual di tiap situs
dan diperbarui saat situs berubah. `loginIndicator`, `loggedInIndicator`, dan
`rateLimitIndicator` sengaja `null`: nilai yang salah menyebabkan false
positive (mis. `loginIndicator` = selector input membuat "login" dan "input
rusak" tak bisa dibedakan). Isi ketiganya hanya setelah diverifikasi di situs
asli. Bila selector rusak, extension otomatis jatuh ke mode Manual Copy
(Selector Doctor).

## Yang masih manual (dilakukan pengguna di website AI)

1. Login di tiap situs AI (tab resmi provider).
2. Menekan tombol **Kirim** — selalu manusia, tidak pernah extension.
3. Menekan **"Ambil jawaban"** (atau menempel jawaban manual bila selector rusak).
4. Menyetujui patch / commit di Local Runner (tombol Approve).

## Yang masih tersisa (bukan bagian tugas ini)

- Verifikasi selector di situs AI asli (butuh Chrome + login provider).
- Uji klik side panel end-to-end di Chrome sungguhan (vitest hanya menguji
  engine; App.tsx belum diuji lewat browser).
- H6 (native host path/token), C1–C3, H1/H3/H4/H7 — dikerjakan worker lain.
