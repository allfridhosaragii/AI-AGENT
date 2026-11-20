# MUFAKAT Room — Chrome Extension (Browser-Only, Manual Handoff)

> **Status (20 Nov 2026, setelah perbaikan audit):** ekstensi **bisa di-build dan
> lolos typecheck + test** — lihat "Hasil verifikasi" di bawah untuk perintah,
> versi, dan output apa adanya. Mode utama adalah **Manual Handoff**
> (browser-only): pengguna menyalin prompt, menempel di tab resmi provider,
> mengirim sendiri, lalu menempel jawaban kembali ke side panel.
>
> **Assisted Fill dan content script DIHAPUS dari MVP (putaran 2).**
> Tombol "Ambil jawaban terakhir dari tab" dihapus dari side panel;
> handler `FILL_INPUT` / `READ_LAST_REPLY` dihapus dari background;
> 6 content script dipindah ke `src/phase2-optin/content-scripts/` (bukan
> entrypoint WXT, tidak di-build ke manifest); `host_permissions` 6 domain
> dihapus dari `wxt.config.ts`. Native Messaging (Local Runner) tetap ada
> sebagai jalur Fase 2 yang terpisah. Alur utama tidak pernah membaca DOM
> situs AI dan tidak pernah mengisi input — hanya Manual Handoff.
>
> **Risiko terbuka (putaran 2): IndexedDB TANPA enkripsi aplikasi.**
> Data rapat (ide, jawaban impor, state) tersimpan plaintext di IndexedDB
> (Dexie) dan `chrome.storage.local` — siapa pun yang bisa membaca profil
> browser bisa membacanya. Ini BUKAN klaim terenkripsi; enkripsi
> aplikasi tidak dilakukan di MVP (butuh manajemen kunci yang aman, di
> luar lingkup MVP). Mitigasi: jangan masukkan kredensial (secret scanner
> memblokir sebelum simpan) dan hapus data lewat tombol "Hapus seluruh
> data rapat" di side panel. Lihat "Risiko terbuka" di bawah.
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

## Perbaikan audit putaran 2 (2026-11-20)

- **N5:** `labelMap` per ronde di Dexie (`runs.labelMap[round]`) — dibuat
  SEKALI saat masuk fase kritik, dipakai di kritik/rapat/spesifikasi;
  pemenang Borda (label A/B/C) dipetakan lewat labelMap ke proposal yang
  benar (`resolveWinnerProposal`); tanpa labelMap, spesifikasi ditolak —
  JANGAN fallback ke usulan pertama. Prompt kritik tanpa nama provider.
- **N6 + GPT-1:** satu sumber kebenaran = state machine background. Side
  panel meng-await hasil transisi dan menampilkan errornya; ronde baru
  lewat event `ronde_baru` (`debat_ulang` → `usulan_r1`, ronde +1);
  event `reset` pada "Mulai rapat" (rapat kedua bisa dimulai). Test
  integrasi 3 ronde penuh dengan urutan event side panel persis.
- **GPT-2:** buka ulang extension memulihkan ISI IDE (+ peserta, labelMap)
  dari data rapat, bukan hanya ID dan pesan.
- **N10:** ID provider Muse disamakan jadi `muse` di UI, `selectors.json`,
  adapter, dan content script (`metaai` dihapus).
- **N13:** jawaban AI disisipkan hanya sebagai DATA — delimiter
  `--- DATA DARI AI ... ---` + instruksi eksplisit, isi hanya
  summary/claims hasil parse (`engine/promptGuard.ts`).
- **N14:** secret scanner TS menangkap GitLab `glpat-` dan HuggingFace
  `hf_` (block). Catatan: Python `src/mufakat/room/secret_scan.py` BELUM
  punya kedua pola ini — paritas penuh butuh perbaikan di sisi Python.
- **GPT-4:** secret scan SEBELUM `db.runs.add()`; ide berkredensial tidak
  tersimpan; pengguna memilih hapus otomatis (`redactText`) atau sunting
  manual; notice hanya menyebut nama pola, bukan nilai kredensial.
- **GPT-6:** lihat status di atas — content script keluar dari MVP.
- **Tabel tambahan:** tombol "Hapus seluruh data rapat" di side panel
  (Dexie + chrome.storage + reset mesin); Selector Doctor memakai situs
  dari URL tab aktif yang benar-benar dicek (bukan `selected[0]`);
  listener background menolak `ROOM_TRANSITION` dari content script
  (`sender.tab`); IndexedDB tanpa enkripsi didokumentasikan sebagai
  risiko terbuka (bukan klaim terenkripsi).
- **L5:** patch applier runner (`runner/mufakat_runner/worktree.py`) tidak
  lagi menambah `\n` di setiap baris `+`: pakai EOL file asli (CRLF
  dipertahankan, baca/tulis bytes tanpa translasi newline) dan hormati
  penanda `\ No newline at end of file`. Test pytest 4 kasus baru + 1
  ekspektasi lama diperbaiki ke semantik diff standar.
- **.gitignore:** tambah `!.env.example` (pola `.env.*` sebelumnya ikut
  mengabaikan `.env.example`).

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
  saat prompt disalin. (Putaran 2: "Ambil jawaban terakhir dari tab"
  DIHAPUS dari MVP — impor jawaban hanya tempel manual.)
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
- **M8:** (Putaran 2: DIHAPUS dari MVP — `FILL_INPUT` dan content script
  keluar dari jalur utama; lihat status di atas. Bila modul Fase 2
  diaktifkan kembali, `FILL_INPUT` harus mencari tab berdasarkan host
  yang cocok dengan `site` dan menjalankan secret-scan + pacing sebelum
  meneruskan.)
