export interface Webhook {
  id: number;
  name?: string;
  url: string;
  events: string[];
  is_active: boolean;
  secret?: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface WebhookCreate {
  name?: string;
  url: string;
  events: string[];
  is_active?: boolean;
  secret?: string;
  description?: string;
}

export interface WebhookUpdate {
  name?: string;
  url?: string;
  events?: string[];
  is_active?: boolean;
  secret?: string;
  description?: string;
}

export interface WebhookDelivery {
  id: number;
  webhook_id: number;
  event: string;
  event_type?: string;
  status: string;
  response_code?: number;
  response_body?: string;
  attempted_at?: string;
  created_at?: string;
}
