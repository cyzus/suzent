import { describe, expect, it } from 'vitest';
import { parseSubAgentArgs } from './SubAgentCallBlock';

describe('parseSubAgentArgs', () => {
  it('returns the same object for the same args string', () => {
    // The card is memoized, so identity is what stops every delegated task in a
    // long turn from re-rendering on each streamed token.
    const args = JSON.stringify({ description: 'Check the tests', tools_allowed: ['Bash'] });
    const first = parseSubAgentArgs(args);
    const second = parseSubAgentArgs(args);
    expect(second).toBe(first);
    expect(second.toolsAllowed).toBe(first.toolsAllowed);
  });

  it('reads the description and tool list', () => {
    const parsed = parseSubAgentArgs(
      '{"description":"Audit deps","tools_allowed":["Read","Grep"]}'
    );
    expect(parsed.description).toBe('Audit deps');
    expect(parsed.toolsAllowed).toEqual(['Read', 'Grep']);
  });

  it('survives args that are still streaming in', () => {
    expect(parseSubAgentArgs('{"description":"half a jso')).toEqual({});
    expect(parseSubAgentArgs(undefined)).toEqual({});
    expect(parseSubAgentArgs('[1,2]')).toEqual({});
  });

  it('ignores fields of the wrong shape', () => {
    const parsed = parseSubAgentArgs('{"description":42,"tools_allowed":"Bash"}');
    expect(parsed.description).toBeUndefined();
    expect(parsed.toolsAllowed).toBeUndefined();
  });
});

describe('run_in_background', () => {
  it('defaults to background when the arg is absent', () => {
    expect(parseSubAgentArgs('{"description":"x"}').runInBackground).toBe(true);
  });

  it('reads an explicit blocking call', () => {
    expect(parseSubAgentArgs('{"run_in_background":false}').runInBackground).toBe(false);
  });

  it('ignores a non-boolean value', () => {
    expect(parseSubAgentArgs('{"run_in_background":"no"}').runInBackground).toBe(true);
  });
});
