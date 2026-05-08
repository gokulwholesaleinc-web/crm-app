import { describe, it, expect } from 'vitest';
import { trimQuotedHtml, trimQuotedText } from './emailBodyTrim';

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
    expect(result.body).not.toContain('gmail_signature');
    expect(result.body).not.toContain('Link Creative');
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

  it('strips Outlook divRplyFwdMsg + everything after', () => {
    const html =
      '<p>Confirmed for Tuesday.</p>' +
      '<div id="divRplyFwdMsg">' +
      '<hr><b>From:</b> someone@example.com<br><b>Sent:</b> Monday<br>' +
      '</div>' +
      '<p>Original message body still tagged on after the divider.</p>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(true);
    expect(result.body).toContain('Confirmed for Tuesday');
    expect(result.body).not.toContain('divRplyFwdMsg');
    expect(result.body).not.toContain('Original message body');
  });

  it('returns the original body untouched when no marker present', () => {
    const html = '<p>Just a plain note, no quote.</p>';
    const result = trimQuotedHtml(html);
    expect(result.trimmed).toBe(false);
    expect(result.body).toBe(html);
  });

  it('keeps the new message when Gmail wraps it in <div dir="ltr"> with the quote', () => {
    // Real Gmail output puts new text + quoted reply inside the same
    // wrapper. Naive ancestor-walk-and-remove deletes the wrapper too,
    // which would erase the new text. Regression for that bug.
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
    expect(result.body).toContain('Approved');
    expect(result.body).not.toContain('Giancarlo');
  });

  it('handles empty input safely', () => {
    expect(trimQuotedHtml('')).toEqual({ body: '', trimmed: false });
  });
});

describe('trimQuotedText', () => {
  it('strips RFC 3676 -- signature delimiter and everything after', () => {
    const text = 'Hi there,\n\nLet me know.\n\n-- \nGiancarlo · CEO\nLink Creative\n+1 555 1234';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(true);
    expect(result.body).toContain('Let me know');
    expect(result.body).not.toContain('Giancarlo');
    expect(result.body).not.toContain('555 1234');
  });

  it('strips Gmail/Outlook "On <date>, X wrote:" reply intro', () => {
    const text =
      'Sounds great.\n\nOn Mon, Apr 28, 2026 at 10:15 AM Daisy <daisy@example.com> wrote:\n> previous message\n> > older message';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(true);
    expect(result.body).toContain('Sounds great');
    expect(result.body).not.toContain('previous message');
  });

  it('strips Outlook desktop From:/Sent: header block', () => {
    const text =
      'Approved.\n\nFrom: bob@example.com\nSent: Monday, April 28, 2026 10:15 AM\nTo: alice@example.com\nSubject: Quote\n\nOriginal body';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(true);
    expect(result.body).toContain('Approved');
    expect(result.body).not.toContain('Original body');
  });

  it('does NOT cut on inline references to "wrote"', () => {
    const text = 'Last week I wrote my report.\nFollow-up coming tomorrow.';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(false);
    expect(result.body).toBe(text);
  });

  it('returns input untouched when no boundary present', () => {
    const text = 'Just a normal line.\nAnother normal line.';
    const result = trimQuotedText(text);
    expect(result.trimmed).toBe(false);
    expect(result.body).toBe(text);
  });

  it('handles empty input safely', () => {
    expect(trimQuotedText('')).toEqual({ body: '', trimmed: false });
  });
});
