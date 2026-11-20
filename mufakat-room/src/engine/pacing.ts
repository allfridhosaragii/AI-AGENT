// MUFAKAT Room — Pacing (Claude §0.1, §T8).
// Jeda minimum 20 detik antar-prompt ke situs yang sama; batas harian
// per situs default 40. Saat batas tercapai -> ronde ditunda (bukan diakali).
export const MIN_INTERVAL_SECONDS = 20;
export const DEFAULT_DAILY_LIMIT = 40;

export interface PacingDecision {
  allowed: boolean;
  reason: string;
  waitSeconds: number;
  usedToday: number;
  dailyLimit: number;
}

interface UsageLedger {
  lastSent: Record<string, number>;
  daily: Record<string, Record<string, number>>;
}

const STORAGE_KEY = 'mufakat-room-usage';

async function loadLedger(): Promise<UsageLedger> {
  const stored = await chrome.storage.local.get(STORAGE_KEY);
  return (stored[STORAGE_KEY] as UsageLedger | undefined) ?? { lastSent: {}, daily: {} };
}

async function saveLedger(ledger: UsageLedger): Promise<void> {
  await chrome.storage.local.set({ [STORAGE_KEY]: ledger });
}

export async function checkPacing(site: string, dailyLimit = DEFAULT_DAILY_LIMIT): Promise<PacingDecision> {
  const ledger = await loadLedger();
  const today = new Date().toISOString().slice(0, 10);
  const usedToday = ledger.daily[site]?.[today] ?? 0;
  if (usedToday >= dailyLimit) {
    return { allowed: false, reason: `Batas harian tercapai (${usedToday}/${dailyLimit} prompt ke ${site}). Ronde ditunda sampai besok.`, waitSeconds: 0, usedToday, dailyLimit };
  }
  const last = ledger.lastSent[site];
  if (last !== undefined) {
    const elapsed = (Date.now() - last) / 1000;
    if (elapsed < MIN_INTERVAL_SECONDS) {
      return { allowed: false, reason: `Jeda minimum belum terpenuhi untuk ${site}.`, waitSeconds: MIN_INTERVAL_SECONDS - elapsed, usedToday, dailyLimit };
    }
  }
  return { allowed: true, reason: 'OK', waitSeconds: 0, usedToday, dailyLimit };
}

export async function recordPrompt(site: string): Promise<PacingDecision> {
  const decision = await checkPacing(site);
  if (!decision.allowed) return decision;
  const ledger = await loadLedger();
  const today = new Date().toISOString().slice(0, 10);
  ledger.lastSent[site] = Date.now();
  ledger.daily[site] = ledger.daily[site] ?? {};
  ledger.daily[site][today] = (ledger.daily[site][today] ?? 0) + 1;
  await saveLedger(ledger);
  return { ...decision, usedToday: ledger.daily[site][today] };
}
