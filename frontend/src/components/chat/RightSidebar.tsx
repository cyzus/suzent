import React, { useState, useEffect } from 'react';
import { PlanProgress } from '../PlanProgress';
import { SandboxFiles } from '../sidebar/SandboxFiles';
import { BrowserView } from '../sidebar/BrowserView';
import type { Plan } from '../../types/api';

interface RightSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  plan: Plan | null;
  isPlanExpanded: boolean;
  onTogglePlanExpand: () => void;
  fileToPreview?: { path: string; name: string } | null;
  onMaximizeFile?: (filePath: string, fileName: string) => void;
}

export const RightSidebar: React.FC<RightSidebarProps> = ({
  isOpen,
  onClose,
  plan,
  isPlanExpanded,
  onTogglePlanExpand,
  fileToPreview,
  onMaximizeFile
}) => {
  const [activeTab, setActiveTab] = useState<'plan' | 'files' | 'browser'>('plan');
  const [isFileExpanded, setIsFileExpanded] = useState(false);

  // Auto-switch to files tab when a file is provided
  useEffect(() => {
    if (fileToPreview) {
      setActiveTab('files');
    }
  }, [fileToPreview]);

  return (
    <div
      className={`
        border-l-3 border-brutal-black z-30 flex flex-col shrink-0
        absolute inset-y-0 right-0 lg:static lg:inset-auto h-full
        bg-white transition-all duration-300 ease-in-out
        ${(activeTab === 'files' && isFileExpanded) || activeTab === 'browser' ? 'w-full lg:w-[50vw]' : 'w-full lg:w-96'}
        ${isOpen
          ? 'translate-x-0 lg:mr-0'
          : `translate-x-full lg:translate-x-0 ${(activeTab === 'files' && isFileExpanded) || activeTab === 'browser' ? 'lg:-mr-[50vw]' : 'lg:-mr-96'}`
        }
      `}
    >
      {/* Tab Header */}
      <div className="h-14 bg-white border-b-3 border-brutal-black flex items-center justify-between px-0 shrink-0">
        <div className="flex h-full w-full">
          <button
            onClick={() => setActiveTab('plan')}
            className={`flex-1 px-2 font-brutal font-bold text-sm tracking-wider uppercase h-full border-r-3 border-brutal-black transition-colors ${activeTab === 'plan'
              ? 'bg-brutal-black text-white'
              : 'bg-white hover:bg-neutral-100 text-brutal-black'
              }`}
          >
            PLAN
          </button>
          <button
            onClick={() => setActiveTab('files')}
            className={`flex-1 px-2 font-brutal font-bold text-sm tracking-wider uppercase h-full border-r-3 border-brutal-black transition-colors ${activeTab === 'files'
              ? 'bg-brutal-black text-white'
              : 'bg-white hover:bg-neutral-100 text-brutal-black'
              }`}
          >
            FILES
          </button>
          <button
            onClick={() => setActiveTab('browser')}
            className={`flex-1 px-2 font-brutal font-bold text-sm tracking-wider uppercase h-full transition-colors ${activeTab === 'browser'
              ? 'bg-brutal-black text-white'
              : 'bg-white hover:bg-neutral-100 text-brutal-black'
              }`}
          >
            BROWSER
          </button>
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto bg-neutral-50/50 scrollbar-thin scrollbar-track-neutral-200 scrollbar-thumb-brutal-black flex flex-col">
        {activeTab === 'plan' && (
          <div className="p-4">
            <PlanProgress
              plan={plan}
              isDocked={true}
              onToggleDock={onClose}
              isExpanded={isPlanExpanded}
              onToggleExpand={onTogglePlanExpand}
            />
          </div>
        )}
        {activeTab === 'files' && (
          <div className="flex-1 h-full">
            <SandboxFiles
              onViewModeChange={setIsFileExpanded}
              externalFilePath={fileToPreview?.path ?? null}
              externalFileName={fileToPreview?.name ?? null}
              onMaximize={onMaximizeFile}
            />
          </div>
        )}
        {/* Always render BrowserView to keep WS connection alive, just hide it */}
        <div className={`flex-1 h-full flex flex-col ${activeTab === 'browser' ? 'flex' : 'hidden'}`}>
          <BrowserView />
        </div>
      </div>
    </div>
  );
};
