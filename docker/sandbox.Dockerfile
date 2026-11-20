# Sandbox MUFAKAT (T9, diperbaiki audit 20 Nov 2026: H7).
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
    PYTHONDONTWRITEBYTECODE=1

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
    && mkdir -p /work && chown mufakat:mufakat /work

USER mufakat
WORKDIR /work
