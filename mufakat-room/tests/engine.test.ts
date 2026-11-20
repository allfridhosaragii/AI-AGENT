// MUFAKAT Room — test engine (vitest). Dijalankan dengan `pnpm test`
// setelah `pnpm install`. BELUM TERJALANKAN di VM ini (pnpm tidak tersedia).
import { describe, expect, it } from 'vitest';
import { parseReply, extractLastJsonBlock } from '../src/engine/parser';
import { bordaCount, decideConsensus, detectFalseConsensus } from '../src/engine/consensus';
import { scanText } from '../src/engine/secretScan';
import { createDebateMachine } from '../src/engine/stateMachine';

describe('parser', () => {
  it('mengambil blok json terakhir', () => {
    const text = 'dulu ```json\n{"phase": "proposal", "summary": "a"}\n``` lalu ```json\n{"phase": "proposal", "summary": "b"}\n```';
    expect(extractLastJsonBlock(text)).toContain('"b"');
    expect(parseReply(text).status).toBe('ok');
  });
  it('tanpa blok json -> unparsed', () => {
    expect(parseReply('hanya teks biasa').status).toBe('unparsed');
  });
  it('json rusak -> repair_needed, lalu unparsed setelah 1x repair', () => {
    const broken = '```json\n{"phase": "proposal",\n```';
    expect(parseReply(broken).status).toBe('repair_needed');
    expect(parseReply(broken, true).status).toBe('unparsed');
  });
});

describe('konsensus', () => {
  it('mufakat 2/3 tanpa blocking', () => {
    const result = decideConsensus(
      [
        { agentId: 'a', decision: 'approve', ranking: ['A', 'B', 'C'] },
        { agentId: 'b', decision: 'approve', ranking: ['A', 'C', 'B'] },
        { agentId: 'c', decision: 'revise', ranking: ['B', 'A', 'C'] },
      ],
      [],
    );
    expect(result.decision).toBe('mufakat');
    expect(result.winner).toBe('A');
  });
  it('blocking menggagalkan mufakat', () => {
    const result = decideConsensus(
      [{ agentId: 'a', decision: 'approve', ranking: ['A', 'B'] }],
      [{ severity: 'blocking', text: 'SQL injection' }],
    );
    expect(result.decision).toBe('belum_mufakat');
  });
  it('borda count', () => {
    expect(bordaCount([['A', 'B', 'C'], ['A', 'C', 'B']]).A).toBe(4);
  });
  it('sepakat palsu terdeteksi', () => {
    expect(detectFalseConsensus(['pakai FastAPI saja', 'pakai FastAPI saja'])).toBe(true);
    expect(detectFalseConsensus(['pakai FastAPI', 'pakai Flask'])).toBe(false);
  });
});

describe('secret scan', () => {
  it('memblokir api key dan private key', () => {
    expect(scanText('api_key = "sk-abcdefghijklmnopqrst"').length).toBeGreaterThan(0);
    expect(scanText('-----BEGIN PRIVATE KEY-----').length).toBeGreaterThan(0);
  });
  it('teks bersih lolos', () => {
    expect(scanText('Buat REST API todo dengan FastAPI.')).toEqual([]);
  });
});

describe('state machine', () => {
  it('alur debat sampai spesifikasi', () => {
    const machine = createDebateMachine();
    machine.transition('kirim_ide');
    machine.transition('usulan_diterima');
    machine.transition('kritik_diterima');
    expect(machine.transition('mufakat_atau_juri')).toBe('spesifikasi');
  });
  it('transisi ilegal ditolak', () => {
    const machine = createDebateMachine();
    expect(() => machine.transition('kode_selesai')).toThrow();
  });
});
