# AUDIT EKSTREM 2 PUTARAN — MUFAKAT ROOM (artifact slug `mufakat`)
Tanggal: 2026-11-20 (WIB). Auditor: subagent audit (depth 2/2).

> **Catatan ruang lingkup (ditambah 20 Nov 2026, perbaikan dokumentasi):**
> semua path file di laporan ini (`client/src/App.tsx`,
> `server/src/actions.ts`, `server/src/schema.ts`, `client/src/api.ts`,
> `client/src/reference.ts`, `client/src/main.tsx`, `client/index.html`,
> `client/src/theme.css`) adalah file **internal website artifact slug
> `mufakat`** — BUKAN file di repo `~/workspace/mufakat/` dan jangan
> dicari di sana. `audits/latest/` yang disebut di bawah juga milik
> builder artifact, bukan direktori repo.

Sumber yang dibaca penuh: `client/src/App.tsx` (919 baris), `client/src/reference.ts` (249),
`server/src/actions.ts` (2050 baris), `server/src/schema.ts` (228),
`client/src/api.ts`, `client/src/main.tsx`, `client/index.html`, `client/src/theme.css` (parsial),
audit builder terakhir `audits/latest/` (2026-11-20T01:50Z).

## BLOKIR KRITIS — TIDAK ADA EDIT YANG DITERAPKAN

`artifact.edit` (juga `artifact.status` / `artifact.list`) **tidak tersedia untuk subagent ini**.
`tool_search.load_tool_namespace(["artifact"])` dipanggil 2x dan hanya mengembalikan 3 fungsi:
`artifact.restore`, `artifact.share`, `artifact.unshare`. Tidak ada cara yang sah bagi
subagent ini untuk memanggil `artifact.edit` (skemanya tidak ada di konteks).
`AGENTS.md` di `ts-spaces/mufakat/` juga melarang hand-edit `ts-spaces/` dan `bun run build`.
Karena itu **nol baris kode diubah** — audit ini menghasilkan daftar bug + spesifikasi
patch eksak di bawah, siap dieksekusi oleh builder (parent agent harap spawn builder
dengan akses `artifact.edit`). Jangan klaim bug-bug ini "sudah diperbaiki" sebelum
builder mengeksekusi patch dan build/audit builder lolos.

## BASELINE / VERIFIKASI SEBELUM PERBAIKAN

- Audit builder terakhir (v3, 2026-11-20T01:50Z): nav HTTP 200, mobile overflow 0px
  (viewport 390, scroll_width 390), tidak ada kontrol tak terjangkau, tidak ada
  console error. Satu-satunya temuan: teks crew terpotong (kosmetik) + Google Fonts
  diblokir egress (fallback font sistem, bukan bug fungsional).
- Verifikasi logika kritis dilakukan dengan mengekstrak fungsi **verbatim** dari
  `actions.ts`/`reference.ts` ke `/tmp/mufakat_audit_test.mjs` dan
  `/tmp/mufakat_audit_test2.mjs`, dijalankan dengan node v24 — hasilnya dikutip
  pada tiap bug (R1-01, R1-02, R1-05, R1-11). Bukan re-implementasi, melainkan
  salinan persis kode produksi.
- Keamanan (grep + baca kode): TIDAK ada `dangerouslySetInnerHTML`, `document.cookie`,
  `localStorage`/`sessionStorage`, iframe, atau fetch ke situs AI. Satu-satunya
  `fetch` server adalah ke `baseUrl` API resmi provider (`/chat/completions`,
  `/models`) + `ctx.inference`. Tidak ada klaim "Connected" palsu: status web
  selalu `manual_handoff`/`needs_verification`/`unsupported`; "Official Connected"
  hanya muncul bila `testConnection` ke API resmi berhasil. Klaim ini **lolos**.

---

# PUTARAN 1 — BUG DITEMUKAN (12 bug, 3 HIGH)

## R1-01 [HIGH] Anti-loop `stalled` TERBALIK — progres bagus dieskalasi, regresi dibiarkan
- Lokasi: `server/src/actions.ts`, `advanceRun`, cabang `gate`/`final_audit`:
  `const stalled = lastTwo.length === 2 && lastTwo.every((s) => s.findings >= findingsCount) && failedGates.length > 0;`
