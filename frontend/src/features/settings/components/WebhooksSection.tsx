/**
 * Webhooks management section for Settings page.
 * Lists webhooks, allows create/edit/delete, shows delivery logs, test button.
 */

import { useState } from 'react';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import {
  useWebhooks,
  useCreateWebhook,
  useUpdateWebhook,
  useDeleteWebhook,
  useTestWebhook,
  useWebhookDeliveries,
} from '../../../hooks/useWebhooks';
import type { Webhook, WebhookCreate, WebhookUpdate } from '../../../types';
import {
  PlusIcon,
  TrashIcon,
  PencilSquareIcon,
  CheckCircleIcon,
  XCircleIcon,
  BeakerIcon,
  ChevronDownIcon,
  ChevronUpIcon,
} from '@heroicons/react/24/outline';

const AVAILABLE_EVENTS = [
  'lead.created',
  'lead.updated',
  'contact.created',
  'contact.updated',
  'company.created',
  'company.updated',
  'opportunity.created',
  'opportunity.updated',
  'opportunity.stage_changed',
  'activity.created',
];

function WebhookForm({
  webhook,
  onSubmit,
  onCancel,
  isLoading,
}: {
  webhook?: Webhook;
  onSubmit: (data: WebhookCreate | WebhookUpdate) => void;
  onCancel: () => void;
  isLoading: boolean;
}) {
  const [name, setName] = useState(webhook?.name || '');
  const [url, setUrl] = useState(webhook?.url || '');
  const [secret, setSecret] = useState(webhook?.secret || '');
  const [events, setEvents] = useState<string[]>(webhook?.events || []);
  const [isActive, setIsActive] = useState(webhook?.is_active ?? true);

  const toggleEvent = (event: string) => {
    setEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const data = {
      name,
      url,
      events,
      secret: secret || undefined,
      is_active: isActive,
    };
    onSubmit(data);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="webhook-name" className="block text-sm font-medium text-gray-700">
          Name
        </label>
        <input
          id="webhook-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        />
      </div>
      <div>
        <label htmlFor="webhook-url" className="block text-sm font-medium text-gray-700">
          URL
        </label>
        <input
          id="webhook-url"
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          placeholder="https://example.com/webhook"
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        />
      </div>
      <div>
        <label htmlFor="webhook-secret" className="block text-sm font-medium text-gray-700">
          Secret (optional, for HMAC signature)
        </label>
        <input
          id="webhook-secret"
          type="text"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        />
      </div>
      <div>
        <span className="block text-sm font-medium text-gray-700 mb-2">Events</span>
        <div className="grid grid-cols-2 gap-2">
          {AVAILABLE_EVENTS.map((event) => (
            <label key={event} className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={events.includes(event)}
                onChange={() => toggleEvent(event)}
                className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              {event}
            </label>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <input
          id="webhook-active"
          type="checkbox"
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
          className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
        />
        <label htmlFor="webhook-active" className="text-sm text-gray-700">
          Active
        </label>
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={isLoading || events.length === 0}>
          {isLoading ? <Spinner size="sm" /> : webhook ? 'Update' : 'Create'}
        </Button>
      </div>
    </form>
  );
}

function DeliveryLog({ webhookId }: { webhookId: number }) {
  const { data: deliveries, isLoading } = useWebhookDeliveries(webhookId);

  if (isLoading) return <Spinner size="sm" />;
  if (!deliveries?.length) {
    return <p className="text-sm text-gray-500">No deliveries yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="text-left py-2 px-2 font-medium text-gray-500">Event</th>
            <th className="text-left py-2 px-2 font-medium text-gray-500">Status</th>
            <th className="text-left py-2 px-2 font-medium text-gray-500">Code</th>
            <th className="text-left py-2 px-2 font-medium text-gray-500">Time</th>
          </tr>
        </thead>
        <tbody>
          {deliveries.map((d) => (
            <tr key={d.id} className="border-b border-gray-100">
              <td className="py-2 px-2">{d.event_type}</td>
              <td className="py-2 px-2">
                <span
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                    d.status === 'success'
                      ? 'bg-green-100 text-green-700'
                      : 'bg-red-100 text-red-700'
                  }`}
                >
                  {d.status === 'success' ? (
                    <CheckCircleIcon className="h-3 w-3" aria-hidden="true" />
                  ) : (
                    <XCircleIcon className="h-3 w-3" aria-hidden="true" />
                  )}
                  {d.status}
                </span>
              </td>
              <td className="py-2 px-2">{d.response_code || '-'}</td>
              <td className="py-2 px-2">
                {new Intl.DateTimeFormat('en-US', {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                }).format(new Date(d.attempted_at))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function WebhooksSection() {
  const { data: webhooks, isLoading } = useWebhooks();
  const createMutation = useCreateWebhook();
  const updateMutation = useUpdateWebhook();
  const deleteMutation = useDeleteWebhook();
  const testMutation = useTestWebhook();
  const [showForm, setShowForm] = useState(false);
  const [editingWebhook, setEditingWebhook] = useState<Webhook | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const handleCreate = (data: WebhookCreate | WebhookUpdate) => {
    createMutation.mutate(data as WebhookCreate, {
      onSuccess: () => setShowForm(false),
    });
  };

  const handleUpdate = (data: WebhookCreate | WebhookUpdate) => {
    if (!editingWebhook) return;
    updateMutation.mutate(
      { id: editingWebhook.id, data: data as WebhookUpdate },
      { onSuccess: () => setEditingWebhook(null) }
    );
  };

  return (
    <Card>
      <CardHeader
        title="Webhooks"
        description="Send HTTP callbacks when events occur in the CRM"
        action={
          <Button
            size="sm"
            leftIcon={<PlusIcon className="h-4 w-4" />}
            onClick={() => {
              setShowForm(true);
              setEditingWebhook(null);
            }}
          >
            Add Webhook
          </Button>
        }
      />
      <CardBody className="p-4 sm:p-6">
        {showForm && !editingWebhook && (
          <div className="mb-4 p-4 border border-gray-200 rounded-lg">
            <h4 className="text-sm font-medium text-gray-900 mb-3">New Webhook</h4>
            <WebhookForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              isLoading={createMutation.isPending}
            />
          </div>
        )}

        {isLoading ? (
          <div className="flex justify-center py-8">
            <Spinner size="lg" />
          </div>
        ) : !webhooks?.length ? (
          <p className="text-sm text-gray-500 text-center py-8">
            No webhooks configured yet. Click "Add Webhook" to get started.
          </p>
        ) : (
          <div className="space-y-3">
            {webhooks.map((webhook) => (
              <div
                key={webhook.id}
                className="border border-gray-200 rounded-lg"
              >
                {editingWebhook?.id === webhook.id ? (
                  <div className="p-4">
                    <h4 className="text-sm font-medium text-gray-900 mb-3">
                      Edit Webhook
                    </h4>
                    <WebhookForm
                      webhook={webhook}
                      onSubmit={handleUpdate}
                      onCancel={() => setEditingWebhook(null)}
                      isLoading={updateMutation.isPending}
                    />
                  </div>
                ) : (
                  <>
                    <div className="flex items-center justify-between p-4">
                      <div className="flex items-center gap-3 min-w-0">
                        <span
                          className={`inline-block h-2.5 w-2.5 rounded-full flex-shrink-0 ${
                            webhook.is_active ? 'bg-green-500' : 'bg-gray-300'
                          }`}
                        />
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">
                            {webhook.name}
                          </p>
                          <p className="text-xs text-gray-500 truncate">
                            {webhook.url}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => testMutation.mutate(webhook.id)}
                          disabled={testMutation.isPending}
                          aria-label="Test webhook"
                        >
                          <BeakerIcon className="h-4 w-4" aria-hidden="true" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingWebhook(webhook)}
                          aria-label="Edit webhook"
                        >
                          <PencilSquareIcon className="h-4 w-4" aria-hidden="true" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (window.confirm('Delete this webhook?')) {
                              deleteMutation.mutate(webhook.id);
                            }
                          }}
                          aria-label="Delete webhook"
                        >
                          <TrashIcon className="h-4 w-4 text-red-500" aria-hidden="true" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            setExpandedId(expandedId === webhook.id ? null : webhook.id)
                          }
                          aria-label={expandedId === webhook.id ? 'Collapse' : 'Expand'}
                        >
                          {expandedId === webhook.id ? (
                            <ChevronUpIcon className="h-4 w-4" aria-hidden="true" />
                          ) : (
                            <ChevronDownIcon className="h-4 w-4" aria-hidden="true" />
                          )}
                        </Button>
                      </div>
                    </div>
                    <div className="px-4 pb-2">
                      <div className="flex flex-wrap gap-1">
                        {webhook.events.map((event) => (
                          <span
                            key={event}
                            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600"
                          >
                            {event}
                          </span>
                        ))}
                      </div>
                    </div>
                    {expandedId === webhook.id && (
                      <div className="border-t border-gray-200 p-4">
                        <h5 className="text-sm font-medium text-gray-700 mb-2">
                          Delivery Log
                        </h5>
                        <DeliveryLog webhookId={webhook.id} />
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
