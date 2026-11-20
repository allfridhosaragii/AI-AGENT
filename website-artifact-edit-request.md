# Permintaan edit artifact `mufakat` — perbaikan audit MUFAKAT (20 Nov 2026)

> CATATAN PROSES: file ini disiapkan worker website/dokumentasi karena
> `artifact.edit` TIDAK tersedia di subagent ini (namespace `artifact`
> yang termuat hanya berisi `restore`/`share`/`unshare`). Minta agen yang
> punya akses `artifact.edit` menjalankan permintaan verbatim di bawah
> ini terhadap artifact slug `mufakat` (SATU edit, jangan buat artifact baru).

---

## Permintaan verbatim untuk builder (artifact.edit, slug `mufakat`)

Perbaiki website MUFAKAT Room (Browser-Only AI Room, MVP) berdasarkan
temuan audit 20 Nov 2026 (audit ChatGPT + audit ekstrem 2 putaran).
Jangan buat artifact baru; edit artifact `mufakat` yang sudah ada.

### 1. Impor jawaban harus benar-benar tersimpan (temuan A / H5)
- Tombol "Simpan jawaban impor" / `importAiAnswer` WAJIB menulis jawaban
  ke penyimpanan persisten (IndexedDB/Dexie + state server) SEBELUM
  menampilkan pesan sukses, dan hanya menampilkan "disimpan" setelah
  penulisan berhasil dikonfirmasi. Jangan pernah mengosongkan textarea
  atau menampilkan "Jawaban disimpan…" bila tidak ada yang tersimpan.
- Setiap jawaban impor menyimpan provenance: provider, ronde, waktu impor,
  label "user imported", dan `agentLabel` anonim (A/B/C) yang konsisten
  agar anonimitas dan Borda tidak rusak (R1-06).
- Impor jawaban harus menggerakkan state rapat (R1-03): impor proposal
  mengubah fase/room state sebagaimana mestinya, bukan hanya menyimpan pesan.

### 2. State rapat persisten (temuan B / M5)
- State rapat (fase, jawaban impor, vote, spec, decision) WAJIB persisten
  di IndexedDB / `chrome.storage` / penyimpanan server — TIDAK BOLEH hanya
  di variabel modul service worker atau state React in-memory. Setelah
  reload halaman, rapat kembali pada fase dan data yang sama.

### 3. Pacing ditegakkan di server (temuan H5 / M8)
- Tegakkan di sisi server (bukan hanya client): jeda minimum 20 detik
  per situs sebelum prompt berikutnya boleh disalin, dan batas harian
  40 prompt per situs. Setiap penyalinan prompt WAJIB memanggil
  `recordPrompt` per provider (saat ini tidak pernah dipanggil).
- Tampilkan di UI: hitung mundur jeda 20 detik dan sisa kuota harian
  per situs, serta penolakan yang jelas bila pacing/batas tercapai.

### 4. Secret scan SEBELUM jawaban impor disimpan (temuan M2 / R1-08)
- Jalankan secret scanner SEBELUM jawaban impor ditulis ke penyimpanan.
  Samakan pola dengan `room/secret_scan.py` versi Python (tangkap
  `sk-proj-…`, `github_pat_…`, `AIza…`, `xoxb-…`, JWT, dan pola token
  telanjang lainnya). Bila secret terdeteksi: blokir penyimpanan,
  tampilkan peringatan, dan JANGAN simpan nilai secret di log.
- Kata `.env` di dalam ide/teks biasa hanya peringatan, bukan blokir.

### 5. Borda tidak crash pada vote malformed (temuan R1-02 / R1-05)
- `advanceRun` cabang `meeting`: bungkus `JSON.parse(c.vote)` dalam
  try/catch dan validasi bentuk vote (ranking harus array berisi label
  yang dikenal; vote malformed ditolak dengan pesan jelas, BUKAN crash
  dan BUKAN macet permanen di fase `meeting`).
- Vote dengan `ranking: []` tidak boleh menggelembungkan penyebut
  `approveRatio`; seri harus diputus dengan aturan yang terdokumentasi
  di UI (bukan diam-diam).
- Repair jawaban `repair_needed` dibatasi MAKS 1x dan ditegakkan di
  server (bukan hanya state lokal client yang reset saat remount/reload).

### 6. Tidak ada klaim koneksi palsu (temuan D / I)
- Status provider di UI harus jujur: ChatGPT, Claude, Gemini, DeepSeek,
  Qwen = `manual_handoff` ("Manual handoff only"); Muse =
  `needs_policy_review`. Jangan pernah menampilkan "connected",
  "terhubung", atau indikator hijau koneksi untuk manual handoff.
- Samakan nama provider di seluruh UI (satu penamaan konsisten;
  jangan ada varian ejaan/nama yang berbeda untuk provider yang sama).

### 7. Tombol "Lanjut Fase (pakai jawaban impor)" tetap ada
- Tombol "Lanjut Fase (pakai jawaban impor)" HARUS tetap ada dan tampil
  di fase proposal/kritik/spec/meeting, dan TIDAK BOLEH memanggil mesin
  internal (engine) — hanya memajukan fase memakai jawaban yang sudah
  diimpor.

### 8. Assisted Fill DIHAPUS dari UI utama MVP
- Hapus Assisted Fill dari UI utama MVP. Bila masih ada jejaknya,
  tampilkan sebagai opt-in Fase 2 yang JELAS TIDAK AKTIF (disabled,
  berlabel "Fase 2 — tidak aktif, butuh keputusan owner"), tidak bisa
  diklik untuk mengisi apa pun, dan tidak dipakai Room. Jangan ada
  checkbox "Aktifkan Assisted Fill" yang tidak melakukan apa-apa.

### 9. Anti-loop & state machine (temuan M4 / M7)
- Eskalasi setelah ronde ke-3 tanpa mufakat (bukan setelah 2 ronde),
  menuju `spesifikasi` dengan `dissent` yang dicatat (bukan state
  `eskalasi` buntu). Kritik `blocking` yang sudah dijawab harus bisa
  ditandai `resolved` agar mufakat mungkin tercapai; `approveRatio`
  dihitung terhadap usulan pemenang.

### 10. Verifikasi builder (WAJIB dijalankan di sandbox, laporkan hasilnya)
1. Impor jawaban → tampil "disimpan" → reload halaman → jawaban dan
   fase masih ada (state persisten).
2. Salin prompt, lalu coba salin prompt kedua ke situs yang sama
   < 20 detik → DITOLAK dengan pesan pacing + hitung mundur tampil.
3. Impor vote malformed (mis. `{"ranking": "bukan-array"}` dan JSON
   rusak) → TIDAK crash, fase `meeting` tetap jalan, vote ditolak
   dengan pesan jelas.
4. Impor jawaban berisi `sk-proj-...` → DIBLOKIR sebelum tersimpan,
   tidak ada di penyimpanan maupun log.
5. Periksa seluruh UI: tidak ada klaim "connected"/"terhubung" untuk
   provider manual handoff; tidak ada kontrol Assisted Fill aktif
   di UI utama.
6. Klik "Lanjut Fase (pakai jawaban impor)" di tiap fase → fase maju
   memakai jawaban impor, tanpa memanggil mesin internal.

Laporkan: apa yang diubah (file/fungsi), hasil tiap uji verifikasi di
atas (lolos/gagal + bukti), dan apa yang masih tersisa beserta alasannya.
Jangan mengarang angka atau hasil uji yang tidak dijalankan.
