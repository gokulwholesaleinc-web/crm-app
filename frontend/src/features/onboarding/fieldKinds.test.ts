import { describe, it, expect } from 'vitest';
import { templateSendReadiness } from './fieldKinds';
import type { OnboardingTemplate } from '../../types';

/**
 * templateSendReadiness mirrors the backend ``_template_send_status`` gate so
 * every picker shows the same readiness the server enforces at create. The H1
 * case — an esign template with a PDF but NO signature field — must read as
 * NOT ready (it can never be signed), matching the backend.
 */

function tmpl(over: Partial<OnboardingTemplate> = {}): OnboardingTemplate {
  return {
    id: 1, name: 'T', description: null, service_tag: null, owner_id: null,
    kind: 'esign_pdf', has_pdf: true, pdf_version: 1, field_definitions: [],
    requires_esign: false, is_active: true,
    created_at: '2026-06-01T00:00:00Z', updated_at: '2026-06-01T00:00:00Z',
    ...over,
  };
}

const sig = {
  id: 'sig1', kind: 'signature' as const, label: 'Signature', required: true,
  prefill: null, page: 1, x: 10, y: 10, w: 120, h: 40,
};

describe('templateSendReadiness', () => {
  it('esign with a PDF and a signature field is ready', () => {
    expect(templateSendReadiness(tmpl({ has_pdf: true, field_definitions: [sig] })))
      .toEqual({ ready: true });
  });

  it('esign with a PDF but NO signature field is not ready (H1)', () => {
    const r = templateSendReadiness(
      tmpl({ has_pdf: true, field_definitions: [{ ...sig, kind: 'text' }] }),
    );
    expect(r.ready).toBe(false);
    expect(r.reason).toMatch(/signature/i);
  });

  it('esign with no PDF is not ready', () => {
    const r = templateSendReadiness(tmpl({ has_pdf: false, field_definitions: [] }));
    expect(r.ready).toBe(false);
    expect(r.reason).toMatch(/PDF/i);
  });

  it('a form kind with at least one field is ready (signature not required)', () => {
    expect(
      templateSendReadiness(
        tmpl({
          kind: 'questionnaire', has_pdf: false,
          field_definitions: [{ id: 'q1', kind: 'short_text', label: 'Name', required: true }],
        }),
      ),
    ).toEqual({ ready: true });
  });

  it('an empty form kind is not ready (D2 empty-form guard)', () => {
    const r = templateSendReadiness(
      tmpl({ kind: 'questionnaire', has_pdf: false, field_definitions: [] }),
    );
    expect(r.ready).toBe(false);
    expect(r.reason).toMatch(/questions or fields/i);
  });

  it('defaults a missing kind to esign_pdf', () => {
    const r = templateSendReadiness(tmpl({ kind: undefined, has_pdf: false }));
    expect(r.ready).toBe(false);
    expect(r.reason).toMatch(/PDF/i);
  });
});