- Gejala: `lastTwo` = 2 entri SEBELUM push saat ini. `s.findings >= findingsCount`
  benar bila temuan TURUN/tetap (progres bagus) → eskalasi. Bila temuan NAIK
  (regresi) → tidak eskalasi, revisi dilanjutkan. Kebalikan total dari spek
  "temuan tidak turun 2 iterasi berturut-turut → eskalasi".
- Bukti node (verbatim): temuan 6→4→2 → eval ke-3 `{stalled:true, escalate:true}`;
  temuan 2→4→6 → eval ke-3 `{stalled:false, escalate:false}`.
- Perbaikan: balik operator menjadi `s.findings <= findingsCount`
  (eskalasi bila temuan saat ini TIDAK LEBIH RENDAH dari 2 iterasi sebelumnya),
  dan hitung dari `seen` SETELAH push entri saat ini agar "2 iterasi
  berturut-turut" mencakup iterasi berjalan, atau dokumentasikan jendela 3 evaluasi.
  Uji regresi: 6→4→2 tidak eskalasi; 5→5→5 eskalasi; 2→4→6 eskalasi.

## R1-02 [HIGH] Borda crash pada vote impor malformed → fase `meeting` macet permanen
- Lokasi: `server/src/actions.ts`, `advanceRun`, cabang `meeting`:
  `const v = JSON.parse(c.vote) as {...}; v.ranking.forEach(...)` tanpa try/catch
  dan tanpa validasi bentuk.
- Gejala: satu jawaban impor yang `vote`-nya string (`"approve"`) atau objek
  tanpa `ranking` membuat `advanceRun` melempar `TypeError: Cannot read
  properties of undefined (reading 'forEach')` SETIAP kali. Tidak ada UI hapus
  pesan, jadi run tidak bisa keluar dari fase `meeting` kecuali dibuat run baru.
  `JSON.parse(c.critiques)` di `blockingOnWinner` juga tanpa guard (string
  critiques korup → `SyntaxError` yang sama).
- Bukti node (verbatim): vote string → THROW TypeError; vote tanpa ranking → THROW.
- Perbaikan: bungkus parse tiap pesan dalam try/catch; lewati vote yang
  `typeof v.ranking !== "object"` / bukan array (atau normalisasi ke `[]`);
  validasi di `importAiAnswer`: simpan `vote` hanya bila objek dengan
  `ranking` array string + `decision` dalam enum, bila tidak simpan `null`
  dan tandai `parseStatus: "repair_needed"`. Tambah juga action hapus pesan
  impor (atau izinkan owner menandai pesan "diabaikan dari Borda") sebagai
  jalan keluar darurat.

## R1-03 [HIGH] Tidak ada jalan maju manual — impor tidak pernah menggerakkan fase
- Lokasi: `server/src/actions.ts` `advanceRun` (semua fase) + `importAiAnswer`;
  `client/src/App.tsx` `HandoffCard`/`RoomView`.
- Gejala: `importAiAnswer` hanya menyimpan pesan; TIDAK PERNAH mengubah
  `run.phase`, `run.spec`, atau `run.decision`. `advanceRun` selalu memanggil
  `callAgent` (mesin internal/API) dan mengabaikan pesan impor saat
  menghasilkan usulan/kritik/spek/kode. Akibatnya pengguna murni Manual Handoff
  (tanpa API key, tanpa mesin internal) bisa mengimpor jawaban sebanyak apa pun
  tapi TIDAK BISA pindah fase — tombol satu-satunya ("Jalankan Fase") justru
  men-generate ulang jawaban internal dan menduplikasi pesan impor di timeline
  (proposal impor berlabel `""` tampil sebagai "Usulan ===").
  Terkait: impor spek tidak mengisi `run.spec` (fase coding internal lalu
  memakai `spec: "-"`); impor keputusan rapat tidak mengisi `run.decision`
  (fase spek internal memakai `decision: "-"`). Sebaliknya impor KODE sudah
  benar: tersimpan sebagai artefak `kind:"code"` dan dibaca fase review.
