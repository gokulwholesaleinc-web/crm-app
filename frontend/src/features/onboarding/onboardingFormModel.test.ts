import { describe, it, expect } from 'vitest';
import { validate } from './onboardingFormModel';
import type { OnboardingQuestionnaireField } from '../../types';

/**
 * validate() mirrors the backend questionnaire handler client-side. These cover
 * the prefill allow-list (TW-PREFILL-VAL) and the option-value rules
 * (TW-OPTVAL-VAL) added so an imported/replayed bad definition is caught before
 * a late 422.
 */

const text = (over: Partial<OnboardingQuestionnaireField> = {}): OnboardingQuestionnaireField =>
  ({ id: 'q1', kind: 'short_text', label: 'Name', required: false, ...over }) as OnboardingQuestionnaireField;

const choice = (over: Partial<OnboardingQuestionnaireField> = {}): OnboardingQuestionnaireField =>
  ({
    id: 'c1', kind: 'single_choice', label: 'Pick', required: false,
    options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }],
    ...over,
  }) as OnboardingQuestionnaireField;

describe('onboardingFormModel.validate', () => {
  it('accepts a clean field list', () => {
    expect(validate([text(), choice()])).toBeNull();
  });

  it('accepts an allowed prefill', () => {
    expect(validate([text({ prefill: 'contact.name' })])).toBeNull();
  });

  it('rejects an unsupported prefill (mirrors ALLOWED_PREFILL)', () => {
    expect(validate([text({ prefill: 'contact.email' as never })])).toMatch(/prefill/i);
  });

  it('rejects a duplicate option value', () => {
    expect(
      validate([choice({ options: [{ value: 'x', label: 'A' }, { value: 'x', label: 'B' }] })]),
    ).toMatch(/unique/i);
  });

  it('rejects an empty option value', () => {
    expect(
      validate([choice({ options: [{ value: '', label: 'A' }] })]),
    ).toMatch(/value/i);
  });

  it('still rejects an empty option label', () => {
    expect(
      validate([choice({ options: [{ value: 'a', label: '  ' }] })]),
    ).toMatch(/label/i);
  });
});
