import React, { useState } from 'react';
import { PlanProgress } from '../PlanProgress';
import { SandboxFiles } from '../sidebar/SandboxFiles';
import type { Plan } from '../../types/api';

interface RightSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  plan: Plan | null;
  isPlanExpanded: boolean;
  onTogglePlanExpand: () => void;
}

export const RightSidebar: React.FC<RightSidebarProps> = ({
  isOpen,
  onClose,
  plan,
  isPlanExpanded,
  onTogglePlanExpand
}) => {
  const [activeTab, setActiveTab] = useState<'plan' | 'files'>('plan');
  const [isFileExpanded, setIsFileExpanded] = useState(false);

  return (
    <div
      className={`
        border-l-3 border-brutal-black z-30 flex flex-col shrink-0
        absolute inset-y-0 right-0 lg:static lg:inset-auto h-full
        bg-white transition-all duration-300 ease-in-out
        ${activeTab === 'files' && isFileExpanded ? 'w-full lg:w-[40vw]' : 'w-full lg:w-96'}
        ${isOpen
          ? 'translate-x-0 lg:mr-0'
          : `translate-x-full lg:translate-x-0 ${activeTab === 'files' && isFileExpanded ? 'lg:-mr-[40vw]' : 'lg:-mr-96'}`
        }
      `}
    >
      {/* Tab Header */}
      <div className="h-14 bg-white border-b-3 border-brutal-black flex items-center justify-between px-0 shrink-0">
        <div className="flex h-full">
          <button
            onClick={() => setActiveTab('plan')}
            className={`px-4 font-brutal font-bold text-sm tracking-wider uppercase h-full border-r-3 border-brutal-black transition-colors ${
              activeTab === 'plan'
                ? 'bg-brutal-black text-white'
                : 'bg-white hover:bg-neutral-100 text-brutal-black'
            }`}
          >
            PLAN
          </button>
          <button
            onClick={() => setActiveTab('files')}
            className={`px-4 font-brutal font-bold text-sm tracking-wider uppercase h-full border-r-3 border-brutal-black transition-colors ${
              activeTab === 'files'
                ? 'bg-brutal-black text-white'
                : 'bg-white hover:bg-neutral-100 text-brutal-black'
            }`}
          >
            FILES
          </button>
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto bg-neutral-50/50 scrollbar-thin scrollbar-track-neutral-200 scrollbar-thumb-brutal-black flex flex-col">
        {activeTab === 'plan' ? (
          <div className="p-4">
            <PlanProgress
              plan={plan}
              isDocked={true}
              onToggleDock={onClose}
              isExpanded={isPlanExpanded}
              onToggleExpand={onTogglePlanExpand}
            />
          </div>
        ) : (
          <div className="flex-1 h-full">
            <SandboxFiles onViewModeChange={setIsFileExpanded} />
          </div>
        )}
      </div>
    </div>
  );
};