- Perbaikan (desain, butuh keputusan parent): tambah aksi
  `advanceRunManual` / tombol "Lanjut Fase (pakai jawaban impor)": di fase
  `proposal`/`critique`, bila pesan impor ronde berjalan sudah ≥2 (proposal)
  atau ada vote (critique), langsung transisi fase tanpa `callAgent`; di fase
  `spec`, bila impor mengandung `spec_markdown`, simpan ke `run.spec` +
  buat tasks + approval seperti jalur internal; di fase `meeting`, bila impor
  mengandung `decision_text`, simpan ke `run.decision`/`disputes`/`dissent`.
  Minimal: beri label pada pesan impor (`agentLabel` A/B/C berurutan per ronde,
  lihat R1-06) agar impor ikut Borda secara benar, dan tampilkan peringatan
  jujur di UI bila fase hanya bisa maju lewat mesin internal.

## R1-04 [MEDIUM] Tabel Borda client mencampur semua ronde + badge mufakat tanpa cek blocking
- Lokasi: `client/src/App.tsx`, `BordaTable`.
- Gejala: (a) tidak ada filter ronde — vote kritik ronde 1 + ronde 2 dijumlah
  jadi satu (server justru filter per ronde dengan benar, jadi tampilan dan
  keputusan server DIVERGEN); (b) badge "Mufakat ≥2/3 (perlu 0 blocking)"
  hanya memeriksa `ratio >= 2/3`, TIDAK memeriksa kritik blocking — bisa
  tampil "Mufakat" padahal ada blocking; (c) `voteCount` client menghitung
  vote ber-ranking kosong sebagai 0 (server menghitungnya sebagai 1 —
  lihat R1-05) sehingga rasio client/server berbeda.
- Perbaikan: filter `m.round === run.round` (teruskan `round` sebagai prop);
  hitung `blockingOnWinner` dari `critiques` dan syaratkan `=== 0` untuk
  badge mufakat; samakan definisi `voteCount` dengan server (atau perbaiki
  keduanya ke definisi yang sama, lihat R1-05).

## R1-05 [MEDIUM] Borda server: ranking kosong menggelembungkan penyebut; seri tanpa aturan
- Lokasi: `server/src/actions.ts`, cabang `meeting`.
- Gejala: vote dengan `ranking: []` tetap `voteCount++` tapi menyumbang 0 poin
  → `approveRatio` mengecil secara artifisial (bukti node: 1 vote ranking
  kosong → `{borda:{}, voteCount:1}`); usulan yang tidak pernah di-ranking
  tidak muncul di `sorted` sama sekali (ranking tidak lengkap); seri poin
  diputus oleh urutan insersi (sort stabil JS) tanpa aturan terdokumentasi;
  bila `voteCount === 0`, `winnerLabel === ""` dan keputusan juri berbunyi
  "usulan  () dipilih" lalu spek berjalan dengan keputusan kosong.
- Perbaikan: lewati vote ber-ranking kosong dari `voteCount` (atau tolak saat
  impor); normalisasi ranking (hanya label proposal ronde ini, deduplikasi);
  tambah tie-break deterministik (mis. poin lalu jumlah approve lalu label
  alfabetis) dan tampilkan; guard `voteCount === 0` → lempar error jelas
  "belum ada vote yang bisa dihitung — impor kritik dengan ranking dulu"
  alih-alih keputusan juri kosong.

## R1-06 [MEDIUM] Pesan impor tanpa `agentLabel` merusak anonimitas A/B/C + Borda
- Lokasi: `server/src/actions.ts`, `importAiAnswer` (`agentLabel: ""` hardcoded).
- Gejala: proposal impor tampil "Usulan ===" di prompt kritik dan "Anonim ?"
  di timeline; ranking impor ("A"/"B"/"C") tidak merujuk ke proposal impor
  mana pun; `own` di fase kritik tidak ketemu untuk agen impor (label "?").
  Ditambah: `importAiAnswer` mengabaikan `data.phase` — impor kritik saat fase
  `research` tersimpan sebagai pesan fase `research` dan tidak pernah dihitung
  Borda; `role` impor untuk fase `spec` jatuh ke `"debater"` (salah).
- Perbaikan: saat impor, tetapkan `agentLabel` berurutan per ronde
  (A/B/C… untuk pengirim berbeda di ronde itu, persisten per `runId+round+
  agentName`); tolak/ingatkan bila `data.phase` ada dan ≠ fase run berjalan
  ("jawaban ini untuk fase X, run sedang di fase Y — simpan sebagai catatan
  saja?"); petakan `role` dari fase (`spec`→`architect`, `coding`→`coder`,
  dst.) atau simpan `data.phase` apa adanya.

