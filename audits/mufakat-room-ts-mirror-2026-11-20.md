# AUDIT — MUFAKAT ROOM TypeScript Extension Mirror (`mufakat-room/`)

Tanggal: 2026-11-20 (WIB, ~11:10). Auditor: proactivity research run.
Alasan: audit ekstrem 2 putaran 2026-11-20 hanya mengaudit website Room + kode
Python; mirror TypeScript extension tercatat belum diaudit (MEMORY.md).
Audit ini menutup celah itu. Ini BUKAN putaran ke-3 audit website/Python.

## Ruang lingkup & metode

Dibaca penuh (total ~1.077 baris TS/TSX + `selectors.json`):
`src/engine/secretScan.ts`, `pacing.ts`, `consensus.ts`, `antiLoop.ts`,
`parser.ts`, `stateMachine.ts`, `src/storage/db.ts`, `src/storage/export.ts`,
`src/adapters/base.ts`, `src/adapters/doctor.ts`,
`src/entrypoints/background.ts`, `src/entrypoints/sidepanel/App.tsx`,
6 content script adapter, `tests/engine.test.ts`, `package.json`, `wxt.config.ts`.
Dibandingkan pola per pola dengan `src/mufakat/room/secret_scan.py`
(versi pasca-perbaikan audit Python 20 Nov 2026) dan dengan temuan audit
website R1-01..R1-09 di `audits/mufakat-room-2026-11-20.md`.

Verifikasi empiris (bukan sekadar baca kode):
- Node v24.22.1 menjalankan `consensus.ts` ASLI (type stripping):
  vote tanpa `ranking` -> `TypeError: Cannot read properties of undefined
  (reading 'forEach')`; vote `ranking` string -> `TypeError: ranking.forEach
  is not a function`. Seri 1-1 -> `{decision:'tie', winner:null}`.
- Pola regex `secretScan.ts` diuji ulang terhadap 4 token telanjang:
  `sk-proj-...`, `github_pat_...`, `AIza...` (35 karakter), `xoxb-...` ->
  semuanya LOLOS (tidak ada pola yang cocok). `gho_...` dan `sk-ant-...`
  tertangkap. Hasil ini direplikasi dari pola verbatim di file.
- Grep seluruh `src/`: `recordPrompt` TIDAK PERNAH dipanggil di mana pun;
  `db` tidak pernah diimpor di `sidepanel/App.tsx`; `decideConsensus`
  tidak pernah dipanggil di luar definisinya (belum terhubung ke UI).

Belum diverifikasi di run ini: `pnpm test` / `pnpm build` (pnpm tidak ada di
VM ini, sama seperti catatan sebelumnya); uji live di 6 situs AI
(`selectors.json` sendiri menyatakan "belum terverifikasi", tebakan awal).

## Yang TIDAK memblokir uji nyata hari ini

Uji nyata pertama (instruksi 2026-11-20 03:14 UTC) memakai website Room
via Manual Handoff, BUKAN extension. Extension adalah opt-in Fase 2
(Assisted Fill, default nonaktif). Temuan di bawah ini memblokir pemakaian
extension nanti, bukan uji nyata hari ini. Jangan tunda uji nyata karena
audit ini.

## Temuan

### T1 [HIGH] Secret Scanner TS lolos 4 keluarga token yang baru saja diperbaiki di Python
- Lokasi: `src/engine/secretScan.ts` (8 pola).
- Gejala: token telanjang lolos: `sk-proj-...` (pola `sk-` butuh 20
  alfanumerik berturut-turut; `proj-` mengandung `-` sehingga gagal),
  `github_pat_...` (pola `gh[pousr]_` tidak cocok dengan `github_pat_`),
  `AIza...` (tidak ada pola Google), `xoxb-...` (tidak ada pola Slack).
  Ini persis 4 pola yang ditambahkan di Python pasca-audit
  (`secret_scan.py`: `sk-(?:proj-)?`, `github_pat_`, `AIza[0-9A-Za-z\-_]{35}`,
  `xox[baprs]-`). Kasus terbungkus assignment (`OPENAI_API_KEY=sk-proj-...`)
  sebagian tertangkap pola generik `credential_assignment`, tapi token
  telanjang dalam teks/JSON tidak.
