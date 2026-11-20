# Sandbox MUFAKAT (T9, diperbaiki audit 20 Nov 2026: H7;
# putaran 2: N1 — aturan Semgrep + DB Trivy di dalam image,
# supaya gate jalan offline di container --network none).
# Python 3.12 + tooling verifikasi kode.
#
# Aturan Dockerfile ini:
# - SEMUA tool di-pin versinya dan diverifikasi checksum (SHA-256)
#   bila diunduh sebagai arsip. TIDAK ADA `curl | bash` dari branch
#   `master` dan TIDAK ADA `|| echo dilewati` — build GAGAL bila
#   satu tool tidak terpasang, supaya gate tidak jatuh diam-diam ke
#   fallback regex.
# - trivy v0.76.2 (rilis 5 Nov 2026; v0.50.0 lama sudah sangat tua).
# - gitleaks v8.30.1.
# - Node.js v20.20.2 (tarball resmi + checksum, tanpa nodesource).
# - User `mufakat` uid 10001 — HARUS cocok dengan
#   `--user 10001:10001` di `src/mufakat/sandbox/docker.py`.
# Versi di-pin per 20 Nov 2026 (dicek via PyPI / nodejs.org /
# GitHub releases + checksums resmi).
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TRIVY_CACHE_DIR=/var/lib/trivy

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates xz-utils \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Node.js v20.20.2 — tarball resmi nodejs.org, verifikasi SHA-256.
ARG NODE_VERSION=20.20.2
ARG NODE_SHA256=df770b2a6f130ed8627c9782c988fda9669fa23898329a61a871e32f965e007d
RUN curl -fsSL -o /tmp/node.tar.xz \
        "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
    && echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum -c - \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.xz \
    && node --version && npm --version

# Tooling verifikasi Python — versi di-pin (pip gagal bila versi tak ada).
RUN pip install --no-cache-dir \
        semgrep==1.186.0 \
        bandit==1.9.4 \
        ruff==0.17.6 \
        pytest==9.2.0 \
        pytest-cov==7.1.0 \
    && semgrep --version && bandit --version && ruff --version && pytest --version

# Aturan Semgrep DI DALAM image (N1, putaran 2) — JANGAN pakai
# `--config auto` di gate: container jalan `--network none`, jadi
# unduhan aturan dari registry Semgrep pasti gagal dan gate lolos
# kosong. Salinan `p/python` + `p/secrets` dari repo semgrep-rules,
# di-pin ke commit a5ad1714f00c9f7fde980cab0ea1d6dc6d414fd2
# (2026-11-10) dan diverifikasi SHA-256 tarball-nya. Gate memakai
# `semgrep --config /rules`. Build GAGAL bila tarball/checksum/
# jumlah aturan tidak cocok atau aturan tidak bisa dimuat (smoke
# test atas direktori kosong — membuktikan aturan termuat offline).
ARG SEMGREP_RULES_REF=a5ad1714f00c9f7fde980cab0ea1d6dc6d414fd2
ARG SEMGREP_RULES_SHA256=e5a7ec33035fc7707b87385cb99e1228c76b1604efe5439e92891f3005714cc3
RUN curl -fsSL -o /tmp/semgrep-rules.tar.gz \
        "https://codeload.github.com/semgrep/semgrep-rules/tar.gz/${SEMGREP_RULES_REF}" \
    && echo "${SEMGREP_RULES_SHA256}  /tmp/semgrep-rules.tar.gz" | sha256sum -c - \
    && mkdir -p /tmp/semgrep-rules /rules \
    && tar -xzf /tmp/semgrep-rules.tar.gz -C /tmp/semgrep-rules --strip-components=1 \
    && cp -r /tmp/semgrep-rules/python /rules/python \
    && cp -r /tmp/semgrep-rules/generic/secrets /rules/secrets \
    && find /rules -type f ! -name '*.yaml' ! -name '*.yml' -delete \
    && rm -rf /tmp/semgrep-rules /tmp/semgrep-rules.tar.gz \
    && test "$(find /rules -name '*.yaml' -o -name '*.yml' | wc -l)" -ge 500 \
    && mkdir -p /tmp/empty-rules-check \
    && semgrep --json --config /rules --metrics off --quiet /tmp/empty-rules-check \
    && rm -rf /tmp/empty-rules-check

# trivy v0.76.2 — tarball rilis GitHub resmi, verifikasi SHA-256.
# Build GAGAL bila checksum tidak cocok / binary tidak jalan.
ARG TRIVY_VERSION=0.76.2
ARG TRIVY_SHA256=bc0fc726e017b8927a62b2d3531d7a84ee01769daf5c99ed866dced54089fdbf
RUN curl -fsSL -o /tmp/trivy.tar.gz \
        "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" \
    && echo "${TRIVY_SHA256}  /tmp/trivy.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/trivy.tar.gz -C /usr/local/bin trivy \
    && rm /tmp/trivy.tar.gz \
    && trivy --version

# Database CVE Trivy DI DALAM image (N1, putaran 2) — JANGAN unduh
# saat jalan: container `--network none`, jadi `trivy fs` tanpa DB
# pasti gagal dan gate lolos kosong. Gate memakai
# `trivy fs --skip-db-update --offline-scan`. DB diunduh saat build
# (di sinilah jaringan tersedia) ke $TRIVY_CACHE_DIR dan dibuat
# bisa dibaca/ditulis user `mufakat` (trivy butuh lock file di cache
# saat scan; container bersifat sekali pakai). Build GAGAL bila DB
# tidak terunduh. CATATAN: DB membeku pada tanggal build — rebuild
# image secara berkala untuk CVE terbaru.
RUN mkdir -p /var/lib/trivy \
    && trivy image --download-db-only \
    && test -n "$(find /var/lib/trivy -name 'trivy.db' | head -n 1)" \
    && chmod -R a+rwX /var/lib/trivy

# gitleaks v8.30.1 — tarball rilis GitHub resmi, verifikasi SHA-256.
ARG GITLEAKS_VERSION=8.30.1
ARG GITLEAKS_SHA256=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
RUN curl -fsSL -o /tmp/gitleaks.tar.gz \
        "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
    && echo "${GITLEAKS_SHA256}  /tmp/gitleaks.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/gitleaks.tar.gz -C /usr/local/bin gitleaks \
    && rm /tmp/gitleaks.tar.gz \
    && gitleaks version

RUN useradd -m -u 10001 -s /bin/sh mufakat \
    && mkdir -p /work /rules \
    && chown mufakat:mufakat /work \
    && chmod -R a+rX /rules

USER mufakat
WORKDIR /work
