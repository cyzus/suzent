import { useCallback, useEffect, useRef, useState } from 'react';
import { nodeClient } from '../services/nodeClient';
import { NodeStatus } from '../types';

export function useNodeClient(serverUrl: string, deviceName: string, enabled: boolean) {
  const [status, setStatus] = useState<NodeStatus>('disconnected');
  const [nodeId, setNodeId] = useState<string | null>(null);
  const prevUrl = useRef('');

  useEffect(() => {
    nodeClient.onStatusChange = setStatus;
    nodeClient.onNodeId = setNodeId;
    return () => {
      nodeClient.onStatusChange = () => {};
      nodeClient.onNodeId = () => {};
    };
  }, []);

  useEffect(() => {
    if (!enabled || !serverUrl) {
      nodeClient.disconnect();
      return;
    }

    if (serverUrl !== prevUrl.current) {
      prevUrl.current = serverUrl;
      nodeClient.disconnect();
    }

    nodeClient.connect(serverUrl, deviceName);
    return () => {
      nodeClient.disconnect();
    };
  }, [serverUrl, deviceName, enabled]);

  const reconnect = useCallback(() => {
    nodeClient.disconnect();
    setTimeout(() => nodeClient.connect(serverUrl, deviceName), 300);
  }, [serverUrl, deviceName]);

  return { status, nodeId, reconnect };
}
