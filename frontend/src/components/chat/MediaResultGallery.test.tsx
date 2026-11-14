import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import {
  getImageResultPaths,
  getPlayableResults,
  getSentPaths,
  hasMediaResults,
  hasVisualMediaResults,
} from './ImageResultGallery';
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
  it('shows a saved media path only once across repeated status results', () => {
    const media = getPlayableResults([
      call('check_video', { saved_paths: ['/video.mp4'] }),
      call('check_video', { saved_paths: ['/video.mp4'] }),
    ]);

    expect(media).toHaveLength(1);
    expect(media[0].path).toBe('/video.mp4');
  });
  it('keeps send_file results out of the inline gallery so they gather under the reply', () => {
    const sent = call('send_file', {
      saved_paths: ['/w/chart.PNG', '/w/clip.mp4', '/w/report.pdf', '/w/report.pdf'],
    });
    expect(getImageResultPaths([sent])).toEqual([]);
    expect(getPlayableResults([sent])).toEqual([]);
    expect(hasVisualMediaResults([sent])).toBe(false);
    expect(hasMediaResults([sent])).toBe(false);
    expect(getSentPaths([sent])).toEqual(['/w/chart.PNG', '/w/clip.mp4', '/w/report.pdf']);
    expect(getSentPaths([call('send_file', { saved_paths: ['/w/a.zip'] }, false)])).toEqual([
      '/w/a.zip',
    ]);
    expect(getSentPaths([call('send_file', {}, false)])).toEqual([]);
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
