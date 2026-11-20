// MUFAKAT Room — Secret Scanner (Claude §0.2, §T8).
// Dijalankan SEBELUM prompt disalin/dikirim DAN sebelum jawaban impor
// disimpan. Temuan 'block' -> blokir + peringatkan. Temuan 'warn'
// (mis. rujukan file .env di ide) -> peringatan saja, TIDAK memblokir
// (M2: ".env" di ide "Buat app baca .env" bukan secret).
// Nilai asli TIDAK disimpan di log (hanya preview 4 karakter).
// Pola disamakan dengan Python src/mufakat/room/secret_scan.py, plus JWT.
export interface SecretFinding {
  pattern: string;
  preview: string;
  /** 'block' = blokir simpan/kirim; 'warn' = peringatan saja. */
  severity: 'block' | 'warn';
}

type PatternEntry = [string, RegExp, SecretFinding['severity']];

const PATTERNS: PatternEntry[] = [
  ['aws_access_key', /AKIA[0-9A-Z]{16}/, 'block'],
  ['github_token', /gh[pousr]_[A-Za-z0-9]{20,}/, 'block'],
  ['github_fine_grained_token', /github_pat_[A-Za-z0-9_]{20,}/, 'block'],
  ['openai_key', /sk-(?:proj-)?[A-Za-z0-9\-_]{20,}/, 'block'],
  ['anthropic_key', /sk-ant-[A-Za-z0-9\-_]{10,}/, 'block'],
  ['google_api_key', /AIza[0-9A-Za-z\-_]{35}/, 'block'],
  ['slack_token', /xox[baprs]-[A-Za-z0-9\-]{10,}/, 'block'],
  // JWT: header.payload.signature, masing-masing base64url; header dan
  // payload diawali eyJ ({"alg":...} / {"sub":...}).
  ['jwt_token', /eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/, 'block'],
  ['bearer_token', /Bearer\s+[A-Za-z0-9\-._~+/=]{10,}/, 'block'],
  ['private_key_block', /-----BEGIN [A-Z ]*PRIVATE KEY-----/i, 'block'],
  // M2: rujukan file .env hanya peringatan, bukan blokir.
  ['env_file_ref', /\.env\b/i, 'warn'],
  [
    'credential_assignment',
    /(api[_ -]?key|apikey|secret|password|passwd|token|access[_ -]?key)(\s*[:=]\s*)(["']?)[^\s"',;]{4,}/i,
    'block',
  ],
  [
    'generic_long_token',
    /(token|secret)\s*[:=]\s*['"][A-Za-z0-9\-_]{16,}['"]/i,
    'block',
  ],
];

export function scanText(text: string): SecretFinding[] {
  const findings: SecretFinding[] = [];
  // Satu rentang teks yang cocok beberapa pola hanya dilaporkan sekali
  // (pola pertama yang cocok menang), sama seperti Python.
  const seenSpans: Array<[number, number]> = [];
  for (const [name, pattern, severity] of PATTERNS) {
    const global = new RegExp(pattern, pattern.flags.includes('g') ? pattern.flags : pattern.flags + 'g');
    for (const match of (text ?? '').matchAll(global)) {
      const start = match.index ?? 0;
      const end = start + match[0].length;
      if (seenSpans.some(([s, e]) => start < e && s < end)) continue;
      seenSpans.push([start, end]);
      const cleaned = match[0].trim();
      findings.push({
        pattern: name,
        preview: cleaned.length > 4 ? cleaned.slice(0, 4) + '...' : '****',
        severity,
      });
    }
  }
  return findings;
}

/** Hanya temuan yang memblokir (bukan peringatan). */
export function blockingFindings(findings: SecretFinding[]): SecretFinding[] {
  return findings.filter((f) => f.severity === 'block');
}

export function containsSecret(text: string): boolean {
  return blockingFindings(scanText(text)).length > 0;
}
