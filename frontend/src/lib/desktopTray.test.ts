import { beforeEach, describe, expect, it, vi } from 'vitest';

const core = vi.hoisted(() => ({ invoke: vi.fn(async () => undefined) }));
vi.mock('@tauri-apps/api/core', () => core);

import { publishTrayLanguage } from './desktopTray';

describe('desktop tray language', () => {
  beforeEach(() => {
    core.invoke.mockClear();
  });

  it('sends the app language to the tray menu', async () => {
    await publishTrayLanguage('zh-CN', true);
    expect(core.invoke).toHaveBeenCalledWith('set_tray_language', { language: 'zh-CN' });
  });

  it('does not touch the shell outside the desktop app', async () => {
    await publishTrayLanguage('zh-CN', false);
    expect(core.invoke).not.toHaveBeenCalled();
  });
});