- **M9:** `detectBlocker` cek elemen banner/toast spesifik (`rateLimitIndicator`),
  bukan `body.innerText`; `loginIndicator` (elemen halaman login) dibedakan
  dari input rusak (input hilang → blocker `error`).
- **Selector Doctor:** `lastReplyFound` hasil pemeriksaan nyata dari content
  script, bukan hardcode `true`. (Putaran 2: situs yang dicek diambil dari
  URL tab aktif; di MVP content script tidak aktif sehingga Doctor
  melaporkan modul Fase 2 belum aktif — bukan mengklaim adapter OK.)

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

`sidePanel`, `storage`, `unlimitedStorage`, `clipboardWrite`, `nativeMessaging`.
(Putaran 2: `host_permissions` 6 domain AI DIHAPUS — tidak ada content
script di MVP, jadi extension tidak butuh akses host ke situs AI.)
DILARANG: `cookies`, `webRequest`, `declarativeNetRequest`, `debugger`,
`scripting` injeksi bebas, `<all_urls>`.

## Struktur

```text
src/
  entrypoints/
    background.ts        # orkestrator (state machine persisten + pacing + parser; TANPA FILL_INPUT/READ_LAST_REPLY)
    sidepanel/           # React app (App.tsx) — UI Manual Handoff (alur penuh)
  phase2-optin/
    README.md            # status modul opt-in Fase 2 (tidak aktif di MVP)
    content-scripts/     # 6 adapter situs (defineContentScript) — TIDAK terdaftar di manifest MVP
  adapters/
    base.ts              # interface SiteAdapter + fillInput/readLastReply (turndown) — HANYA untuk modul Fase 2
    selectors.json       # selector per situs (versioned; lastVerified = belum terverifikasi)
    doctor.ts            # Selector Doctor (situs dari URL tab aktif; lastReplyFound nyata)
  engine/
    stateMachine.ts      # alur Claude §2 (ronde 3 -> spesifikasi + dissent; snapshot/restore; ronde_baru + reset)
    prompts/*.md         # template per peran & fase
    parser.ts            # blok ```json terakhir + fallback objek {...} terakhir
    consensus.ts         # anonimisasi (seed acak), Borda, 2/3, blocking resolved; resolveWinnerProposal
    promptGuard.ts       # N13: delimiter DATA + summary/claims hasil parse
    senderGuard.ts       # validasi sender pesan background (tolak content script)
    pacing.ts            # jeda 20 dtk/situs, batas harian default 40
    antiLoop.ts          # hash diff+temuan
    secretScan.ts        # blok kredensial sebelum kirim/simpan (+ JWT, glpat-, hf_; .env = warn)
  storage/
    db.ts                # Dexie: runs (+labelMap per ronde), messages, gateResults, usage
    roomState.ts         # state rapat persisten (chrome.storage.session + local)
    export.ts            # ekspor transkrip .md / .json
  native/
    runnerClient.ts      # chrome.runtime.connectNative('com.mufakat.runner') — legacy Fase 2
  ui/                    # Timeline, VoteTable, GateReport
tests/
  engine.test.ts         # vitest: parser, konsensus, pacing, anti-loop, secret scan
  audit-regressions.test.ts  # vitest: regresi M2-M9 + pacing recordPrompt (20 test)
  audit-round2.test.ts   # vitest: regresi putaran 2 (N5, N6, N10, N13, N14, GPT-4, GPT-6, sender/doctor)
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
3. Menempel jawaban AI secara manual ke side panel (tombol "Ambil jawaban
   terakhir dari tab" DIHAPUS dari MVP putaran 2).
4. Menyetujui patch / commit di Local Runner (tombol Approve).

## Risiko terbuka (jangan klaim sudah tertutup)

- **IndexedDB tanpa enkripsi aplikasi.** Data rapat — ide, jawaban AI
  yang diimpor, labelMap, state rapat — tersimpan **plaintext** di
  IndexedDB (Dexie) dan `chrome.storage.local` di profil browser pengguna.
  Siapa pun yang bisa membaca profil browser (akses fisik ke mesin,
  malware, backup profil yang bocor) bisa membaca data rapat. Extension
  ini TIDAK mengklaim data terenkripsi. Enkripsi di level aplikasi belum
  dilakukan di MVP: butuh manajemen kunci (mis. kunci turunan dari
  passphrase pengguna via WebCrypto + salt) yang aman, dan itu di luar
  lingkup MVP. Mitigasi yang sudah ada: secret scanner memblokir
  penyimpanan ide/jawaban yang mengandung kredensial; tombol "Hapus
  seluruh data rapat" di side panel menghapus Dexie + chrome.storage +
  reset state machine; transkrip yang diunduh juga plaintext — simpan di
  tempat yang aman.
- **Selector belum terverifikasi** (`selectors.json`,
  `lastVerified: "belum terverifikasi"`).

## Yang masih tersisa (bukan bagian tugas ini)

- Verifikasi selector di situs AI asli (butuh Chrome + login provider).
- Uji klik side panel end-to-end di Chrome sungguhan (vitest hanya menguji
  engine; App.tsx belum diuji lewat browser).
- H6 (native host path/token), C1–C3, H1/H3/H4/H7 — dikerjakan worker lain.