## R1-07 [MEDIUM] Repair 1× hanya ditegakkan client — bisa diulang tanpa batas
- Lokasi: `client/src/App.tsx` `HandoffCard.doImport` (`repairCount` state lokal)
  + `server/src/actions.ts` `importAiAnswer` (percaya `args.repairAttempt`).
- Gejala: `repairCount` reset saat komponen remount / pindah room / reload →
  pengguna bisa mengimpor jawaban `repair_needed` berulang kali, tiap kali
  dengan `repairAttempt: 0`, dan server selalu mengembalikan `repairPrompt`
  baru. Batas "maks 1× repair" hanya berlaku bila client jujur.
  Terkait: `repairCount` TIDAK direset setelah impor sukses → jawaban KEDUA
  di fase yang sama langsung dikirim `repairAttempt: 1`, sehingga bila jawaban
  kedua itu `repair_needed`, server langsung menandainya `unparsed` tanpa
  kesempatan repair.
- Perbaikan: tegakkan di server — hitung impor `repair_needed` sebelumnya
  untuk run ini dari DB (pesan `sourceType:"user_imported"` dengan
  `parseStatus:"repair_needed"` pada ronde/fase berjalan); bila sudah ≥1,
  paksa `unparsed`. Di client, reset `repairCount` ke 0 setiap impor `ok`.

## R1-08 [MEDIUM] Secret Scanner: false negative sistematis (lowercase + provider baru)
- Lokasi: `client/src/reference.ts` `SECRET_PATTERNS` + `server/src/actions.ts`
  `SECRET_REGEXES` (duplikat — perbaiki di KEDUA tempat).
- Gejala (bukti node, semua `[]` = lolos): `gho_…`/`ghu_…`/`ghs_…`/`ghr_…`,
  `github_pat_…`, `AIza…` (Google API key), `xoxb-…` (Slack), `password: …`
  (colon, bukan `=`), `apiKey: "…"` / `api_key = …` lowercase. Penyebab:
  pola `.env` TIDAK punya flag `/i` sehingga `openai_api_key=…` lowercase
  lolos (bukti node: `false`); pola `password=` hanya `=`.
- Perbaikan: tambah flag `i` pada pola `.env`; tambah pola
  `gho_|ghu_|ghs_|ghr_|github_pat_`, `AIza[0-9A-Za-z_-]{35}`,
  `xox[baprs]-[0-9A-Za-z-]{10,}`, `(password|passwd|pwd)\s*[:=]\s*\S+`,
  dan pola generik `api[_-]?key\s*[:=]\s*["']?[A-Za-z0-9_-]{16,}`.
  Catatan: `sk-ant-…` dan `sk-proj-…` SUDAH tertangkap pola `sk-` generik.
  Selain itu: `createProject`/`updateProject`/`createMemory` server TIDAK
  memindai (hanya client) — tambah `scanSecretsServer` di ketiga action
  tersebut agar secret tidak tersimpan ke DB lewat pemanggilan langsung.

## R1-09 [MEDIUM] Pacing/limit: tampilan ≠ penegakan; double-click lolos; log dibatasi
- Lokasi: `server/src/actions.ts` `getHandoffStatus` + `recordHandoff`;
  `client/src/App.tsx` `HandoffCard.doCopy/doOpen/doImport`.
- Gejala: (a) `getHandoffStatus.todayCount` menghitung SEMUA aksi
  (`copy`+`open`+`import`), sedangkan penegakan di `recordHandoff` hanya
  menghitung `copy` → angka "hari ini X/40" menggelembung; `secondsSinceLast`
  memakai aksi apa pun (klik "Buka Website" ikut me-reset timer tampil),
  sedangkan penegakan memakai `lastCopy` saja. (b) Tombol Salin/Tempel/Buka
  TIDAK disabled saat request berjalan (tidak seperti tombol Kirim chat yang
  memakai `postMsg.isPending`) → klik ganda cepat mengirim 2× `recordHandoff`
  (keduanya membaca `todayCount` sebelum salah satu insert → pacing lolos)
  dan 2× `importAiAnswer` (pesan impor ganda + artefak ganda). (c)
  `recordHandoff` memakai `.limit(200)` dan `getHandoffStatus` `.limit(500)`
  sebelum filter tanggal → pemakaian berat bisa under-count dan melewati
  batas harian. (d) Prompt tampil `readOnly` di textarea — pengguna bisa
  salin manual dengan Ctrl+C dan melewati `recordHandoff` sepenuhnya
  (pacing + scanner + hitungan). Ini inheren di desain manual-handoff;
  minimal: tampilkan peringatan bahwa salin manual tidak tercatat di kuota.
  (e) `doCopy` mencatat log SEBELUM `clipboard.writeText` — bila clipboard
  gagal (izin), kuota tetap terpotong. Balik urutan: tulis dulu, catat bila sukses.
