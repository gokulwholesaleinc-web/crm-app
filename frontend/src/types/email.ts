/**
 * Email Thread Types
 */

export interface ThreadEmailItem {
  id: number;
  direction: 'inbound' | 'outbound';
  from_email: string | null;
  to_email: string;
  cc: string | null;
  subject: string;
  body: string | null;
  body_html: string | null;
  timestamp: string;
  status: string | null;
  open_count: number | null;
  attachments: unknown | null;
  thread_id: string | null;
}

export interface ThreadResponse {
  items: ThreadEmailItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
