/**
 * Behavioural tests for the questionnaire/upload form builder.
 *
 * No external boundary (no pdf.js) — the component + its emit logic run for
 * real. We assert the SHAPE of the field_definitions it produces matches the
 * backend per-kind validators (kinds/questionnaire.py, kinds/upload_request.py),
 * so the builder can't ship definitions the API would 422.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { OnboardingFormBuilder } from './OnboardingFormBuilder';

const noop = () => {};

describe('OnboardingFormBuilder', () => {
  it('emits a clean short_text question (required toggled)', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <OnboardingFormBuilder
        isOpen
        onClose={noop}
        templateName="Intake"
        kind="questionnaire"
        currentFields={[]}
        onSave={onSave}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Add question' }));
    await user.type(screen.getByLabelText('Question'), 'What is your EIN');
    await user.click(screen.getByRole('switch', { name: 'Required' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(onSave).toHaveBeenCalledWith([
      { id: 'q1', kind: 'short_text', label: 'What is your EIN', required: true },
    ]);
  });

  it('emits a single_choice question with a non-empty option value + label', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <OnboardingFormBuilder
        isOpen
        onClose={noop}
        templateName="Intake"
        kind="questionnaire"
        currentFields={[]}
        onSave={onSave}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Add question' }));
    await user.type(screen.getByLabelText('Question'), 'Pick one');
    await user.selectOptions(screen.getByLabelText('Type'), 'single_choice');
    await user.click(screen.getByRole('button', { name: 'Add option' }));
    await user.type(screen.getByLabelText('Option 1 label'), 'Red');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(onSave).toHaveBeenCalledWith([
      {
        id: 'q1',
        kind: 'single_choice',
        label: 'Pick one',
        required: false,
        options: [{ value: 'opt1', label: 'Red' }],
      },
    ]);
  });

  it('emits a file_upload field with the default caps', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <OnboardingFormBuilder
        isOpen
        onClose={noop}
        templateName="Assets"
        kind="upload_request"
        currentFields={[]}
        onSave={onSave}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Add file field' }));
    await user.type(screen.getByLabelText('File label'), 'Gov ID');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(onSave).toHaveBeenCalledWith([
      { id: 'f1', kind: 'file_upload', label: 'Gov ID', required: false, maxFiles: 1, maxMB: 10 },
    ]);
  });

  it('emits sensitive: true when an upload field is marked sensitive', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <OnboardingFormBuilder
        isOpen
        onClose={noop}
        templateName="Assets"
        kind="upload_request"
        currentFields={[]}
        onSave={onSave}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Add file field' }));
    await user.type(screen.getByLabelText('File label'), 'Gov ID');
    await user.click(screen.getByRole('switch', { name: 'Sensitive (restricted access)' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(onSave).toHaveBeenCalledWith([
      {
        id: 'f1',
        kind: 'file_upload',
        label: 'Gov ID',
        required: false,
        maxFiles: 1,
        maxMB: 10,
        sensitive: true,
      },
    ]);
  });

  it('blocks save until every field has a label', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <OnboardingFormBuilder
        isOpen
        onClose={noop}
        templateName="Intake"
        kind="questionnaire"
        currentFields={[]}
        onSave={onSave}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Add question' }));
    expect(screen.getByText('Every field needs a label.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(onSave).not.toHaveBeenCalled();
  });
});
