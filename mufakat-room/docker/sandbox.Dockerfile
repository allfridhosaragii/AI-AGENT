# Sandbox MUFAKAT (T9): Python 3.12 + tooling verifikasi kode.
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Tooling verifikasi (pip/apt secukupnya; trivy via repo resmi bila tersedia).
RUN pip install --no-cache-dir semgrep bandit ruff pytest \
    && (curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
        | sh -s -- -b /usr/local/bin v0.50.0 || echo "trivy install dilewati") \
    && (curl -sSL https://raw.githubusercontent.com/gitleaks/gitleaks/master/install.sh \
        | bash || echo "gitleaks install dilewati")

RUN useradd -m -u 10001 -s /bin/sh mufakat \
    && mkdir -p /work && chown mufakat:mufakat /work

USER mufakat
WORKDIR /work
