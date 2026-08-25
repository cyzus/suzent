import React from 'react';
import { ChatConfig } from '../types/api';

interface Props {
  config: ChatConfig;
  compact?: boolean;
}

export const RuntimeProvenance: React.FC<Props> = ({ config, compact = false }) => {
  const isAcp = config.runtime === 'acp';

  if (compact) {
    if (isAcp) {
      return (
        <div className="border-2 border-black p-1 text-[10px] font-mono uppercase bg-white">
          EXTERNAL RUNTIME
        </div>
      );
    }
    return (
      <div className="border-2 border-black p-1 text-[10px] font-mono uppercase bg-neutral-100">
        SUZENT: {config.model}
      </div>
    );
  }

  return (
    <div className="border-2 border-black p-2 bg-white flex flex-col gap-1 w-fit">
      {isAcp ? (
        <>
          <div className="font-mono text-xs font-bold uppercase bg-black text-white px-1">
            EXTERNAL RUNTIME
          </div>
          <div className="font-mono text-sm">{config.acp_agent_name || config.acp_agent_id}</div>
          <div className="text-[10px] text-neutral-500 uppercase font-mono">VIA ACP</div>
          <div className="text-[10px] font-mono border-t border-black pt-1">
            SUZENT NATIVE MODEL BYPASSED
          </div>
        </>
      ) : (
        <>
          <div className="font-mono text-xs font-bold uppercase border-b border-black">
            SUZENT RUNTIME
          </div>
          <div className="font-mono text-sm">{config.model}</div>
        </>
      )}
    </div>
  );
};