- Perbaikan: samakan definisi hitungan (hanya `copy`, atau semua aksi —
  pilih satu, di kedua fungsi); filter tanggal di query (`createdAt >=
  startOfDay`) alih-alih `limit()` + filter JS; tambah state `busy` dan
  `disabled={busy}` pada ketiga tombol handoff; pertimbangkan unique
  constraint/idempotency key untuk impor ganda (hash `rawText` + `runId`).

## R1-10 [MEDIUM] Reviewer dicek by NAMA bukan keluarga; moderator minoritas tidak dihitung
- Lokasi: `server/src/actions.ts`, cabang `review` + `meeting`.
- Gejala: `reviewers.filter(a => a.role === "reviewer" && a.name !== coderMsg?.agentName)`
  — reviewer satu keluarga dengan coder (nama berbeda) lolos, melanggar
  "keluarga ≠ coder". `pickRole(agents, ["moderator","planner"])` selalu
  mengambil moderator pertama — aturan "moderator = keluarga paling sedikit
  terwakili di pengusul" tidak pernah dihitung. Terkait: fase `critique`
  memberi tahu tiap debater label usulannya sendiri
  ("Usulanmu sendiri adalah label X") — anonimitas buta bocor dan self-vote
  dimungkinkan; tidak ada yang mencegah debater me-ranking usulannya sendiri
  pertama.
- Perbaikan: bandingkan `a.family !== coderFamily` (ambil family dari pesan
  `phase:"code"`); hitung keluarga pengusul dan pilih moderator dari keluarga
  minoritas (fallback planner bila seri); hapus pengungkapan label sendiri
  dari prompt kritik dan/atau tolak ranking yang menempatkan label sendiri
  di posisi 1 dengan peringatan.

## R1-11 [MEDIUM] Parser fallback: JSON non-MUFAKAT dikira `repair_needed`; JSON valid + prosa kurawal jadi `unparsed`
- Lokasi: `server/src/actions.ts` `parseLastJsonBlock` + `client/src/reference.ts`
  `parseImportedJson` (duplikat — perbaiki keduanya).
- Gejala: fallback `lastIndexOf("{")…lastIndexOf("}")` tanpa validasi skema:
  snippet kode `{"a": 1}` → `repair_needed` (bukti node) padahal bukan pesan
  MUFAKAT; jawaban JSON polos valid yang diikuti prosa mengandung `{`/`}`
  → `unparsed` (bukti node) dan vote/klaim hilang; `summary` dari
  `obj.summary` non-string di-coerce jadi `"[object Object]"`.
- Perbaikan: fallback hanya terima objek bila punya minimal satu kunci
  MUFAKAT (`summary`/`proposal`/`claims`/`critiques`/`vote`/`files`/
  `phase`); untuk JSON polos, cari objek dengan pencocokan kurung berimbang
  (brace-matching dari `{` pertama yang menghasilkan parse valid) alih-alih
  `lastIndexOf`; `summary` hanya dipakai bila `typeof === "string"`.

## R1-12 [LOW-MEDIUM] Devil's advocate & batas lain hanya wacana, tidak dieksekusi
- Lokasi: seluruh codebase (grep: tidak ada komputasi kemiripan).
- Gejala: klaim UI "Devil's advocate bila kemiripan usulan >0,9" tidak punya
  implementasi — tidak ada fungsi similaritas, tidak ada pemicu, tidak ada
  pesan devil's advocate. Sama: `MAX_WALL_TIME ±60 menit` (disebut di
  `ANTI_LOOP`) tidak pernah ditegakkan; `totalIteration` hanya naik di fase
  `revise` sehingga `MAX_TOTAL 12` tidak pernah mengikat sebelum `MAX_FIX 5`
  (keduanya +1 per revisi, `total ≤ fix` selalu).
