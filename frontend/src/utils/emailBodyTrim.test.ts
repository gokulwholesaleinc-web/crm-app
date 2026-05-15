import { describe, it, expect } from 'vitest';
import { trimQuotedHtml, trimQuotedText, trimToggleLabel } from './emailBodyTrim';

describe('trimQuotedHtml', () => {
  it('strips Gmail quote blocks', () => {
    const html =
      '<p>Hi Daisy, attached is the invoice.</p>' +
      '<div class="gmail_quote">' +
      '<div>On Mon, Apr 28 at 10am Daisy &lt;daisy@example.com&gt; wrote:</div>' +
      '<blockquote>old message body</blockquote>' +
      '</div>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('quote');
    expect(result.body).toContain('attached is the invoice');
    expect(result.body).not.toContain('old message body');
    expect(result.body).not.toContain('gmail_quote');
  });

  it('strips Gmail explicit signature wrappers', () => {
    const html =
      '<p>Best regards,</p>' +
      '<div class="gmail_signature" data-smartmail="gmail_signature">' +
      '<table><tr><td><img src="data:image/png;base64,abc" alt="logo"></td>' +
      '<td>Giancarlo · CEO · Link Creative</td></tr></table>' +
      '</div>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('signature');
    expect(result.body).not.toContain('gmail_signature');
    expect(result.body).not.toContain('Link Creative');
  });

  it('reports cut=both when both quote and signature were trimmed', () => {
    const html =
      '<p>Approved.</p>' +
      '<div class="gmail_signature">Giancarlo</div>' +
      '<div class="gmail_quote">previous</div>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('both');
    expect(result.body).toContain('Approved');
  });

  it('strips Apple Mail blockquote type=cite', () => {
    const html =
      '<div>Sounds good.</div>' +
      '<blockquote type="cite">' +
      'Sent from my iPhone — original text here' +
      '</blockquote>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.body).toContain('Sounds good');
    expect(result.body).not.toContain('original text here');
  });

  it('strips Outlook divRplyFwdMsg + the trailing stray <hr> and quoted body', () => {
    const html =
      '<p>Confirmed for Tuesday.</p>' +
      '<hr>' +
      '<div id="divRplyFwdMsg">' +
      '<b>From:</b> someone@example.com<br><b>Sent:</b> Monday<br>' +
      '</div>' +
      '<p>Original message body still tagged on after the divider.</p>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.body).toContain('Confirmed for Tuesday');
    expect(result.body).not.toContain('divRplyFwdMsg');
    expect(result.body).not.toContain('Original message body');
    // Stray <hr> that lived between the new message and the divider
    // gets cleaned up by trimDanglingTrailers — it has no content under
    // it after the cut and would render as a useless rule.
    expect(result.body).not.toContain('<hr>');
  });

  it('returns the original body untouched when no marker present', () => {
    const html = '<p>Just a plain note, no quote.</p>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(false);
    expect(result.cut).toBe('none');
    expect(result.body).toBe(html);
  });

  it('keeps the new message when Gmail wraps it in <div dir="ltr"> with the quote', () => {
    // Real Gmail output puts new text + quoted reply inside the same
    // wrapper. Naive ancestor-walk-and-remove deletes the wrapper too,
    // which would erase the new text. Range-based cut preserves it.
    const html =
      '<div dir="ltr">' +
      '<p>Approved — please proceed.</p><br>' +
      '<div class="gmail_quote"><blockquote>can you confirm?</blockquote></div>' +
      '</div>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.body).toContain('Approved');
    expect(result.body).not.toContain('can you confirm?');
  });

  it('keeps the new message when Apple Mail wraps it in an outer <div> with the cite blockquote', () => {
    const html =
      '<div>' +
      '<div>Sounds good.</div>' +
      '<blockquote type="cite">original draft</blockquote>' +
      '</div>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.body).toContain('Sounds good');
    expect(result.body).not.toContain('original draft');
  });

  it('keeps content before a Gmail signature even when the sig is nested in a wrapper', () => {
    const html =
      '<div dir="ltr">' +
      '<p>Approved.</p>' +
      '<div class="gmail_signature">Giancarlo · CEO</div>' +
      '</div>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('signature');
    expect(result.body).toContain('Approved');
    expect(result.body).not.toContain('Giancarlo');
  });

  it('cuts at an unmarked "Best," sign-off block (heuristic)', () => {
    const html =
      '<p>Sounds great.</p>' +
      '<p>Best,</p>' +
      '<p>Giancarlo</p>' +
      '<p>CEO · Link Creative</p>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('signature');
    expect(result.body).toContain('Sounds great');
    expect(result.body).not.toContain('Giancarlo');
    expect(result.body).not.toContain('Link Creative');
  });

  it('cuts at "Sent from my iPhone" auto-signature (heuristic)', () => {
    const html =
      '<div>Sounds good — moving forward.</div>' +
      '<div>Sent from my iPhone</div>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('signature');
    expect(result.body).toContain('Sounds good');
    expect(result.body).not.toContain('Sent from my iPhone');
  });

  it('cuts at the corporate confidentiality footer (no explicit wrapper)', () => {
    // Some clients don't wrap the signature in gmail_signature and the
    // author skips the conventional sign-off ("Best,", "Thanks,"), so
    // the only reliable end-of-body marker is the legal boilerplate.
    const html =
      '<div>Quick update on the campaign — proofs attached.</div>' +
      '<div>This email and any files transmitted with it are confidential ' +
      'and intended solely for the use of the individual or entity to ' +
      'whom they are addressed.</div>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('signature');
    expect(result.body).toContain('proofs attached');
    expect(result.body).not.toContain('confidential');
  });

  it('cuts at Gmail [image:] plain-text placeholders rendered inside HTML', () => {
    // Defensive: some Gmail rendering paths leak the plain-text
    // alternative into the HTML alternative when an inline image
    // can't be referenced as cid:. The placeholder always sits at
    // signature scope.
    const html =
      '<div>See attached pricing notes.</div>' +
      '<div>Lorenzo Costa<br>Founder &amp; CEO | Link Creative</div>' +
      '<div>[image: instagram] <a href="https://instagram.com/co">link</a></div>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('signature');
    expect(result.body).toContain('attached pricing notes');
    expect(result.body).not.toContain('Lorenzo Costa');
  });

  it('does NOT trip on "best laid plans" mid-sentence', () => {
    const html = '<p>The best laid plans of mice and men go awry.</p>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(false);
    expect(result.cut).toBe('none');
    expect(result.body).toBe(html);
  });

  it('does NOT delete a single-paragraph "Thanks," reply', () => {
    const html = '<div>Thanks,</div>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(false);
    expect(result.body).toContain('Thanks');
  });

  it('does NOT delete a "Thanks" then name only', () => {
    const html = '<div>Thanks</div><div>Giancarlo</div>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(false);
    expect(result.body).toContain('Thanks');
    expect(result.body).toContain('Giancarlo');
  });

  it('handles empty input safely', () => {
    expect(trimQuotedHtml('')).toEqual({ body: '', trimmed: false, cut: 'none' });
  });
});

