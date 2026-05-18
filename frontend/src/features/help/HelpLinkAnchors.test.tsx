import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { SECTIONS } from './helpContent';

function collectTsxFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    const stat = statSync(path);
    if (stat.isDirectory()) return collectTsxFiles(path);
    return path.endsWith('.tsx') ? [path] : [];
  });
}

function collectHelpAnchors(): string[] {
  const files = collectTsxFiles(join(process.cwd(), 'src'));
  const anchors = new Set<string>();
  const helpLinkPattern = /<HelpLink\b[^>]*\sanchor="([^"]+)"/g;
  const hrefPattern = /\/help#([A-Za-z0-9_-]+)/g;

  for (const file of files) {
    const source = readFileSync(file, 'utf8');
    for (const match of source.matchAll(helpLinkPattern)) {
      anchors.add(match[1] ?? '');
    }
    for (const match of source.matchAll(hrefPattern)) {
      anchors.add(match[1] ?? '');
    }
  }

  anchors.delete('');
  return Array.from(anchors).sort();
}

describe('HelpLink anchors', () => {
  it('resolves every inline help anchor to rendered help content', () => {
    render(
      <>
        {SECTIONS.map((section) => (
          <article key={section.id} id={`help-section-${section.id}`}>
            {section.body}
          </article>
        ))}
      </>,
    );

    const missing = collectHelpAnchors().filter((anchor) => !document.getElementById(anchor));

    expect(missing).toEqual([]);
  });
});