- Perbaikan: port 4 pola Python verbatim ke `PATTERNS` (plus
  `private_key_block` flag `i`, seperti Python). Tambah test: keempat token
  telanjang di atas harus `scanText(...).length > 0`.

### T2 [HIGH] Side panel "Simpan jawaban impor" membuang jawaban yang ditempel
- Lokasi: `src/entrypoints/sidepanel/App.tsx`, tombol impor.
- Gejala: `onClick` hanya `setNotice(...)` + `setImported('')`. Tidak ada
  `scanText`, tidak ada `parseReply`, tidak ada `db.messages.add`, tidak
  ada penanda provider/ronde/fase. Jawaban yang ditempel pengguna hilang
  begitu tombol ditekan, tanpa penyimpanan apa pun.
- Perbaikan: sebelum simpan, jalankan `scanText` (blokir bila ada temuan),
  `parseReply` (simpan `parseStatus`), lalu `db.messages.add` dengan
  `runId/round/phase/provider/source:'user imported'`; tampilkan status
  parse ke pengguna. Ini prasyarat agar impor extension bisa ikut Borda.

### T3 [HIGH] Pacing extension tidak pernah ditegakkan — `recordPrompt` mati
- Lokasi: `src/engine/pacing.ts` + `src/entrypoints/sidepanel/App.tsx`
  `copyPrompt` + `src/entrypoints/background.ts`.
- Gejala: `recordPrompt` (satu-satunya penulis `lastSent`/`daily` di
  ledger) tidak dipanggil di file mana pun. `copyPrompt` hanya memanggil
  `checkPacing(selected[0])` lalu `clipboard.writeText` — ledger tidak
  pernah bertambah, jadi batas 20 detik dan 40/hari tidak pernah tercapai.
  Bonus: pengecekan hanya memakai provider pertama yang dipilih, bukan
  tiap situs yang disalin; tombol Salin tidak disabled saat request berjalan
  (risiko klik ganda, sama kelasnya dengan website R1-09).
- Perbaikan: setelah `clipboard.writeText` sukses, panggil
  `recordPrompt(site)` untuk situs yang bersangkutan; cek pacing per situs
  saat menyalin; disable tombol selama proses; tambah jalur `RECORD_PROMPT`
  di background bila check/record dipisah proses.

### T4 [HIGH] Borda crash pada vote impor malformed — sama seperti website R1-02
- Lokasi: `src/engine/consensus.ts`, `decideConsensus` -> `bordaCount`.
- Gejala (terbukti node pada file asli): vote tanpa `ranking` melempar
  `TypeError`; `ranking` string melempar `TypeError`. Parser zod di
  `parser.ts` memvalidasi bentuk saat impor, tapi `decideConsensus` tidak
  punya guard sendiri dan akan crash bila dipanggil dengan data apa pun di
  luar jalur parser (atau bila skema berubah).
- Perbaikan: di `decideConsensus`, lewati vote yang `ranking`-nya bukan
  array string (atau normalisasi ke `[]` + tandai tidak valid); jangan
  biarkan satu vote merusak seluruh rapat. Tambah test regresi untuk kedua
  kasus crash di atas.

### T5 [MEDIUM] `MAX_TOTAL_ITERATIONS = 12` tidak pernah mengikat (TS mirror dari R1 website)
- Lokasi: `src/engine/stateMachine.ts`, `createDebateMachine`.
- Gejala: `totalIterations` hanya bertambah pada event `revisi_selesai`,
  bersamaan dengan `fixIterations` — keduanya selalu sama, jadi
  `fixIterations >= 5` selalu memicu eskalasi lebih dulu; batas total 12
  mati. `debat_lanjut` tidak menambah `totalIterations` sama sekali.
- Perbaikan: tambah `totalIterations` pada setiap transisi iterasi
  (`debat_lanjut`, `revisi_selesai`, dst.) atau hapus konstanta bila memang
  tidak dipakai; tambah test: 12 iterasi campuran -> eskalasi.

### T6 [MEDIUM] Batas repair 1x hanya dikontrol pemanggil (mirror R1-07)
- Lokasi: `src/engine/parser.ts` (`repairAttempted` parameter) +
  `background.ts` (`PARSE_REPLY` memakai `Boolean(message.repairAttempted)`).
