/**
 * `@dnd-kit` ID helpers for the Lead kanban board.
 *
 * Card IDs encode both the lead id and the source stage id so the
 * `onDragEnd` handler can detect cross-stage drops without having to
 * cross-reference the rendered tree. Column IDs are used as fallback
 * droppable targets so leads can be dropped onto empty columns.
 */

export function encodeLeadDragId(leadId: number, stageId: number): string {
  return `lead:${leadId}:${stageId}`;
}

export function encodeLeadColumnId(stageId: number): string {
  return `lead-col:${stageId}`;
}

export function parseLeadDragId(
  id: string,
): { leadId: number; stageId: number } | null {
  const m = id.match(/^lead:(\d+):(\d+)$/);
  if (!m) return null;
  return { leadId: Number(m[1]), stageId: Number(m[2]) };
}
