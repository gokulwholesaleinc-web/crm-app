// =============================================================================
// Workflow Types
// =============================================================================

export interface WorkflowRule {
  id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
  trigger_entity: string;
  trigger_event: string;
  conditions?: Record<string, unknown> | null;
  actions?: Record<string, unknown>[] | null;
  created_by_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowRuleCreate {
  name: string;
  description?: string | null;
  is_active?: boolean;
  trigger_entity: string;
  trigger_event: string;
  conditions?: Record<string, unknown> | null;
  actions?: Record<string, unknown>[] | null;
}

export interface WorkflowRuleUpdate {
  name?: string | null;
  description?: string | null;
  is_active?: boolean | null;
  trigger_entity?: string | null;
  trigger_event?: string | null;
  conditions?: Record<string, unknown> | null;
  actions?: Record<string, unknown>[] | null;
}

export interface WorkflowExecution {
  id: number;
  rule_id: number;
  entity_type: string;
  entity_id: number;
  status: string;
  result?: Record<string, unknown> | null;
  executed_at: string;
}

export interface WorkflowTestRequest {
  entity_type: string;
  entity_id: number;
}

// =============================================================================
// Sequence Types
// =============================================================================

export interface SequenceStep {
  step_number: number;
  type: 'email' | 'task' | 'wait';
  delay_days: number;
  template_id?: number;
  task_description?: string;
}

export interface Sequence {
  id: number;
  name: string;
  description?: string;
  steps: SequenceStep[];
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface SequenceCreate {
  name: string;
  description?: string;
  steps: SequenceStep[];
  is_active?: boolean;
}

export interface SequenceUpdate {
  name?: string;
  description?: string;
  steps?: SequenceStep[];
  is_active?: boolean;
}

export interface SequenceEnrollment {
  id: number;
  sequence_id: number;
  contact_id: number;
  current_step: number;
  status: 'active' | 'paused' | 'completed' | 'cancelled';
  created_at?: string;
  updated_at?: string;
}

export interface ProcessDueResult {
  processed: number;
  errors: number;
}

// =============================================================================
// Webhook Types
// =============================================================================

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
