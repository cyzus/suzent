import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { getPlayableResults, hasMediaResults, hasVisualMediaResults } from './ImageResultGallery';
import { SpeechPlayer } from './SpeechPlayer';
import { I18nProvider } from '../../i18n';

const call = (toolName: string, metadata: Record<string, unknown>, success = true) => ({
  toolName,
  output: JSON.stringify({ success, metadata }),
});

describe('media results', () => {
  it('keeps pending/failed video in the rail and exposes only completed artifacts', () => {
    expect(hasMediaResults([call('generate_video', { job_id: 'job', status: 'queued' })])).toBe(
      false
    );
    expect(hasMediaResults([call('check_video', { status: 'in_progress', saved_paths: [] })])).toBe(
      false
    );
    expect(hasMediaResults([call('check_video', { saved_paths: ['/video.mp4'] }, false)])).toBe(
      false
    );
    expect(getPlayableResults([call('check_video', { saved_paths: ['/video.mp4'] })])[0].kind).toBe(
      'video'
    );
  });
  it('surfaces both system speech and saved API audio in order', () => {
    const media = getPlayableResults([
      call('speak', { engine: 'system', text: 'hello' }),
      call('speak', { engine: 'api', saved_paths: ['/voice.wav'] }),
    ]);
    expect(media.map((item) => item.kind)).toEqual(['system', 'audio']);
    expect(hasMediaResults([call('speak', { engine: 'system', text: 'hello' })])).toBe(true);
    expect(hasVisualMediaResults([call('speak', { engine: 'system', text: 'hello' })])).toBe(false);
    expect(hasVisualMediaResults([call('check_video', { saved_paths: ['/video.mp4'] })])).toBe(
      true
    );
  });
  it('renders an explicit playback control and unavailable-device hint without autoplay', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <SpeechPlayer metadata={{ text: 'hello', engine: 'system' }} />
      </I18nProvider>
    );
    expect(html).toContain('Play');
    expect(html).toContain('No local voices');
    expect(html).not.toContain('autoplay');
  });
});
