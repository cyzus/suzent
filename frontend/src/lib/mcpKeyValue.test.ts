import { describe, expect, it } from 'vitest';

import { formatKeyValueList, parseKeyValueList } from './mcpKeyValue';

describe('parseKeyValueList', () => {
  it('returns undefined for blank input', () => {
    expect(parseKeyValueList('  ')).toBeUndefined();
  });

  it('parses comma-separated pairs', () => {
    expect(parseKeyValueList('A=1, B=2')).toEqual({ A: '1', B: '2' });
  });

  it('keeps = inside values such as base64 padding', () => {
    expect(parseKeyValueList('Authorization=Basic dXNlcjpwYXNz==')).toEqual({
      Authorization: 'Basic dXNlcjpwYXNz==',
    });
  });

  it('keeps commas that do not start a new pair', () => {
    expect(parseKeyValueList('Accept=text/html, application/json, X-Key=abc')).toEqual({
      Accept: 'text/html, application/json',
      'X-Key': 'abc',
    });
  });

  it('accepts newline-separated pairs', () => {
    expect(parseKeyValueList('A=1\nB=2')).toEqual({ A: '1', B: '2' });
  });

  it('round-trips through formatKeyValueList', () => {
    const values = { Authorization: 'Bearer a=b', 'X-Api-Key': 'k,1' };
    expect(parseKeyValueList(formatKeyValueList(values))).toEqual(values);
  });
});
