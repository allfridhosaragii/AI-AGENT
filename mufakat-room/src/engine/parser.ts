// MUFAKAT Room — Parser jawaban AI (Claude §3, §T5).
// Ambil blok ```json TERAKHIR, validasi dengan zod. Hasil:
// 'ok' | 'repair_needed' | 'unparsed' (maks 1x repair; masih gagal -> unparsed,
// tampilkan ke pengguna untuk diisi manual). Output AI adalah data tak tepercaya.
import { z } from 'zod';

export const AiReplySchema = z.object({
  phase: z
    .enum(['proposal', 'critique', 'meeting', 'spec', 'code', 'review', 'audit', 'test', 'revise', 'rebuttal'])
    .optional(),
  summary: z.string().max(1200).optional(),
  proposal: z.string().optional(),
  claims: z
    .array(z.object({ id: z.string(), text: z.string(), evidence: z.string().optional(), confidence: z.number().optional() }))
    .optional(),
  critiques: z
    .array(z.object({ target: z.string(), claim: z.string().optional(), severity: z.enum(['info', 'minor', 'major', 'blocking']), text: z.string() }))
    .optional(),
  vote: z
    .object({ decision: z.enum(['approve', 'revise', 'reject']), ranking: z.array(z.string()), confidence: z.number().optional() })
    .optional(),
  files: z
    .array(z.object({ path: z.string(), mode: z.enum(['replace', 'patch']), content: z.string() }))
    .optional(),
});

export type AiReply = z.infer<typeof AiReplySchema>;
export type ParseStatus = 'ok' | 'repair_needed' | 'unparsed';

export interface ParseResult {
  status: ParseStatus;
  payload: AiReply | null;
  error: string;
  repairAttempted: boolean;
}

// M3: izinkan \s* (nol atau lebih) setelah "json" — blok ```json{...}```
// tanpa newline dulu gagal parse. \n tetap didukung seperti sebelumnya.
const JSON_BLOCK_RE = /```(?:json)?\s*(.*?)```/gis;

export function extractLastJsonBlock(text: string): string | null {
  const matches = [...text.matchAll(JSON_BLOCK_RE)];
  return matches.length ? matches[matches.length - 1][1].trim() : null;
}

/** Fallback M3: teks hasil innerText kehilangan pagar ``` (DOM merender
 *  blok kode tanpa backtick). Cari objek {...} TERAKHIR yang valid JSON
 *  dengan pemindaian kurung seimbang yang sadar string. */
export function extractLastJsonObject(text: string): string | null {
  for (let start = text.lastIndexOf('{'); start >= 0; start = text.lastIndexOf('{', start - 1)) {
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let i = start; i < text.length; i++) {
      const ch = text[i];
      if (inString) {
        if (escaped) escaped = false;
        else if (ch === '\\') escaped = true;
        else if (ch === '"') inString = false;
        continue;
      }
      if (ch === '"') inString = true;
      else if (ch === '{') depth++;
      else if (ch === '}') {
        depth--;
        if (depth === 0) {
          const candidate = text.slice(start, i + 1);
          try {
            JSON.parse(candidate);
            return candidate;
          } catch {
            break; // objek ini rusak, coba '{' sebelumnya
          }
        }
      }
    }
  }
  return null;
}

export function parseReply(text: string, repairAttempted = false): ParseResult {
  // M3: dulu hanya blok berpagar; kini fallback ke objek {...} terakhir.
  const block = extractLastJsonBlock(text) ?? extractLastJsonObject(text);
  if (block === null) {
    return { status: 'unparsed', payload: null, error: 'Tidak ada blok ```json dalam jawaban.', repairAttempted };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(block);
  } catch (error) {
    if (repairAttempted) {
      return { status: 'unparsed', payload: null, error: `JSON rusak dan repair sudah dipakai 1x: ${String(error)}`, repairAttempted: true };
    }
    return { status: 'repair_needed', payload: null, error: `JSON rusak: ${String(error)}`, repairAttempted };
  }
  const validated = AiReplySchema.safeParse(parsed);
  if (!validated.success) {
    if (repairAttempted) {
      return { status: 'unparsed', payload: null, error: validated.error.message, repairAttempted: true };
    }
    return { status: 'repair_needed', payload: null, error: validated.error.message, repairAttempted };
  }
  return { status: 'ok', payload: validated.data, error: '', repairAttempted };
}

export function formatRepairPrompt(error: string): string {
  return (
    `Jawabanmu sebelumnya tidak bisa diparse karena format JSON-nya bermasalah (${error}). ` +
    'Tolong kirim ulang HANYA blok ```json yang valid sesuai skema, tanpa mengubah isi usulanmu. ' +
    'Tulis penjelasan singkat, lalu akhiri dengan SATU blok ```json sesuai skema.'
  );
}
