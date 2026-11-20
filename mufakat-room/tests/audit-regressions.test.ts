// MUFAKAT Room — test regresi audit 2026-11-20 (H2/H5, M2-M9).
// Tiap test memetakan ke satu temuan audit; baru dianggap selesai bila lulus.
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { parseReply, extractLastJsonObject } from '../src/engine/parser';
import { anonymize, decideConsensus } from '../src/engine/consensus';
import { blockingFindings, scanText } from '../src/engine/secretScan';
import { createDebateMachine, MAX_DEBATE_ROUNDS } from '../src/engine/stateMachine';
import { detectBlockerGeneric, isLoggedInGeneric, type SiteSelectors } from '../src/adapters/base';

const JWT = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c';

describe('M3 parser', () => {
  it('blok ```json tanpa newline setelah json tetap terparse', () => {
    const text = 'Penjelasan singkat. ```json{"phase": "proposal", "summary": "tanpa newline"}```';
    expect(parseReply(text).status).toBe('ok');
    expect(parseReply(text).payload?.summary).toBe('tanpa newline');
  });
  it('innerText tanpa pagar (DOM menghilangkan ```) memakai fallback objek terakhir', () => {
    const text = 'Penjelasan singkat.\n{"phase": "proposal", "summary": "tanpa pagar"}';
    expect(parseReply(text).status).toBe('ok');
    expect(parseReply(text).payload?.summary).toBe('tanpa pagar');
  });
  it('fallback mengambil objek {...} terakhir yang valid, bukan yang rusak', () => {
    const text = 'dulu {"phase": "proposal", "summary": "a",} lalu {"phase": "proposal", "summary": "b"} ekor';
    expect(extractLastJsonObject(text)).toContain('"b"');
    expect(parseReply(text).payload?.summary).toBe('b');
  });
});

describe('M2 secret scan', () => {
  it('menangkap 5 pola telanjang: sk-proj-, github_pat_, AIza, xoxb-, JWT', () => {
    expect(scanText(`key ${'sk-proj-' + 'a'.repeat(24)}`).map((f) => f.pattern)).toContain('openai_key');
    expect(scanText(`token ${'github_pat_' + 'A'.repeat(22)}`).map((f) => f.pattern)).toContain('github_fine_grained_token');
    expect(scanText(`key ${'AIza' + 'A'.repeat(35)}`).map((f) => f.pattern)).toContain('google_api_key');
    expect(scanText(`token ${'xoxb-' + '1234567890'}`).map((f) => f.pattern)).toContain('slack_token');
    expect(scanText(`auth ${JWT}`).map((f) => f.pattern)).toContain('jwt_token');
  });
  it('.env hanya peringatan, bukan blokir', () => {
    const findings = scanText('Buat app baca .env');
    expect(findings.length).toBeGreaterThan(0);
    expect(findings.every((f) => f.severity === 'warn')).toBe(true);
    expect(blockingFindings(findings)).toEqual([]);
  });
  it('satu secret yang cocok dua pola hanya dilaporkan sekali', () => {
    const findings = scanText(`api_key = "${'sk-proj-' + 'a'.repeat(24)}"`);
    expect(findings).toHaveLength(1);
  });
});

