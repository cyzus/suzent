import { describe, expect, it } from 'vitest';
import { parseSubAgentResult } from './subAgentResult';

// The shapes below are taken from real persisted `agent` tool results.
describe('parseSubAgentResult', () => {
  it('reads the task id and status out of the JSON metadata', () => {
    const output = JSON.stringify({
      success: true,
      message: 'Sub-agent sub_052ecd64 completed.\nTask: …',
      metadata: {
        task_id: 'sub_052ecd64',
        chat_id: 'subagent-sub_052ecd64',
        status: 'completed',
        result_summary: 'found it',
      },
    });
    expect(parseSubAgentResult(output)).toEqual({
      taskId: 'sub_052ecd64',
      status: 'completed',
      resultSummary: 'found it',
      error: undefined,
    });
  });

  it('keeps a background spawn non-terminal instead of calling it completed', () => {
    const output = JSON.stringify({
      success: true,
      message: 'Sub-agent spawned (ID: sub_be2a259b).',
      metadata: { task_id: 'sub_be2a259b', status: 'queued' },
    });
    const parsed = parseSubAgentResult(output);
    expect(parsed.taskId).toBe('sub_be2a259b');
    // 'completed' here would freeze the block as terminal and stop the poll.
    expect(parsed.status).toBe('queued');
  });

  it('recovers the id from the completed wording the old ID-only pattern missed', () => {
    expect(parseSubAgentResult('Sub-agent sub_3cf19d28 completed.\nTask: …').taskId).toBe(
      'sub_3cf19d28'
    );
  });

  it('still recovers the id from the spawned wording', () => {
    expect(parseSubAgentResult('Sub-agent spawned (ID: `sub_6abe74d7`).').taskId).toBe(
      'sub_6abe74d7'
    );
  });

  it('falls back to the prose scan when the payload is not valid JSON', () => {
    // A Python-repr payload: single quotes, so JSON.parse throws.
    const output = "{'success': True, 'message': 'Sub-agent sub_6e227609 completed.'}";
    expect(parseSubAgentResult(output).taskId).toBe('sub_6e227609');
  });

  it('reports nothing for a timed-out call, which records no id at all', () => {
    const output =
      'Tool execution timed out after 60s and was cancelled. The result is unavailable; ' +
      'treat this tool call as failed and decide how to proceed.';
    expect(parseSubAgentResult(output)).toEqual({});
  });

  it('ignores a status the UI does not model', () => {
    const output = JSON.stringify({
      metadata: { task_id: 'sub_abc123', status: 'something_new' },
    });
    expect(parseSubAgentResult(output)).toMatchObject({ taskId: 'sub_abc123', status: undefined });
  });

  it('returns empty for no output', () => {
    expect(parseSubAgentResult(undefined)).toEqual({});
  });
});

describe('parseSubAgentResult — timed-out agent envelope', () => {
  it('keeps a cancelled call non-terminal so the poll still resolves it', () => {
    // What streaming.py synthesizes when the tool timeout cancels an `agent`
    // call whose sub-agent is still running.
    const output = JSON.stringify({
      success: false,
      message: 'Tool execution timed out … The sub-agent sub_abc123 may still be running.',
      metadata: { task_id: 'sub_abc123', status: 'running' },
    });
    expect(parseSubAgentResult(output)).toMatchObject({
      taskId: 'sub_abc123',
      status: 'running',
    });
  });
});

describe('parseSubAgentResult — agent identity', () => {
  it('recovers which model ran and what kind of agent it was', () => {
    // Both have been in the tool result's metadata all along; the transcript
    // block showed a generic status glyph instead.
    const output = JSON.stringify({
      success: true,
      message: 'Sub-agent sub_052ecd64 completed.',
      metadata: {
        task_id: 'sub_052ecd64',
        status: 'completed',
        model_override: 'chatgpt/gpt-5.6-sol',
        subagent_type: 'verify',
      },
    });
    expect(parseSubAgentResult(output)).toMatchObject({
      model: 'chatgpt/gpt-5.6-sol',
      subagentType: 'verify',
    });
  });

  it('leaves identity undefined when the metadata does not carry it', () => {
    const output = JSON.stringify({ metadata: { task_id: 'sub_abc123' } });
    expect(parseSubAgentResult(output)).toMatchObject({
      model: undefined,
      subagentType: undefined,
    });
  });
});

describe('a call that never spawned anything', () => {
  it('reads a rejected spawn as failed, not done', () => {
    // The caller treats any output as success, so without this an `agent` call
    // rejected for a bad subagent_type rendered DONE beside the real ones.
    const info = parseSubAgentResult(
      JSON.stringify({
        success: false,
        message: "Unknown subagent_type 'general'. Available: explore, plan, verify, web, write",
        error_code: 'invalid_argument',
        metadata: {},
      })
    );

    expect(info.status).toBe('failed');
    expect(info.error).toContain("Unknown subagent_type 'general'");
    expect(info.taskId).toBeUndefined();
  });

  it('carries the reason through for an unrecognized tool list', () => {
    const info = parseSubAgentResult(
      JSON.stringify({
        success: false,
        message: 'None of the provided tool names were recognized.',
        metadata: { unrecognized_tools: ['NopeTool'] },
      })
    );

    expect(info.status).toBe('failed');
    expect(info.error).toBe('None of the provided tool names were recognized.');
  });

  it('leaves a timed-out call reporting running, since its child may still be', () => {
    const info = parseSubAgentResult(
      JSON.stringify({
        success: false,
        message: 'Tool execution timed out after 60s.',
        metadata: { task_id: 'sub_abc123', status: 'running' },
      })
    );

    expect(info.status).toBe('running');
    expect(info.taskId).toBe('sub_abc123');
  });

  it('leaves a successful spawn alone', () => {
    const info = parseSubAgentResult(
      JSON.stringify({
        success: true,
        message: 'Sub-agent spawned (ID: sub_abc123).',
        metadata: { task_id: 'sub_abc123', status: 'queued' },
      })
    );

    expect(info.status).toBe('queued');
    expect(info.error).toBeUndefined();
  });
});