- Gejala: tidak ada penghitung sisi penyimpanan; pemanggil mana pun bisa
  mengirim `repairAttempted: false` berulang kali dan mendapat
  `repairPrompt` baru tanpa batas.
- Perbaikan: hitung pesan `parseStatus:'repair_needed'` untuk run/fase
  berjalan dari `db.messages` sebelum mengizinkan repair; bila sudah >= 1,
  paksa `unparsed`.

### T7 [MEDIUM] Secret mentah tersimpan & diekspor verbatim di extension
- Lokasi: `src/storage/db.ts` (`MessageRecord.rawText`) +
  `src/storage/export.ts` (`renderTranscriptMarkdown` + `exportRun`).
- Gejala: `rawText` disimpan apa adanya di IndexedDB; ekspor Markdown/JSON
  menyertakan `rawText` verbatim. Komentar export ("Tidak ada rahasia yang
  diekspor (prompt sudah lolos secret scan)") tidak benar selama T1 belum
  diperbaiki — token yang lolos scanner akan ikut tersimpan dan tereksport.
  Ini pola yang sama dengan `room.json` plaintext di website.
- Perbaikan: redaksi saat simpan/ekspor (pakai pola scanner yang sudah
  diperbaiki), atau simpan payload ter-parse saja + `rawText` ter-redaksi;
  perbaiki komentar agar jujur.

### T8 [MEDIUM] Vote ranking kosong ikut penyebut; seri tanpa tie-break (mirror R1-05)
- Lokasi: `src/engine/consensus.ts`.
- Gejala: vote `ranking: []` tetap dihitung di `votes.length` (penyebut
  `approveRatio`) tapi menyumbang 0 poin Borda; kandidat 0 poin tetap
  muncul di hasil; seri dikembalikan sebagai `decision:'tie'` tanpa aturan
  pemutus yang terdokumentasi.
- Perbaikan: lewati vote ranking kosong dari penyebut (atau tolak saat
  impor); tambah tie-break deterministik (poin -> jumlah approve -> label
  alfabetis) dan tampilkan.

### T9 [LOW] Selector Doctor melaporkan `lastReplyFound: true` secara hardcoded
- Lokasi: `src/adapters/doctor.ts`, `checkCurrentTab`.
- Gejala: `lastReplyFound: true` ditulis literal dengan komentar "dicek
  terpisah"; `inputFound` sebenarnya memakai `reply.loggedIn`
  (keberadaan indikator login), bukan keberadaan input. Status "Adapter OK"
  bisa tampil padahal balasan terakhir belum pernah dicek.
- Perbaikan: panggil `readLastReply` di content script untuk status
  adapter, atau ubah field menjadi `lastReplyChecked: false` yang jujur.

### T10 [LOW] Parser JSON butuh newline setelah ```json
- Lokasi: `src/engine/parser.ts`, `JSON_BLOCK_RE = /```(?:json)?\s*\n(.*?)```/gis`.
- Gejala: jawaban ```json {"phase": ...}``` sebaris (tanpa newline) tidak
  cocok -> `unparsed`, padahal JSON-nya valid.
- Perbaikan: longgarkan ke /```(?:json)?\s*(.*?)```/gis dengan guard
  tetap mengambil blok terakhir.

## Yang terverifikasi BERSIH di mirror ini

- Anti-loop (`antiLoop.ts`): arah SUDAH benar — `stagnantFindings` memakai
  `>=` setelah push (temuan tidak turun 3 observasi -> eskalasi). Ini
  kebalikan dari bug website R1-01 yang terbalik; tidak perlu diperbaiki.
  Catatan kecil: `hashCounts`/`findingCounts` hanya in-memory, hilang saat
  reload — bukan bug eskalasi, tapi batas yang patut dicatat.
- State machine menolak transisi ilegal (test ada, logika `TRANSITIONS`
  konsisten); parser zod memvalidasi `vote.ranking` array di jalur impor.
- Secret scan menangkap `gho_/ghu_/ghs_/ghr_`, `sk-ant-`, `AKIA`, blok
  private key, dan assignment `password:`/`apiKey:` (case-insensitive).
- Adapter mematuhi §0 di permukaan: `fillInputGeneric` hanya mengisi teks,
  tidak ada klik Kirim / Enter / submit; tidak ada akses cookie/token/
  localStorage situs AI di `base.ts`; `selectors.json` jujur menyatakan
  "belum terverifikasi".

## Masih terbuka (di luar mirror, dicatat agar tidak hilang)

- `selectors.json` v1: 6 situs, semua "tebakan awal BELUM diuji di halaman
  asli" — perlu verifikasi manual per situs via Selector Doctor.
- Website Room: sebagian perbaikan putaran 2 baru diverifikasi lewat
  pembacaan kode + typecheck, belum uji klik live di browser.
- `.github/workflows/ci.yml` tetap harus ditambah manual via web GitHub
  (GitHub memblokir file workflow lewat API).

## Saran langkah berikutnya (untuk keputusan owner)

1. Terapkan patch T1–T4 dulu (secret scanner, impor tidak hilang, pacing
   ditegakkan, Borda tahan malformed) — keempatnya HIGH dan semuanya punya
   spesifikasi patch eksak di atas.
2. Jalankan `pnpm test` (tambah test regresi T1/T4/T5) + `pnpm build` +
   `tsc --noEmit`, lalu push ke `allfridhosaragii/AI-AGENT` seperti pola
   push sebelumnya.
3. Baru setelah itu uji Assisted Fill di 1 situs (ChatGPT) dengan Selector
   Doctor; extension tetap opt-in Fase 2, Manual Handoff tetap default.

## Addendum — Patch T1–T4 diterapkan (2026-11-20 ~12:05 WIB, proactivity run)

Patch T1–T4 sudah diterapkan ke file lokal (BELUM di-push ke GitHub):

- **T1** `src/engine/secretScan.ts`: port verbatim 4 pola Python
  (`github_pat_`, `sk-(?:proj-)?`, `AIza…{35}`, `xox[baprs]-`) + flag `i`
  pada `private_key_block`.
- **T2** `src/entrypoints/sidepanel/App.tsx`: `saveImported()` baru —
  `scanText` (blokir bila ada temuan) → `parseReply` (status parse
  dicatat) → `db.messages.add` (`runId: 'sidepanel-manual'`, round 1,
  fase dari payload parse atau `'proposal'`, provider dipilih via
  dropdown baru, `source: 'user imported'`). Gagal simpan tidak
  menghapus teks tempelan.
- **T3** `App.tsx` `copyPrompt()`: cek pacing per situs yang dipilih,
  `recordPrompt(site)` dipanggil setelah `clipboard.writeText` sukses,
  tombol Salin di-disable selama proses.
- **T4** `src/engine/consensus.ts`: `bordaCount` dan `decideConsensus`
  melewati vote yang `ranking`-nya bukan array string (bukan crash);
  vote malformed tidak dihitung di penyebut `approveRatio`.
- Test regresi ditambah di `tests/engine.test.ts` (T1: 4 token telanjang;
  T4: vote tanpa ranking / ranking string).

**Temuan baru saat menerapkan patch (T11, HIGH — luput dari audit ini):**
`App.tsx` mengimpor `'../engine/secretScan'` dan `'../engine/pacing'`,
yang menunjuk ke `src/entrypoints/engine/` — direktori itu TIDAK ADA,
jadi side panel tidak bisa di-build. Sudah diperbaiki ke
`'../../engine/...'` (dan impor baru `parser`/`db` memakai path yang
benar). Verifikasi filesystem: `src/entrypoints/engine` tidak ada;
keempat target `../../engine/secretScan|pacing|parser` dan
`../../storage/db` ada.

**Verifikasi empiris run ini (Node v24.22.1, type stripping, file asli):**
`/tmp/verify-ts-patch.mjs` — 11/11 PASS: keempat token T1 tertangkap,
`gho_`/`sk-ant-` tetap tertangkap, teks bersih lolos, vote malformed
tidak crash (winner A), kasus mufakat normal tidak berubah
(Borda A=4, winner A).

**Masih BELUM terverifikasi / belum dilakukan:** `pnpm test` +
`pnpm build` + `tsc --noEmit` (pnpm tetap tidak ada di VM ini, sama
seperti catatan sebelumnya) — App.tsx dan test baru belum lolos
typecheck/build; push ke `allfridhosaragii/AI-AGENT` belum dilakukan.
T5–T10 belum dikerjakan.