describe('M4 state machine ronde 3', () => {
  function driveToRound3WithoutConsensus(): ReturnType<typeof createDebateMachine> {
    const machine = createDebateMachine();
    machine.transition('kirim_ide'); // ronde 1
    machine.transition('usulan_diterima');
    machine.transition('kritik_diterima');
    machine.transition('belum_mufakat');
    machine.transition('debat_lanjut'); // ronde 2
    machine.transition('kritik_diterima');
    machine.transition('belum_mufakat');
    machine.transition('debat_lanjut'); // ronde 3 -> harus spesifikasi + dissent
    return machine;
  }
  it('ronde 3 tanpa mufakat -> spesifikasi dengan dissent, bukan eskalasi', () => {
    expect(MAX_DEBATE_ROUNDS).toBe(3);
    const machine = driveToRound3WithoutConsensus();
    expect(machine.getState()).toBe('spesifikasi');
    expect(machine.getRound()).toBe(3);
    expect(machine.getDissent()).toContain('Ronde 3');
    expect(machine.isTerminal()).toBe(false);
    expect(machine.transition('spek_selesai')).toBe('approve_spek');
  });
  it('juri_memutus dari rapat -> spesifikasi dengan dissent', () => {
    const machine = createDebateMachine();
    machine.transition('kirim_ide');
    machine.transition('usulan_diterima');
    machine.transition('kritik_diterima');
    expect(machine.transition('juri_memutus', 'Minoritas menolak karena biaya.')).toBe('spesifikasi');
    expect(machine.getDissent()).toBe('Minoritas menolak karena biaya.');
  });
  it('snapshot/restore bertahan melewati pembuatan ulang machine (M5)', () => {
    const machine = driveToRound3WithoutConsensus();
    const snapshot = machine.getSnapshot();
    const restored = createDebateMachine(snapshot);
    expect(restored.getState()).toBe('spesifikasi');
    expect(restored.getRound()).toBe(3);
    expect(restored.getDissent()).toContain('Ronde 3');
  });
});