describe('trimQuotedText', () => {
  it('strips RFC 3676 -- signature delimiter and everything after', () => {
    const text = 'Hi there,\n\nLet me know.\n\n-- \nGiancarlo · CEO\nLink Creative\n+1 555 1234';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('signature');
    expect(result.body).toContain('Let me know');
    expect(result.body).not.toContain('Giancarlo');
    expect(result.body).not.toContain('555 1234');
  });

  it('strips Gmail/Outlook "On <date>, X wrote:" reply intro', () => {
    const text =
      'Sounds great.\n\nOn Mon, Apr 28, 2026 at 10:15 AM Daisy <daisy@example.com> wrote:\n> previous message\n> > older message';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('quote');
    expect(result.body).toContain('Sounds great');
    expect(result.body).not.toContain('previous message');
  });

  it('strips Outlook desktop From:/Sent: header block', () => {
    const text =
      'Approved.\n\nFrom: bob@example.com\nSent: Monday, April 28, 2026 10:15 AM\nTo: alice@example.com\nSubject: Quote\n\nOriginal body';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('quote');
    expect(result.body).toContain('Approved');
    expect(result.body).not.toContain('Original body');
  });

  it('cuts at unmarked "Best regards," sign-off (heuristic)', () => {
    const text = 'Sounds great.\n\nBest regards,\nGiancarlo\nLink Creative\n+1 555 1234';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('signature');
    expect(result.body).toContain('Sounds great');
    expect(result.body).not.toContain('Giancarlo');
    expect(result.body).not.toContain('555 1234');
  });

  it('cuts at "Sent from my iPhone" plain-text auto-sig', () => {
    const text = 'Looks good.\n\nSent from my iPhone';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('signature');
    expect(result.body).toBe('Looks good.');
  });

  it('does NOT delete a single-line "Thanks!" reply', () => {
    // Without the earlier-content guard, cutAt=0 → body becomes empty.
    const text = 'Thanks!';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(false);
    expect(result.body).toBe('Thanks!');
  });

  it('does NOT cut when "Thanks" is mid-paragraph', () => {
    const text = 'Thanks for the proposal — looks great.\nFollow-up notes inline.';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(false);
    expect(result.body).toBe(text);
  });

  it('does NOT cut on inline references to "wrote"', () => {
    const text = 'Last week I wrote my report.\nFollow-up coming tomorrow.';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(false);
    expect(result.cut).toBe('none');
    expect(result.body).toBe(text);
  });

  it('returns input untouched when no boundary present', () => {
    const text = 'Just a normal line.\nAnother normal line.';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(false);
    expect(result.body).toBe(text);
  });

  it('handles empty input safely', () => {
    expect(trimQuotedText('')).toEqual({ body: '', trimmed: false, cut: 'none' });
  });

  it('cuts at Gmail plain-text [image:] placeholders (signature start)', () => {
    // Lorenzo's signature gets emitted as plain text with inline-image
    // alt-text placeholders when the rendered body falls back to text
    // (Gmail send-as alias, image-blocked client). The placeholder line
    // is the cut marker — body text never contains "[image: foo]".
    const text =
      'Hi Martin,\n\n' +
      "I don't wanna overshoot or rush anything.\n\n" +
      'Have a great weekend.\n\n' +
      'Lorenzo Costa\n' +
      'Founder & CEO | Link Creative\n' +
      '350 W Ontario Street, Suite 5E, Chicago, IL, 60654\n' +
      'Phone: (630) 999-7922\n' +
      'Email: Lorenzo@linkcreativeco.com\n' +
      '[image: instagram] <https://www.instagram.com/linkcreativeco/>\n' +
      '[image: facebook] <https://www.facebook.com/...>\n';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('signature');
    expect(result.body).toContain('Have a great weekend');
    expect(result.body).not.toContain('[image: instagram]');
    expect(result.body).not.toContain('linkcreativeco.com');
  });

  it('cuts at the corporate confidentiality footer', () => {
    const text =
      'Quick update on the campaign — proofs attached.\n\n' +
      'Thanks,\n' +
      'Daisy\n\n' +
      'This email and any files transmitted with it are confidential ' +
      'and intended solely for the use of the individual or entity to ' +
      'whom they are addressed.\n';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('signature');
    expect(result.body).toContain('proofs attached');
    // The sign-off ("Thanks,") wins the race against the confidentiality
    // boilerplate because it appears first — either way the footer must
    // be off.
    expect(result.body).not.toContain('confidential');
  });

  it('cuts at "This message contains confidential information" variant', () => {
    const text =
      'See the attached invoice.\n\n' +
      'This message contains confidential information and is intended ' +
      'only for the individual named.';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(true);
    expect(result.cut).toBe('signature');
    expect(result.body).toContain('attached invoice');
    expect(result.body).not.toContain('confidential');
  });
});

describe('trimToggleLabel', () => {
  it('uses accurate copy for each cut variant', () => {
    expect(trimToggleLabel('quote', false)).toBe('Show quoted history');
    expect(trimToggleLabel('signature', false)).toBe('Show signature');
    expect(trimToggleLabel('both', false)).toBe('Show quoted history & signature');
    expect(trimToggleLabel('quote', true)).toBe('Hide quoted history');
    expect(trimToggleLabel('signature', true)).toBe('Hide signature');
  });

  it('returns empty string when nothing was cut', () => {
    expect(trimToggleLabel('none', false)).toBe('');
    expect(trimToggleLabel('none', true)).toBe('');
  });
});
