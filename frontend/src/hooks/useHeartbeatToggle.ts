import { useState } from 'react';
import { useChatCoreStore } from './useChatStore';
import { disableHeartbeat, enableHeartbeat } from '../lib/api';

export function useHeartbeatToggle() {
  const { currentChatId, config, setConfig } = useChatCoreStore();
  const [toggling, setToggling] = useState(false);
  const enabled = !!(currentChatId && config?.heartbeat_enabled);

  const toggle = async (): Promise<void> => {
    if (!currentChatId || toggling) return;
    const next = !enabled;
    setToggling(true);
    setConfig((prev) => ({ ...prev, heartbeat_enabled: next }));
    try {
      if (next) {
        await enableHeartbeat(currentChatId);
      } else {
        await disableHeartbeat(currentChatId);
      }
    } catch {
      setConfig((prev) => ({ ...prev, heartbeat_enabled: !next }));
    } finally {
      setToggling(false);
    }
  };

  return { enabled, toggling, toggle };
}
