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
