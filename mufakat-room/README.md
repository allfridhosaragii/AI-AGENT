# MUFAKAT Room — Chrome Extension (Assisted Fill, Fase 2, OPT-IN)

> **Status scaffold (20 Nov 2026):** struktur file + kode TypeScript sudah ditulis
> mengikuti Claude §6–§7, **tetapi belum pernah dijalankan** — `pnpm` tidak tersedia
> di VM ini sehingga `pnpm install` / `pnpm dev` **belum terverifikasi**. Jangan
> menganggap extension ini sudah jalan sebelum diuji di Chrome sungguhan.
>
> **PENTING — baca dulu:** mode default MUFAKAT Room adalah **Manual Handoff**
> (V3 §2.2 Mode B): pengguna menyalin prompt, menempel di tab resmi provider,
> mengirim sendiri, lalu menempel jawaban kembali. Extension ini adalah modul
> **opt-in Fase 2** yang HANYA mengisi teks ke kolom chat (Assisted Fill) dan
> membaca jawaban saat pengguna memintanya. Extension **tidak pernah** menekan
> tombol Kirim/Enter, tidak membaca cookie/token, dan tidak memakai otomasi
> browser lain. Lihat `../README.md` bagian MUFAKAT Room untuk konflik
> Claude vs V3 dan cara penyelesaiannya.

## Disclaimer ToS (Claude §0.4)

> "Mengotomasi web chat bisa melanggar Ketentuan Layanan penyedia AI. MUFAKAT Room
> dirancang semi-manual (Anda yang menekan Kirim) untuk meminimalkan risiko, tetapi
> risiko pembatasan akun tetap ada dan menjadi tanggung jawab pengguna. Gunakan akun
> sendiri, untuk proyek sendiri, dengan kecepatan wajar."

## Instalasi (setelah diverifikasi)

```bash
cd mufakat-room
pnpm install
pnpm dev        # membuka Chrome dengan side panel "MUFAKAT Room"
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
    background.ts        # orkestrator (state machine + pacing + parser)
    sidepanel/           # React app (App.tsx) — UI Manual Handoff + Assisted Fill
    chatgpt.content.ts   # adapter per situs (delegasi ke adapters/base.ts)
    claude.content.ts
    gemini.content.ts
    deepseek.content.ts
    qwen.content.ts
    metaai.content.ts
  adapters/
    base.ts              # interface SiteAdapter + fillInput/readLastReply
    selectors.json       # selector per situs (versioned; lastVerified = belum terverifikasi)
    doctor.ts            # Selector Doctor
  engine/
    stateMachine.ts      # alur Claude §2
    prompts/*.md         # template per peran & fase
    parser.ts            # blok ```json terakhir + status ok/repair_needed/unparsed
    consensus.ts         # anonimisasi, Borda, 2/3, blocking, devil's advocate
    pacing.ts            # jeda 20 dtk/situs, batas harian default 40
    antiLoop.ts          # hash diff+temuan
    secretScan.ts        # blok kredensial sebelum kirim
  storage/
    db.ts                # Dexie: runs, messages, gateResults, usage
    export.ts            # ekspor transkrip .md / .json
  native/
    runnerClient.ts      # chrome.runtime.connectNative('com.mufakat.runner')
  ui/                    # Timeline, VoteTable, GateReport
tests/
  engine.test.ts         # vitest: parser, konsensus, pacing, anti-loop, secret scan
```

## Selector

Semua selector CSS ada di `src/adapters/selectors.json` (bukan hardcode), dengan
`version` dan `lastVerified`. Nilai `lastVerified` saat ini
**"belum terverifikasi"** — selector HARUS diverifikasi manual di tiap situs
dan diperbarui saat situs berubah. Bila selector rusak, extension otomatis
jatuh ke mode Manual Copy (Selector Doctor).

## Yang masih manual (dilakukan pengguna di website AI)

1. Login di tiap situs AI (tab resmi provider).
2. Menekan tombol **Kirim** — selalu manusia, tidak pernah extension.
3. Menekan **"Ambil jawaban"** (atau menempel jawaban manual bila selector rusak).
4. Menyetujui patch / commit di Local Runner (tombol Approve).
