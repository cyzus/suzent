import { describe, expect, it } from 'vitest';
import { artifactKind, collectChatArtifacts } from './chatArtifacts';
import type { Message } from '../types/api';

const toolResult = (savedPaths: string[], success = true): string =>
  JSON.stringify({ success, message: 'ok', metadata: { saved_paths: savedPaths } });

const writeResult = (absPath: string, success = true): string =>
  JSON.stringify({ success, message: 'ok', metadata: { abs_path: absPath, file_path: absPath } });

const assistant = (overrides: Partial<Message>): Message => ({
  role: 'assistant',
  content: '',
  ...overrides,
});

const PROJECT = '/home/u/.suzent/sandbox/projects/p1';

describe('collectChatArtifacts', () => {
  it('lists media, sent files and library files, newest first', () => {
    const messages: Message[] = [
      { role: 'user', content: 'draw a cat' },
      assistant({
        parts: [
          {
            type: 'tool',
            toolName: 'generate_image',
            state: 'completed',
            output: toolResult(['/workspace/artifacts/images/cat.png']),
          },
        ],
      }),
      assistant({
        parts: [
          {
            type: 'tool',
            toolName: 'check_video',
            state: 'completed',
            output: toolResult(['/workspace/artifacts/videos/clip.mp4']),
          },
          {
            type: 'tool',
            toolName: 'send_file',
            state: 'completed',
            output: toolResult(['/repo/dist/report.pdf']),
          },
          {
            type: 'tool',
            toolName: 'write_file',
            state: 'completed',
            output: writeResult(`${PROJECT}/artifacts/docs/brief.md`),
          },
        ],
      }),
    ];

    expect(collectChatArtifacts(messages)).toEqual([
      {
        path: `${PROJECT}/artifacts/docs/brief.md`,
        displayPath: 'artifacts/docs/brief.md',
        name: 'brief.md',
        kind: 'file',
        messageIndex: 2,
      },
      {
        path: '/repo/dist/report.pdf',
        displayPath: '/repo/dist/report.pdf',
        name: 'report.pdf',
        kind: 'file',
        messageIndex: 2,
      },
      {
        path: '/workspace/artifacts/videos/clip.mp4',
        displayPath: 'artifacts/videos/clip.mp4',
        name: 'clip.mp4',
        kind: 'video',
        messageIndex: 2,
      },
      {
        path: '/workspace/artifacts/images/cat.png',
        displayPath: 'artifacts/images/cat.png',
        name: 'cat.png',
        kind: 'image',
        messageIndex: 1,
      },
    ]);
  });

  it('ignores working edits outside artifacts/', () => {
    const messages: Message[] = [
      assistant({
        parts: [
          {
            type: 'tool',
            toolName: 'write_file',
            state: 'completed',
            output: writeResult(`${PROJECT}/notes/plan.md`),
          },
          {
            type: 'tool',
            toolName: 'edit_file',
            state: 'completed',
            output: writeResult('/home/u/code/app/src/main.py'),
          },
          {
            type: 'tool',
            toolName: 'write_file',
            state: 'completed',
            output: writeResult('/home/u/code/app/build/artifacts/out.bin'),
          },
          {
            type: 'tool',
            toolName: 'write_file',
            state: 'completed',
            output: writeResult(
              'C:\\Users\\u\\.suzent\\sandbox\\projects\\p1\\artifacts\\report.md'
            ),
          },
        ],
      }),
    ];

    expect(collectChatArtifacts(messages).map((artifact) => artifact.displayPath)).toEqual([
      'artifacts/report.md',
    ]);
  });

  it('keeps files a chat app refused to receive from send_file', () => {
    const messages: Message[] = [
      assistant({
        parts: [
          {
            type: 'tool',
            toolName: 'send_file',
            state: 'completed',
            output: toolResult([`${PROJECT}/artifacts/report.pdf`], false),
          },
        ],
      }),
    ];

    expect(collectChatArtifacts(messages).map((artifact) => artifact.name)).toEqual(['report.pdf']);
  });

  it('skips inputs and failed tool calls', () => {
    const messages: Message[] = [
      assistant({
        parts: [
          {
            type: 'tool',
            toolName: 'analyze_visual',
            state: 'completed',
            output: toolResult(['/workspace/photo.png']),
          },
          {
            type: 'tool',
            toolName: 'generate_image',
            state: 'completed',
            output: toolResult(['/workspace/failed.png'], false),
          },
          {
            type: 'tool',
            toolName: 'edit_image',
            state: 'error',
            output: toolResult(['/workspace/denied.png']),
          },
          {
            type: 'tool',
            toolName: 'write_file',
            state: 'completed',
            output: writeResult(`${PROJECT}/artifacts/failed.txt`, false),
          },
        ],
      }),
    ];

    expect(collectChatArtifacts(messages)).toEqual([]);
  });

  it('keeps one entry per path at its latest turn', () => {
    const planPath = `${PROJECT}/artifacts/plan.md`;
    const otherPath = `${PROJECT}/artifacts/other.md`;
    const messages: Message[] = [
      assistant({
        parts: [
          {
            type: 'tool',
            toolName: 'write_file',
            state: 'completed',
            output: writeResult(planPath),
          },
        ],
      }),
      assistant({
        parts: [
          {
            type: 'tool',
            toolName: 'write_file',
            state: 'completed',
            output: writeResult(otherPath),
          },
        ],
      }),
      assistant({
        parts: [
          {
            type: 'tool',
            toolName: 'edit_file',
            state: 'completed',
            output: writeResult(planPath),
          },
        ],
      }),
    ];

    expect(
      collectChatArtifacts(messages).map((artifact) => [artifact.name, artifact.messageIndex])
    ).toEqual([
      ['plan.md', 2],
      ['other.md', 1],
    ]);
  });
});

describe('artifactKind', () => {
  it('classifies by extension in any case', () => {
    expect(artifactKind('a/B.PNG')).toBe('image');
    expect(artifactKind('speech.mp3')).toBe('audio');
    expect(artifactKind('clip.MOV')).toBe('video');
    expect(artifactKind('report.pdf')).toBe('file');
    expect(artifactKind('Makefile')).toBe('file');
  });
});
