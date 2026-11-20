// MUFAKAT Room — Secret Scanner (Claude §0.2, §T8).
// Dijalankan SEBELUM prompt disalin/dikirim. Bila ada temuan -> blokir + peringatkan.
// Nilai asli TIDAK disimpan di log (hanya preview 4 karakter).
export interface SecretFinding {
  pattern: string;
  preview: string;
}

const PATTERNS: Array<[string, RegExp]> = [
  ['aws_access_key', /AKIA[0-9A-Z]{16}/],
  ['github_token', /gh[pousr]_[A-Za-z0-9]{20,}/],
  ['openai_key', /sk-[A-Za-z0-9]{20,}/],
  ['anthropic_key', /sk-ant-[A-Za-z0-9\-_]{10,}/],
  ['bearer_token', /Bearer\s+[A-Za-z0-9\-._~+/=]{10,}/],
  ['private_key_block', /-----BEGIN [A-Z ]*PRIVATE KEY-----/],
  ['env_file_ref', /\.env\b/i],
  [
    'credential_assignment',
    /(api[_-]?key|apikey|secret|password|passwd|token)(\s*[:=]\s*)(["']?)[^\s"',;]{4,}/i,
  ],
];

export function scanText(text: string): SecretFinding[] {
  const findings: SecretFinding[] = [];
  for (const [name, pattern] of PATTERNS) {
    for (const match of text.matchAll(new RegExp(pattern, pattern.flags.includes('g') ? pattern.flags : pattern.flags + 'g'))) {
      const cleaned = match[0].trim();
      findings.push({ pattern: name, preview: cleaned.length > 4 ? cleaned.slice(0, 4) + '...' : '****' });
    }
  }
  return findings;
}
