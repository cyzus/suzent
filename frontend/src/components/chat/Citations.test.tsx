import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MarkdownRenderer } from './MarkdownRenderer';
import { CitationProvider, formatTextWithCitationReferences, type CitationSourcesMap } from './Citations';

const sources: CitationSourcesMap = new Map([
  [
    't0_src_1',
    {
      id: 't0_src_1',
      type: 'search',
      title: 'Example Source',
      url: 'https://example.com',
    },
  ],
  [
    't0_src_2',
    {
      id: 't0_src_2',
      type: 'webpage',
      title: 'Second Source',
      url: 'https://example.org',
    },
  ],
]);

function render(content: string): string {
  return renderToStaticMarkup(
    <CitationProvider sources={sources}>
      <MarkdownRenderer content={content} />
    </CitationProvider>,
  );
}

function renderWithSources(content: string, sourceMap: CitationSourcesMap): string {
  return renderToStaticMarkup(
    <CitationProvider sources={sourceMap}>
      <MarkdownRenderer content={content} />
    </CitationProvider>,
  );
}

describe('citation rendering', () => {
  it('renders PUA citation markers as badges', () => {
    const html = render('Fact\ue200cite\ue202t0_src_1\ue201.');

    expect(html).toContain('example.com');
    expect(html).not.toContain('citet0_src_1');
  });

  it('renders PUA citation markers even when wrapped in inline code', () => {
    const html = render('Fact `\ue200cite\ue202t0_src_1\ue201`.');

    expect(html).toContain('example.com');
    expect(html).not.toContain('<code');
    expect(html).not.toContain('citet0_src_1');
  });

  it('renders OBJ-normalized PUA citation markers as badges', () => {
    const html = render('Fact\ufffccite\ufffct0_src_1\ufffc.');

    expect(html).toContain('example.com');
    expect(html).not.toContain('citet0_src_1');
    expect(html).not.toContain('\ufffc');
  });

  it('renders multiple source ids in OBJ-normalized markers', () => {
    const html = render('Fact\ufffccite\ufffct0_src_1\ufffct0_src_2\ufffc.');

    expect(html).toContain('example.com');
    expect(html).toContain('+1');
    expect(html).not.toContain('citet0_src_1');
    expect(html).not.toContain('t0_src_2');
  });

  it('renders a fallback chip when an id is missing from a populated map', () => {
    // A cite to an id not in this message's map (e.g. an earlier-turn source):
    // the map is non-empty, so we keep the citation as a muted fallback chip
    // rather than dropping a possibly-real cross-turn reference.
    const html = render('Fact\ufffccite\ufffct0_src_99\ufffc.');

    expect(html).toContain('t0_src_99');
    expect(html).toContain('Citation source metadata missing');
    expect(html).not.toContain('citet0_src_99');
    expect(html).not.toContain('\ufffc');
  });

  it('strips a cite marker entirely when there are no sources at all', () => {
    // Empty/absent map: the marker can't resolve to anything, so it is dropped
    // rather than leaking its raw protocol glyphs or showing an id-only chip.
    const html = renderWithSources('Fact\ue200cite\ue202t0_src_1\ue201 done.', new Map());

    expect(html).toContain('Fact');
    expect(html).toContain('done.');
    expect(html).not.toContain('t0_src_1');
    expect(html).not.toContain('cite');
    expect(html).not.toContain('\ue200');
    expect(html).not.toContain('\ue201');
    expect(html).not.toContain('Citation source metadata missing');
  });

  it('renders loose cite-source text as a badge', () => {
    const html = render('Fact cite-t0_src_1.');

    expect(html).toContain('example.com');
    expect(html).not.toContain('cite-t0_src_1');
  });

  it('hides a partially-streamed PUA marker until it closes', () => {
    // Mid-stream the closing  has not arrived yet; the raw glyphs
    // ( box /  star) must not leak into the rendered text.
    const html = render('Factcitet0');

    expect(html).not.toContain('cite');
    expect(html).not.toContain('');
    expect(html).not.toContain('');
    expect(html).toContain('Fact');
  });

  it('hides a partially-streamed ASCII marker until it closes', () => {
    const html = render('Fact [[cite:t0');

    expect(html).not.toContain('[[cite');
    expect(html).toContain('Fact');
  });

  it('formats citation markers as markdown references for copy', () => {
    const text = formatTextWithCitationReferences(
      'Fact\ue200cite\ue202t0_src_1\ue201. More\ufffccite\ufffct0_src_1\ufffct0_src_2\ufffc.',
      sources,
    );

    expect(text).toContain('Fact [example.com][1].');
    expect(text).toContain('More [example.com][1] [example.org][2].');
    expect(text).toContain('[1]: https://example.com "Example Source"');
    expect(text).toContain('[2]: https://example.org "Second Source"');
    expect(text).not.toContain('\ue200');
    expect(text).not.toContain('\ufffc');
  });

  it('formats loose citation text as markdown references for copy', () => {
    const text = formatTextWithCitationReferences('Fact cite-t0_src_1.', sources);

    expect(text).toContain('Fact [example.com][1].');
    expect(text).toContain('[1]: https://example.com "Example Source"');
    expect(text).not.toContain('cite-t0_src_1');
  });
});

describe('file citation support', () => {
  const fileSources: CitationSourcesMap = new Map([
    [
      't0_src_1',
      {
        id: 't0_src_1',
        type: 'file',
        title: 'README.md',
        url: 'file:///D:/workspace/suzent/README.md',
      },
    ],
  ]);

  it('displays the filename for file:// urls', () => {
    const html = renderWithSources('See citet0_src_1.', fileSources);
    expect(html).toContain('README.md');
  });

  it('renders an extension-based icon for file sources without a favicon', () => {
    const html = renderWithSources('See citet0_src_1.', fileSources);
    // .md maps to 📝 in FILE_EXT_ICONS
    expect(html).toContain('📝');
  });
});
