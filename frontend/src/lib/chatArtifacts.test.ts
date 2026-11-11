import { describe, expect, it } from 'vitest';
import { artifactKind, collectChatArtifacts } from './chatArtifacts';
import type { Message } from '../types/api';

const toolResult = (savedPaths: string[], success = true): string =>
  JSON.stringify({ success, message: 'ok', metadata: { saved_paths: savedPaths } });

const assistant = (overrides: Partial<Message>): Message => ({
  role: 'assistant',
  content: '',
  ...overrides,
});

describe('collectChatArtifacts', () => {
  it('lists generated media and written files, newest first', () => {
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
        ],
        file_changes: [
          {
            path: '/home/u/.suzent/sandbox/projects/p1/notes/report.md',
            diff: '--- /dev/null\n+++ b/notes/report.md\n@@ -0,0 +1 @@\n+hi',
            additions: 1,
            deletions: 0,
          },
        ],
      }),
    ];

    expect(collectChatArtifacts(messages)).toEqual([
      {
        path: '/home/u/.suzent/sandbox/projects/p1/notes/report.md',
        displayPath: 'notes/report.md',
        name: 'report.md',
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

  it('skips inputs, failures, undone turns and deleted files', () => {
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
        ],
        file_changes: [{ path: '/workspace/a.txt', diff: '+x', additions: 1, deletions: 0 }],
      }),
      assistant({
        file_changes: [
          {
            path: '/workspace/a.txt',
            diff: '--- a/a.txt\n+++ b/a.txt\n@@ -1 +0,0 @@\n-x',
            additions: 0,
            deletions: 1,
            after_exists: false,
          },
        ],
      }),
      assistant({
        file_changes_undone: true,
        file_changes: [{ path: '/workspace/b.txt', diff: '+y', additions: 1, deletions: 0 }],
      }),
    ];

    expect(collectChatArtifacts(messages)).toEqual([]);
  });

  it('keeps one entry per path at its latest turn', () => {
    const change = { path: '/workspace/plan.md', diff: '+a', additions: 1, deletions: 0 };
    const messages: Message[] = [
      assistant({ file_changes: [change] }),
      assistant({
        file_changes: [{ path: '/workspace/other.md', diff: '+b', additions: 1, deletions: 0 }],
      }),
      assistant({ file_changes: [change] }),
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
