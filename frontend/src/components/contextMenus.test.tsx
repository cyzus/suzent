import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.stubGlobal('document', {
  fullscreenElement: null,
  body: {},
  addEventListener() {},
  removeEventListener() {},
});
import { ProjectRowMenu } from './ProjectRowMenu';
import { FileTreeContextMenu } from './sidebar/FileTreeContextMenu';
import { HeartbeatRowMenu, ScheduledTaskMenu } from './sidebar/AutomationRowMenu';
import { MessageActionMenu } from './chat/MessageActionMenu';

vi.mock('../i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));
vi.mock('react-dom', async () => {
  const actual = await vi.importActual<typeof import('react-dom')>('react-dom');
  return { ...actual, createPortal: (node: React.ReactNode) => node };
});

const anchor = { x: 12, y: 16 };

describe('context menus', () => {
  it('offers a new chat on every project, including ones that cannot be renamed', () => {
    const system = renderToStaticMarkup(
      <ProjectRowMenu
        anchor={anchor}
        onNewChat={() => undefined}
        onSettings={() => undefined}
        onClose={() => undefined}
      />
    );
    expect(system).toContain('chatList.newChat');
    expect(system).toContain('chatList.menu.settings');
    expect(system).not.toContain('chatList.menu.rename');
    expect(system).not.toContain('chatList.menu.delete');
  });

  it('downloads a browser file and uploads into a folder without offering both at once', () => {
    const file = renderToStaticMarkup(
      <FileTreeContextMenu
        anchor={anchor}
        isDir={false}
        canDelete
        onOpen={() => undefined}
        onReveal={() => undefined}
        onCopyPath={() => undefined}
        onDownload={() => undefined}
        onDelete={() => undefined}
        onClose={() => undefined}
      />
    );
    const folder = renderToStaticMarkup(
      <FileTreeContextMenu
        anchor={anchor}
        isDir
        canDelete={false}
        onOpen={() => undefined}
        onReveal={() => undefined}
        onCopyPath={() => undefined}
        onUpload={() => undefined}
        onDelete={() => undefined}
        onClose={() => undefined}
      />
    );
    expect(file).toContain('sandbox.contextMenu.download');
    expect(file).not.toContain('sandbox.contextMenu.uploadHere');
    expect(folder).toContain('sandbox.contextMenu.uploadHere');
    expect(folder).not.toContain('sandbox.contextMenu.download');
    expect(folder).not.toContain('sandbox.contextMenu.delete');
  });

  it('pauses a scheduled task and disables run now while it is running', () => {
    const html = renderToStaticMarkup(
      <ScheduledTaskMenu
        anchor={anchor}
        active
        runDisabled
        onToggleActive={() => undefined}
        onRunNow={() => undefined}
        onRename={() => undefined}
        onDelete={() => undefined}
        onClose={() => undefined}
      />
    );
    expect(html).toContain('chatList.automation.pause');
    expect(html).toContain('disabled=""');
    expect(html).toContain('chatList.menu.delete');
  });

  it('offers heartbeat run and disable without a delete action', () => {
    const html = renderToStaticMarkup(
      <HeartbeatRowMenu
        anchor={anchor}
        runDisabled={false}
        onOpen={() => undefined}
        onDisable={() => undefined}
        onRunNow={() => undefined}
        onClose={() => undefined}
      />
    );
    expect(html).toContain('chatList.automation.runHeartbeat');
    expect(html).toContain('chatList.automation.disableHeartbeat');
    expect(html).not.toContain('chatList.menu.delete');
  });

  it('lists only the message actions it was given', () => {
    const html = renderToStaticMarkup(
      <MessageActionMenu
        anchor={anchor}
        actions={[
          { key: 'copy', label: 'chatMessage.copy', onSelect: () => undefined },
          { key: 'fork', label: 'conversationFork.button', onSelect: () => undefined },
        ]}
        onClose={() => undefined}
      />
    );
    expect(html).toContain('chatMessage.copy');
    expect(html).toContain('conversationFork.button');
    expect(html).not.toContain('chatMessage.edit');
  });
});
