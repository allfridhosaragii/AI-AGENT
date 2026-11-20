# Modul Opt-in Fase 2 — content script + Assisted Fill (TIDAK AKTIF di MVP)

Direktori ini berisi satu-satunya kode MUFAKAT Room yang membaca DOM situs
AI (`readLastReply`) atau mengisi kolom input (`fillInput`):

- `content-scripts/*.content.ts` — content script per situs (WXT
  `defineContentScript`), delegasi ke `src/adapters/base.ts`.
- `src/adapters/base.ts` — interface `SiteAdapter` + `fillInputGeneric` /
  `readLastReplyGeneric` (dipakai hanya oleh modul ini; tidak ada jalur
  lain yang memanggilnya di MVP).

## Status MVP (browser-only, Manual Handoff)

- File-file ini BERADA DI LUAR `src/entrypoints/`, sehingga WXT **tidak**
  menemukannya sebagai entrypoint dan **tidak** memasukkannya ke manifest
  MVP. Extension MVP tidak menyuntikkan skrip apa pun ke situs AI, tidak
  membaca DOM, dan tidak mengisi input.
- Background MVP tidak lagi punya handler `FILL_INPUT` / `READ_LAST_REPLY`
  (dihapus putaran 2). Tombol "Ambil jawaban terakhir dari tab" dihapus
  dari side panel.
- `host_permissions` untuk 6 domain AI dihapus dari `wxt.config.ts`.

## Mengaktifkan (keputusan eksplisit, bukan default)

1. Pindahkan `content-scripts/*.content.ts` kembali ke `src/entrypoints/`.
2. Tambah kembali `host_permissions` 6 domain di `wxt.config.ts`.
3. Tambah kembali handler `FILL_INPUT` / `READ_LAST_REPLY` di background
   (dengan validasi sender + secret scan + pacing).
4. Uji ulang ToS tiap situs dan Selector Doctor sebelum dipakai.

Tanpa langkah di atas, modul ini hanyalah kode mati yang tidak dieksekusi.
