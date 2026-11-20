// MUFAKAT Room — Ekspor transkrip (Claude §T2).
// Transkrip -> Markdown per ronde; JSON mentah untuk audit.
// Tidak ada rahasia yang diekspor (prompt sudah lolos secret scan).
import { db, type MessageRecord } from './db';

export function renderTranscriptMarkdown(runId: string, idea: string, messages: MessageRecord[]): string {
  const lines = [`# Transkrip MUFAKAT Room — ${runId}`, '', `Ide: ${idea}`, ''];
  const rounds = [...new Set(messages.map((m) => m.round))].sort((a, b) => a - b);
  for (const round of rounds) {
    lines.push(`## Ronde ${round}`, '');
    for (const message of messages.filter((m) => m.round === round)) {
      lines.push(
        `### ${message.provider} (${message.phase}) — ${message.source}`,
        `Diimpor: ${new Date(message.importedAt).toISOString()} | Parse: ${message.parseStatus}`,
        '',
        message.rawText,
        '',
      );
    }
  }
  return lines.join('\n');
}

export async function exportRun(runId: string, idea: string): Promise<{ markdown: string; json: string }> {
  const messages = await db.messages.where('runId').equals(runId).toArray();
  return {
    markdown: renderTranscriptMarkdown(runId, idea, messages),
    json: JSON.stringify(messages, null, 2),
  };
}