- Perbaikan: implementasi minimal — hitung similaritas Jaccard/cosine atas
  token usulan antar debater di fase `proposal`; bila max > 0,9, sisipkan
  pesan sistem "Devil's advocate" (pakai agen `contra` bila ada, atau
  instruksikan moderator) dan catat di audit; ATAU hapus klaim dari UI dan
  tulis "belum diimplementasikan". Untuk `totalIteration`, naikkan +1 di
  SETIAP `advanceRun` yang berhasil (atau hapus dari header bila tidak dipakai).

---

# PUTARAN 2 — AUDIT ULANG DARI NOL (temuan tambahan + cek regresi)

Karena Putaran 1 tidak menghasilkan edit apa pun (blokir artifact.edit),
Putaran 2 adalah penyisiran ulang independen atas kode yang sama. Tidak ada
bug yang "diperkenalkan perbaikan" untuk diperiksa — sebagai gantinya ditemukan
9 bug tambahan di bawah. Semua bug Putaran 1 di atas dikonfirmasi masih ada
(kode tidak berubah; tidak ada yang tertutup).

## R2-01 [MEDIUM] Kontaminasi antar-room: `paste`/`repairCount`/progres Run-All terbawa saat pindah room
- Lokasi: `client/src/App.tsx` — `RoomView` merender `<HandoffCard runId={run.id}
  ... />` (baris 540) TANPA `key`; `RoomView` sendiri juga tanpa `key={runId}`.
- Gejala: state `paste`, `agentName`, `repairCount`, `chatText`,
  `runAllSteps`, `runAllSummary` dipertahankan React saat pengguna pindah room.
  Tempelan jawaban room A bisa tanpa sengaja diimpor ke room B dengan sekali
  klik. Progres "Jalankan Semua Fase" room lama tampil di room baru.
- Perbaikan: `<HandoffCard key={run.id} ... />` dan `<RoomView key={effectiveRunId}
  ... />` (atau reset state di `useEffect` saat `runId` berubah).

## R2-02 [MEDIUM] `decideApproval` membangkitkan run yang sudah dihentikan
- Lokasi: `server/src/actions.ts`, `decideApproval` — tidak memeriksa `run.status`.
- Gejala: owner menghentikan run saat approval spek pending, lalu menyetujui
  approval itu (dari Dashboard) → run kembali `status:"running"`, `phase:"coding"`.
  Approval kedaluwarsa tetap bisa dieksekusi.
- Perbaikan: tolak bila `run.status` bukan `"awaiting_approval"` (atau setidaknya
  bukan `running`/`awaiting_approval`); kembalikan error "run sudah berhenti".

## R2-03 [MEDIUM] Pesan & impor & gate bisa masuk ke run yang sudah selesai/berhenti
- Lokasi: `server/src/actions.ts` `postRoomMessage`, `importAiAnswer`,
  `recordGateResult` — tidak ada cek `run.status`.
- Gejala: composer tetap tampil di run `completed`/`stopped`/`escalated`
  (RoomView hanya menyembunyikan HandoffCard + tombol fase); `postRoomMessage`
  bahkan memetakan fase `"done"` → `"meeting"` agar pesan "lolos". Audit trail
  run selesai bisa tercemar pesan/gate baru.
- Perbaikan: tolak ketiga aksi bila status terminal; sembunyikan composer
  bila `finished` (atau tampilkan read-only).

## R2-04 [LOW-MEDIUM] `ensureSeed` menghidupkan kembali agen yang dihapus
- Lokasi: `server/src/actions.ts`, `ensureSeed` (dipanggil di 6 action).
- Gejala: bila pengguna menghapus SEMUA agen (atau agen terakhir),
  pemanggilan berikutnya (`getBootstrap` dsb.) menyisipkan kembali 13 agen
  default. Penghapusan tidak permanen.
- Perbaikan: seed hanya bila tabel `settings` juga kosong (instalasi pertama
  yang sesungguhnya), atau tambah flag `seeded` di settings.

## R2-05 [LOW-MEDIUM] `saveConnection`/`callAgent`/`testConnection`: SSRF via `baseUrl`
- Lokasi: `server/src/actions.ts` — `baseUrl` disimpan tanpa validasi dan
  dipakai `fetch(\`${baseUrl}/chat/completions\`)` / `/models` dengan header
  `Authorization: Bearer <API key user>`.
