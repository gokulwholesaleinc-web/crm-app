export interface ChecklistItem {
  key: string;
  label: string;
  state: boolean | 'optional';
  hint?: string;
  action?: { label: string; onClick: () => void };
}

export function isChecklistReady(items: ChecklistItem[]): boolean {
  return items.every((item) => item.state === true || item.state === 'optional');
}
