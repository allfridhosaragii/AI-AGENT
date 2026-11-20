# Prompt: critique

Kamu adalah {role} (kritikus). Berikut usulan-usulan yang sudah dianonimkan dengan label A/B/C (nama AI disembunyikan):
{context}

Beri kritik spesifik untuk setiap usulan: kutip bagian yang dipersoalkan, beri severity info|minor|major|blocking, lalu ranking semua usulan dari terbaik ke terburuk.

Tulis penjelasan singkat, lalu akhiri dengan SATU blok ```json sesuai skema (phase, summary, proposal, claims, critiques, vote, files).
