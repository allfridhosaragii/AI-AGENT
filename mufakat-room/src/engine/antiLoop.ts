// MUFAKAT Room — Anti-loop (Claude §2.4, §T13).
// Eskalasi bila hash (diff + temuan) sama muncul 2x, atau jumlah temuan
// tidak turun 2 iterasi berturut-turut.
export async function hashDiffFindings(diffText: string, findings: unknown[]): Promise<string> {
  const normalized = [...findings].map((f) => JSON.stringify(f)).sort();
  const payload = JSON.stringify({ diff: diffText, findings: normalized });
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(payload));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export class AntiLoop {
  private hashCounts = new Map<string, number>();
  private findingCounts: number[] = [];

  async observe(diffText: string, findings: unknown[]): Promise<{ escalate: boolean; repeatedHash: boolean; stagnantFindings: boolean }> {
    const hash = await hashDiffFindings(diffText, findings);
    const seen = (this.hashCounts.get(hash) ?? 0) + 1;
    this.hashCounts.set(hash, seen);
    this.findingCounts.push(findings.length);
    const repeatedHash = seen >= 2;
    const n = this.findingCounts.length;
    const stagnantFindings =
      n >= 3 &&
      this.findingCounts[n - 1] >= this.findingCounts[n - 2] &&
      this.findingCounts[n - 2] >= this.findingCounts[n - 3] &&
      this.findingCounts[n - 1] > 0;
    return { escalate: repeatedHash || stagnantFindings, repeatedHash, stagnantFindings };
  }
}