describe('M6 anonimisasi seed acak', () => {
  it('tanpa seed -> seed diambil dari crypto.getRandomValues', () => {
    const spy = vi.spyOn(globalThis.crypto, 'getRandomValues');
    anonymize([
      { agentId: 'gemini', text: 'a' },
      { agentId: 'chatgpt', text: 'b' },
      { agentId: 'claude', text: 'c' },
    ]);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });
  it('seed eksplisit -> deterministik dan TIDAK memakai crypto', () => {
    const spy = vi.spyOn(globalThis.crypto, 'getRandomValues');
    const a = anonymize(
      [
        { agentId: 'gemini', text: 'a' },
        { agentId: 'chatgpt', text: 'b' },
        { agentId: 'claude', text: 'c' },
      ],
      42,
    );
    const b = anonymize(
      [
        { agentId: 'gemini', text: 'a' },
        { agentId: 'chatgpt', text: 'b' },
        { agentId: 'claude', text: 'c' },
      ],
      42,
    );
    expect(a.mapping).toEqual(b.mapping);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});

describe('M7 konsensus', () => {
  const votes = [
    { agentId: 'a', decision: 'approve' as const, ranking: ['A', 'B', 'C'] },
    { agentId: 'b', decision: 'approve' as const, ranking: ['A', 'C', 'B'] },
    { agentId: 'c', decision: 'revise' as const, ranking: ['B', 'A', 'C'] },
  ];
  it('kritik blocking yang sudah resolved tidak menghalangi mufakat', () => {
    const result = decideConsensus(votes, [{ severity: 'blocking', text: 'SQL injection', resolved: true }]);
    expect(result.blocking).toBe(0);
    expect(result.decision).toBe('mufakat');
  });
  it('kritik blocking belum dijawab tetap menghalangi', () => {
    const result = decideConsensus(votes, [{ severity: 'blocking', text: 'SQL injection' }]);
    expect(result.blocking).toBe(1);
    expect(result.decision).toBe('belum_mufakat');
  });
  it('approveRatio terikat ke pemenang, bukan ke total approve', () => {
    // Global approve 4/5, tapi pemenang A hanya didukung 2/5 -> belum mufakat.
    const tricky = [
      { agentId: 'a', decision: 'approve' as const, ranking: ['B', 'A'] },
      { agentId: 'b', decision: 'approve' as const, ranking: ['B', 'A'] },
      { agentId: 'c', decision: 'approve' as const, ranking: ['A', 'B'] },
      { agentId: 'd', decision: 'approve' as const, ranking: ['A', 'B'] },
      { agentId: 'e', decision: 'revise' as const, ranking: ['A', 'B'] },
    ];
    const result = decideConsensus(tricky, []);
    expect(result.winner).toBe('A');
    expect(result.winnerApprovals).toBe(2);
    expect(result.approveRatio).toBeCloseTo(0.4);
    expect(result.decision).toBe('belum_mufakat');
  });
});

describe('M9 detectBlocker', () => {
  const baseSelectors: SiteSelectors = {
    input: '#prompt-textarea',
    lastMessage: '[data-message-author-role="assistant"]',
    matches: ['https://chatgpt.com/*'],
  };
  let present: Set<string>;
  let savedDocument: unknown;

  beforeEach(() => {
    savedDocument = (globalThis as unknown as { document?: unknown }).document;
    present = new Set<string>();
    (globalThis as unknown as { document: unknown }).document = {
      querySelector: (sel: string) => (present.has(sel) ? {} : null),
      querySelectorAll: () => [],
    };
  });
  afterEach(() => {
    (globalThis as unknown as { document?: unknown }).document = savedDocument as never;
  });

  it('teks "too many requests" di body TIDAK memicu rate_limit tanpa banner spesifik', () => {
    // Stub document di atas bahkan tidak punya body.innerText: bila kode
    // menyentuh body.innerText, test ini throw.
    present.add('#prompt-textarea');
    expect(detectBlockerGeneric(baseSelectors)).toBeNull();
  });
  it('banner/toast rate-limit spesifik memicu rate_limit', () => {
    present.add('#prompt-textarea');
    expect(
      detectBlockerGeneric({ ...baseSelectors, rateLimitIndicator: '.rl-toast' }),
    ).toBeNull();
    present.add('.rl-toast');
    expect(detectBlockerGeneric({ ...baseSelectors, rateLimitIndicator: '.rl-toast' })).toBe('rate_limit');
  });
  it('input hilang -> error (selector rusak), BUKAN logged_out', () => {
    expect(detectBlockerGeneric(baseSelectors)).toBe('error');
    expect(isLoggedInGeneric(baseSelectors)).toBe(false);
  });
  it('loginIndicator (elemen halaman login) dibedakan dari input', () => {
    present.add('#prompt-textarea');
    present.add('a[href*="login"]');
    const selectors = { ...baseSelectors, loginIndicator: 'a[href*="login"]' };
    expect(detectBlockerGeneric(selectors)).toBe('logged_out');
    expect(isLoggedInGeneric(selectors)).toBe(false);
    present.delete('a[href*="login"]');
    expect(detectBlockerGeneric(selectors)).toBeNull();
    expect(isLoggedInGeneric(selectors)).toBe(true);
  });
});

describe('H5 pacing recordPrompt', () => {
  const store = new Map<string, unknown>();
  beforeEach(() => {
    store.clear();
    (globalThis as unknown as { chrome: unknown }).chrome = {
      storage: {
        local: {
          get: async (key: string) => ({ [key]: store.get(key) }),
          set: async (items: Record<string, unknown>) => {
            for (const [k, v] of Object.entries(items)) store.set(k, v);
          },
        },
      },
    };
  });
  afterEach(() => {
    vi.restoreAllMocks();
    delete (globalThis as unknown as { chrome?: unknown }).chrome;
  });

  it('recordPrompt lalu checkPacing langsung ditolak (jeda 20 detik) dan usedToday naik', async () => {
    const { checkPacing, recordPrompt } = await import('../src/engine/pacing');
    const first = await recordPrompt('chatgpt');
    expect(first.allowed).toBe(true);
    expect(first.usedToday).toBe(1);
    const second = await checkPacing('chatgpt');
    expect(second.allowed).toBe(false);
    expect(second.waitSeconds).toBeGreaterThan(0);
    // Situs lain tidak terpengaruh.
    expect((await checkPacing('claude')).allowed).toBe(true);
  });
  it('batas harian 40 tercapai -> ditolak', async () => {
    const { checkPacing, recordPrompt } = await import('../src/engine/pacing');
    let now = Date.now();
    vi.spyOn(Date, 'now').mockImplementation(() => now);
    for (let i = 0; i < 40; i++) {
      const r = await recordPrompt('gemini');
      expect(r.allowed).toBe(true);
      now += 21_000;
    }
    const over = await checkPacing('gemini');
    expect(over.allowed).toBe(false);
    expect(over.usedToday).toBe(40);
  });
});
