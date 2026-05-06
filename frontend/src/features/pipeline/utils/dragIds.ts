export function encodeLeadDragId(leadId: number, stageId: number): string {
  return `lead:${leadId}:${stageId}`;
}

export function encodeOppDragId(oppId: number, stageId: number): string {
  return `opp:${oppId}:${stageId}`;
}

export function encodeLeadColumnId(stageId: number): string {
  return `lead-col:${stageId}`;
}

export function encodeOppColumnId(stageId: number): string {
  return `opp-col:${stageId}`;
}

export function parseLeadDragId(id: string): { leadId: number; stageId: number } | null {
  const m = id.match(/^lead:(\d+):(\d+)$/);
  if (!m) return null;
  return { leadId: Number(m[1]), stageId: Number(m[2]) };
}

export function parseOppDragId(id: string): { oppId: number; stageId: number } | null {
  const m = id.match(/^opp:(\d+):(\d+)$/);
  if (!m) return null;
  return { oppId: Number(m[1]), stageId: Number(m[2]) };
}