- Gejala: `baseUrl` sewenang-wenang (mis. `http://169.254.169.254/` atau
  server penyerang) akan menerima API key user di header. Risiko memerlukan
  pengguna menempel URL jahat (mis. dari "tutorial"), tapi ini jalur
  eksfiltrasi kredensial dari server.
- Perbaikan: validasi `baseUrl` harus `https://` + hostname publik
  (tolak IP privat/loopback/link-local dan skema non-https, kecuali
  `http://localhost` eksplisit untuk dev lokal); tampilkan host yang akan
  dihubungi di UI sebelum Tes Koneksi.

## R2-06 [LOW] Dashboard: tombol Tutup disclaimer mati + catatan approval dipakai bersama
- Lokasi: `client/src/App.tsx` baris 655 `<Disclaimer onClose={() => {}} />`
  (RoomView memakai `setShowDisclaimer(false)` yang benar); `Dashboard`
  memakai SATU state `note` untuk SEMUA input catatan approval.
- Gejala: klik "Tutup" di Command Center tidak melakukan apa-apa; mengetik
  catatan di satu approval mengisi semua input approval lain — keputusan
  bisa tersimpan dengan catatan milik approval lain.
- Perbaikan: `const [showDisclaimer, setShowDisclaimer] = useState(true)` +
  `{showDisclaimer && <Disclaimer onClose={() => setShowDisclaimer(false)} />}`;
  ubah `note` menjadi `Record<number,string>` seperti `approvalNotes` di RoomView.

## R2-07 [LOW] Inkonsistensi kecil lain (dikumpulkan)
- `webForAgent` (App.tsx): agen OpenCode/Cursor jatuh ke `WEB_PROVIDERS[0]`
  (chatgpt.com) karena tidak ada cabang `opencode`/`cursor` — tautan "Buka
  Website AI" salah untuk agen tersebut. Tambah cabang atau kembalikan `undefined`
  dan sembunyikan tombol.
- Fase pesan coding memakai literal `"code"` (`saveMessage(..., "code", ...)`),
  bukan `"coding"` — `PHASE_LABELS["code"]` tidak ada → timeline menampilkan
  "code" mentah; `postRoomMessage`/`PhaseStepper` ikut terdampak. Samakan ke `"coding"`
  (dan perbaiki lookup `coderMsg` di fase review yang mencari `phase === "code"`).
- `GateCenter`: grid mode testing hanya menampilkan `tests`+`review`, tapi
  dropdown "Catat Hasil Gate Manual" menampilkan ke-7 gate — catat gate
  tersembunyi dari mode itu. Samakan daftar dropdown dengan `filtered`.
- `ProviderCard`: `baseUrl`/`model` diinisialisasi sekali dari props
  (`useState(p.connBaseUrl...)`) — bila data provider berubah, input basi.
  Sinkronkan dengan `useEffect` atau jadikan `key={p.key + p.connBaseUrl}`.
- `testConnection` gagal: client menampilkan pesan yang sama dua kali
  (teks hijau `msg` + `ErrorNote` merah). Hanya isi salah satunya.
- `getBootstrap.totals.runCount` menghitung `runs` yang sudah `.limit(30)` →
  salah bila run > 30. Hitung dengan query `count` terpisah.
- `deleteProject` tidak menghapus `handoffLogs` → log yatim tetap dihitung
  `getHandoffStatus` (batas harian) setelah proyek dihapus. Tambah penghapusan.
- `Tasks` (`tasks.error`) dan `Connections` (`webQ.error`) dan `HandoffCard`
  (`handoffQ.error`) mengabaikan error query → panel tampil kosong tanpa pesan.
  Tampilkan `ErrorNote`.
- `index.html`: `user-scalable=no` di viewport mematikan pinch-zoom (a11y).
  Hapus `user-scalable=no`.
- `Dashboard` "Run Terakhir" + sidebar memakai `runs[0]` sebagai fallback
  saat `runId` basi — peralihan diam-diam ke run lain. Tampilkan "run tidak
  ditemukan" bila `runId` tidak ada di daftar.
