// MUFAKAT Room — Storage Dexie (Claude §T2).
// runs, messages, gateResults, usage. Semua data lokal (IndexedDB +
// chrome.storage.local). Tidak ada server eksternal / analytics.
import Dexie, { type Table } from 'dexie';

export interface RunRecord {
  id: string;
  idea: string;
  state: string;
  roundNo: number;
  providers: string[];
  createdAt: number;
  /** N5 (putaran 2): labelMap per ronde — label anonim (A/B/C) -> provider.
   *  Dibuat SEKALI saat masuk fase kritik ronde itu, lalu dipakai di
   *  kritik, rapat, dan spesifikasi. Tanpa ini label berubah setiap
   *  "Susun prompt" dan pemenang voting tidak bisa dipetakan balik.
   *  Properti baru pada record Dexie tidak butuh migrasi skema (bukan
   *  index); record lama yang belum punya labelMap dibaca sebagai
   *  undefined dan ditangani pemanggil (spesifikasi menolak fallback). */
  labelMap?: Record<number, Record<string, string>>;
}

export interface MessageRecord {
  id?: number;
  runId: string;
  round: number;
  phase: string;
  provider: string;
  source: 'user imported' | 'assisted fill reply';
  rawText: string;
  parseStatus: 'ok' | 'repair_needed' | 'unparsed';
  importedAt: number;
}

export interface GateResultRecord {
  id?: number;
  runId: string;
  tool: string;
  passed: boolean;
  findings: string;
  createdAt: number;
}

export interface UsageRecord {
  id?: number;
  site: string;
  day: string;
  promptsCopied: number;
}

export class MufakatRoomDb extends Dexie {
  runs!: Table<RunRecord, string>;
  messages!: Table<MessageRecord, number>;
  gateResults!: Table<GateResultRecord, number>;
  usage!: Table<UsageRecord, number>;

  constructor() {
    super('mufakat-room');
    this.version(1).stores({
      runs: 'id, state, createdAt',
      messages: '++id, runId, round, provider',
      gateResults: '++id, runId, tool',
      usage: '++id, site, day',
    });
  }
}

export const db = new MufakatRoomDb();
