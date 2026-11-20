// MUFAKAT Room — State persisten rapat (M5).
// State machine TIDAK boleh tinggal di variabel modul service worker MV3:
// SW tidur setelah ±30 detik idle dan state hilang. Snapshot disimpan di
// chrome.storage.session (bertahan selama sesi browser, melewati tidur SW)
// dan dicerminkan ke chrome.storage.local (bertahan melewati restart
// browser). Di luar extension (test/node) dipakai fallback memori.
import type { DebateSnapshot } from '../engine/stateMachine';

const SESSION_KEY = 'mufakat-room-state';
const LOCAL_KEY = 'mufakat-room-state-backup';
const META_KEY = 'mufakat-room-meta';

export interface RoomMeta {
  runId: string;
  round: number;
  phase: string;
}

type ChromeStorageArea = {
  get(key: string): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
  remove(key: string): Promise<void>;
};

function storageArea(area: 'session' | 'local'): ChromeStorageArea | null {
  try {
    const chromeApi = (globalThis as unknown as { chrome?: { storage?: Record<string, ChromeStorageArea> } }).chrome;
    return chromeApi?.storage?.[area] ?? null;
  } catch {
    return null;
  }
}

const memoryFallback = new Map<string, unknown>();

async function areaGet(area: 'session' | 'local', key: string): Promise<unknown> {
  const store = storageArea(area);
  if (store) {
    const result = await store.get(key);
    return result[key];
  }
  return memoryFallback.get(`${area}:${key}`);
}

async function areaSet(area: 'session' | 'local', key: string, value: unknown): Promise<void> {
  const store = storageArea(area);
  if (store) {
    await store.set({ [key]: value });
    return;
  }
  memoryFallback.set(`${area}:${key}`, value);
}

export async function saveRoomState(snapshot: DebateSnapshot): Promise<void> {
  await areaSet('session', SESSION_KEY, snapshot);
  await areaSet('local', LOCAL_KEY, snapshot);
}

export async function loadRoomState(): Promise<DebateSnapshot | null> {
  const fromSession = (await areaGet('session', SESSION_KEY)) as DebateSnapshot | undefined;
  if (fromSession?.state) return fromSession;
  const fromLocal = (await areaGet('local', LOCAL_KEY)) as DebateSnapshot | undefined;
  return fromLocal?.state ? fromLocal : null;
}

export async function clearRoomState(): Promise<void> {
  const session = storageArea('session');
  const local = storageArea('local');
  if (session) await session.remove(SESSION_KEY);
  if (local) await local.remove(LOCAL_KEY);
  memoryFallback.delete(`session:${SESSION_KEY}`);
  memoryFallback.delete(`local:${LOCAL_KEY}`);
}

export async function saveRoomMeta(meta: RoomMeta): Promise<void> {
  await areaSet('local', META_KEY, meta);
}

export async function loadRoomMeta(): Promise<RoomMeta | null> {
  const meta = (await areaGet('local', META_KEY)) as RoomMeta | undefined;
  return meta?.runId ? meta : null;
}

/** Hapus meta rapat (dipakai "Hapus seluruh data rapat"). */
export async function clearRoomMeta(): Promise<void> {
  const local = storageArea('local');
  if (local) await local.remove(META_KEY);
  memoryFallback.delete(`local:${META_KEY}`);
}