- `advanceRun` memakai `Promise.all` di fase proposal/kritik/review:
  satu agen gagal → seluruh fase gagal dan TIDAK ADA pesan yang tersimpan
  (semua-atau-tidak-ada). Simpan hasil per agen segera setelah selesai
  (atau tangkap error per agen dan lanjutkan dengan yang berhasil + catatan).
- `callAgent` jalur API: kegagalan parse JSON output model ikut menandai
  koneksi `status:"error"` — koneksi sehat disalahkan atas output model yang
  buruk. Bedakan: hanya kegagalan HTTP/jaringan yang mengubah status koneksi.
- Kunci API disimpan plaintext di SQLite `app.db` (`connections.secret`).
  Ini keterbatasan runtime artifact (tanpa manajemen kunci) — dokumentasikan
  sebagai risiko residual; jangan klaim "aman" lebih dari itu.

## R2-08 [LOW] Layout/mobile — hasil audit builder terakhir tetap berlaku
- Audit builder 01:50Z: overflow horizontal 0px di 390px dan 1440px, tidak ada
  kontrol tak terjangkau. Penyisiran kode: semua tabel dibungkus
  `overflow-x-auto`, drawer mobile 280/300px, composer sticky — tidak ditemukan
  overflow baru. Catatan: `theme.css` mengimpor Google Fonts eksternal
  (diblokir di lingkungan audit → fallback font sistem; bukan bug).
  Klip "Message — tulis pesan" di laporan audit adalah label `sr-only`
  (1×1, by design) — false positive. Teks handle crew terpotong di 300px
  (`truncate`, overflow 39px) — kosmetik, perbaiki dengan `min-w-0` sudah ada
  tapi `span` luar perlu `flex-1 min-w-0` penuh (sudah sebagian).

## R2-09 [INFO] Yang diperiksa dan dinyatakan LOLOS (tidak ada bug)
- Manual Handoff: tidak ada auto-send, scraping DOM, cookie/token,
  headless/tab tersembunyi; `window.open(..., "noopener,noreferrer")`;
  clipboard hanya atas klik. Klaim status jujur (tidak ada "Connected" palsu).
- `advanceRun` menolak jalan saat `spec_approval`/`commit_approval` dan
  saat status terminal; Run-All berhenti di approval dan tidak pernah
  memanggil `decideApproval`. Approval tidak bisa dilewati otomatis.
- Borda server memfilter per ronde dengan benar; konsensus mensyaratkan
  `≥2/3 + 0 blocking` (dengan cacat R1-05/R1-02 di atas).
- `decideApproval` menolak approval yang sudah diputuskan.
- Secret Scanner berjalan di client DAN server untuk copy/impor/pesan.
- Data tersimpan di SQLite server → selamat dari reload (state client
  transien seperti `repairCount`/`runAllSteps` memang hilang — wajar).

---

# RINGKASAN SEVERITY

| Severity | Jumlah | ID |
|---|---|---|
| HIGH | 3 | R1-01, R1-02, R1-03 |
| MEDIUM | 11 | R1-04 s/d R1-11 (8) + R2-01, R2-02, R2-03 (3) |
| LOW | 6 | R1-12 + R2-04 s/d R2-08 (5) |

Total: 3 HIGH, 11 MEDIUM, 6 LOW = 20 bug. Nol diperbaiki (blokir alat).

# RENCANA EKSEKUSI UNTUK BUILDER (parent agent)

1. Spawn builder dengan akses `artifact.edit` untuk slug `mufakat`.
2. Terapkan patch per bug di atas, urutan: R1-02 → R1-01 → R1-05 → R1-04 →
   R1-06 → R1-07 → R1-08 → R1-11 → R1-09 → R1-10 → R1-03 (butuh keputusan
   desain parent) → R1-12 → R2-01 s/d R2-07.
3. Verifikasi: typecheck + build builder + audit builder (desktop+mobile) +
   uji ulang skenario node di `/tmp/mufakat_audit_test*.mjs` (skenario
   stalled/Borda/parser/scanner) — file-file itu ada di VM ini.
4. Bug yang sengaja TIDAK diperbaiki di putaran ini: tidak ada (semua punya
   perbaikan spesifik di atas) kecuali R1-03 yang butuh keputusan desain
   parent (apakah impor boleh menggerakkan fase) dan enkripsi API key
   (R2-07, keterbatasan runtime — didokumentasikan saja).
