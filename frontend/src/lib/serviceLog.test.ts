import { describe, it, expect } from 'vitest';

import { countByLevel, filterServiceLog, formatEntry, parseServiceLog } from './serviceLog';

const DATED = '2026-05-04 13:47:32.481 | INFO     | suzent.server:startup:120 | Ready on 25314';
const UNDATED = '13:47:33 | WARNING  | suzent.sync.service:pull:88 | Remote refused, retrying';

describe('parseServiceLog', () => {
  it('splits a record into its fields', () => {
    const [entry] = parseServiceLog([DATED]);

    expect(entry.time).toBe('2026-05-04 13:47:32.481');
    expect(entry.level).toBe('INFO');
    expect(entry.source).toBe('suzent.server:startup:120');
    expect(entry.message).toBe('Ready on 25314');
  });

  it('reads a line written without the date', () => {
    // What a service manager captured from a terminal-formatted stream holds.
    const [entry] = parseServiceLog([UNDATED]);

    expect(entry.time).toBe('13:47:33');
    expect(entry.level).toBe('WARNING');
  });

  it('strips terminal colour codes left by older versions', () => {
    const coloured = `\x1b[32m13:47:33\x1b[0m | \x1b[1mERROR   \x1b[0m | a:b:1 | \x1b[1mboom\x1b[0m`;

    const [entry] = parseServiceLog([coloured]);

    expect(entry.level).toBe('ERROR');
    expect(entry.message).toBe('boom');
  });

  it('keeps a traceback with the record that announced it', () => {
    const entries = parseServiceLog([
      DATED,
      'Traceback (most recent call last):',
      '  File "server.py", line 12, in start',
      'ValueError: no port',
      UNDATED,
    ]);

    expect(entries).toHaveLength(2);
    expect(entries[0].continuation).toEqual([
      'Traceback (most recent call last):',
      '  File "server.py", line 12, in start',
      'ValueError: no port',
    ]);
    expect(entries[1].level).toBe('WARNING');
  });

  it('leaves unrelated output standing on its own', () => {
    // Output that merely follows a record is not part of it. Folding a run of
    // it into the record above hides it behind a line it has nothing to do
    // with, and it is usually the interesting half of a broken start-up.
    const entries = parseServiceLog([DATED, 'Downloading model weights...', 'done']);

    expect(entries).toHaveLength(3);
    expect(entries[1].message).toBe('Downloading model weights...');
    expect(entries[2].message).toBe('done');
  });

  it('shows a tail that opens mid-traceback rather than dropping it', () => {
    const entries = parseServiceLog(['ValueError: no port', DATED]);

    expect(entries[0].level).toBeNull();
    expect(entries[0].message).toBe('ValueError: no port');
  });

  it('does not mistake a pipe in a message for a field separator', () => {
    const [entry] = parseServiceLog([
      '13:47:33 | INFO     | suzent.tools.base:audit:10 | ran `ps aux | grep suzent`',
    ]);

    expect(entry.source).toBe('suzent.tools.base:audit:10');
    expect(entry.message).toBe('ran `ps aux | grep suzent`');
  });

  it('reads the lines written before logging is configured', () => {
    // Imports log through loguru's default handler, which separates the
    // message with a dash. Those are the first lines of every start-up.
    const [entry] = parseServiceLog([
      '2026-09-19 01:38:59.002 | INFO     | suzent.config.model:load:308 - Loaded overrides',
    ]);

    expect(entry.level).toBe('INFO');
    expect(entry.source).toBe('suzent.config.model:load:308');
    expect(entry.message).toBe('Loaded overrides');
  });

  it('treats an unknown severity word as a plain line', () => {
    const [entry] = parseServiceLog(['12:00:00 | NOTICE   | a:b:1 | hm']);

    expect(entry.level).toBeNull();
  });
});

describe('filterServiceLog', () => {
  const entries = parseServiceLog([
    '12:00:00 | DEBUG    | a:b:1 | polling',
    '12:00:01 | INFO     | a:b:2 | started',
    '12:00:02 | ERROR    | a:b:3 | crashed',
    'Traceback (most recent call last):',
  ]);

  it('hides records below the threshold', () => {
    const kept = filterServiceLog(entries, { minLevel: 'INFO' });

    expect(kept.map((entry) => entry.level)).toEqual(['INFO', 'ERROR']);
  });

  it('keeps unlevelled output whatever the threshold', () => {
    // A crash that bypassed the logger is exactly what a severity filter is
    // reached for, so it must not be what the filter removes.
    const loose = parseServiceLog(['Segmentation fault']);

    expect(filterServiceLog(loose, { minLevel: 'CRITICAL' })).toHaveLength(1);
  });

  it('searches the message, the source and the attached traceback', () => {
    expect(filterServiceLog(entries, { query: 'crash' })).toHaveLength(1);
    expect(filterServiceLog(entries, { query: 'a:b:1' })).toHaveLength(1);
    expect(filterServiceLog(entries, { query: 'traceback' })).toHaveLength(1);
    expect(filterServiceLog(entries, { query: 'CRASHED' })).toHaveLength(1);
  });

  it('combines a threshold with a search', () => {
    expect(filterServiceLog(entries, { minLevel: 'ERROR', query: 'polling' })).toEqual([]);
  });

  it('returns everything when nothing is asked of it', () => {
    expect(filterServiceLog(entries)).toHaveLength(entries.length);
  });
});

describe('countByLevel', () => {
  it('counts records and ignores loose lines', () => {
    const counts = countByLevel(
      parseServiceLog([
        '12:00:00 | INFO     | a:b:1 | one',
        '12:00:01 | INFO     | a:b:2 | two',
        'loose',
        '12:00:02 | ERROR    | a:b:3 | three',
      ])
    );

    expect(counts.INFO).toBe(2);
    expect(counts.ERROR).toBe(1);
    expect(counts.DEBUG).toBe(0);
  });
});

describe('formatEntry', () => {
  it('round-trips a record and its traceback back to text', () => {
    const [entry] = parseServiceLog([
      DATED,
      'Traceback (most recent call last):',
      'ValueError: no port',
    ]);

    expect(formatEntry(entry)).toBe(
      '2026-05-04 13:47:32.481 | INFO | suzent.server:startup:120 | Ready on 25314\n' +
        'Traceback (most recent call last):\nValueError: no port'
    );
  });
});

describe('loguru decorated tracebacks', () => {
  it('keeps every decorated frame with the record that raised', () => {
    // loguru writes markers and blank lines between frames, so a traceback
    // runs until the next record rather than until the next unindented line.
    const entries = parseServiceLog([
      '2026-09-19 01:37:03.456 | ERROR    | uvicorn.error:startup:11 | startup failed',
      'Traceback (most recent call last):',
      '',
      '> File "/app/server.py", line 9, in start',
      '    raise ValueError("no port")',
      '',
      'ValueError: no port',
      '2026-09-19 01:37:04.000 | INFO     | suzent.server:stop:20 | shutting down',
    ]);

    expect(entries).toHaveLength(2);
    expect(entries[0].continuation).toHaveLength(6);
    expect(entries[0].continuation.at(-1)).toBe('ValueError: no port');
    expect(entries[1].message).toBe('shutting down');
  });
});
