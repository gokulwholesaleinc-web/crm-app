import { type ConnectionSyncStatus } from '../../../api/marketing';
import { type SourceFreshness } from '../components/DataTrustBadge';
import { platformLabel } from './platformLabel';

/** Map per-connection sync status → DataTrustBadge source freshness (shared by the
 *  reporting tabs so the freshness chips read identically everywhere). */
export function syncToSources(connections: ConnectionSyncStatus[]): SourceFreshness[] {
  return connections.map((c) => ({
    source: platformLabel(c.platform),
    lastSyncedAt: c.last_synced_at,
    status: c.status,
  }));
}
