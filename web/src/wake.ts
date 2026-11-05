/** Pull the command out of a heard phrase. Empty string means he woke with no command yet. */

export function commandAfterWake(transcript: string, alreadyAwake: boolean): string | null {
  const text = transcript
    .toLowerCase()
    .replace(/[^a-z\s']/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return null;
  const atStart = text.match(/^(?:hey\s+)?orion(?:\s+(.*))?$/);
  if (atStart) return (atStart[1] || "").trim();
  const later = text.match(/\bhey\s+orion(?:\s+(.*))?$/);
  if (later) return (later[1] || "").trim();
  return alreadyAwake ? text : null;
}
