import React, { useState } from 'react';
import { Sidebar } from './components/sidebar/Sidebar';
import { ChatWindow } from './components/ChatWindow';
import { PlanView } from './components/sidebar/PlanView';
import { ConfigView } from './components/sidebar/ConfigView';
import { ChatList } from './components/ChatList';
import { MemoryView } from './components/memory/MemoryView';
import { ErrorBoundary } from './components/ErrorBoundary';
import { PlanProvider, usePlan } from './hooks/usePlan';
import { ChatProvider, useChatStore } from './hooks/useChatStore.js';

const HeaderTitle: React.FC = () => {
  const { backendConfig } = useChatStore();
  return (
    <div className="flex items-center gap-3">
      <div className="w-3 h-3 bg-brutal-black"></div>
      <h1 className="font-brutal text-3xl text-brutal-black tracking-tighter uppercase leading-none">
        {backendConfig?.title || 'SUZENT'}
      </h1>
      <div className="w-3 h-3 bg-brutal-black"></div>
    </div>
  );
};

const AppInner: React.FC = () => {
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'plan' | 'config'>('chats');
  const [mainView, setMainView] = useState<'chat' | 'memory'>('chat');
  const { plan, plans, currentPlan, snapshotPlan, selectedPlanKey, selectPlan, refresh } = usePlan();
  const { currentChatId } = useChatStore();
  const prevSnapshotRef = React.useRef<{ key?: string; taskCount?: number }>({});
  const chatIdRef = React.useRef<string | null>(null);

  const handlePlanRefresh = React.useCallback(() => {
    refresh(currentChatId);
  }, [refresh, currentChatId]);

  // Load plan when chat changes
  React.useEffect(() => {
    console.log('Loading plan for chat:', currentChatId);
    refresh(currentChatId);
    // Track chat change
    chatIdRef.current = currentChatId;
  }, [currentChatId, refresh]);

  // Auto-switch to plan tab when plan is actually updated (has tasks and changed)
  React.useEffect(() => {
    const snapshotKey = snapshotPlan?.versionKey;
    const snapshotTaskCount = snapshotPlan?.tasks.length || 0;

    const prev = prevSnapshotRef.current;

    console.log('Plan update check:', {
      snapshotKey,
      snapshotTaskCount,
      prevKey: prev.key,
      prevTaskCount: prev.taskCount,
      hasSnapshot: !!snapshotPlan
    });

    // Switch to plan tab whenever we have a snapshot with tasks AND
    // either we didn't have one before OR it changed
    if (snapshotKey && snapshotTaskCount > 0) {
      const hadNoPreviousSnapshot = !prev.key;
      const snapshotChanged = prev.key && (snapshotKey !== prev.key || snapshotTaskCount !== prev.taskCount);

      if (hadNoPreviousSnapshot || snapshotChanged) {
        console.log('Plan created/updated! Switching to plan tab', { hadNoPreviousSnapshot, snapshotChanged });
        setSidebarTab('plan');
      }
    }

    // Update ref for next comparison
    prevSnapshotRef.current = {
      key: snapshotKey,
      taskCount: snapshotTaskCount
    };
  }, [snapshotPlan]);

  return (
    <div className="h-full w-full bg-neutral-50 text-brutal-black font-sans">
      <div className="flex h-full">
        <Sidebar
          activeTab={sidebarTab}
          onTabChange={setSidebarTab}
          chatsContent={<ChatList />}
          planContent={(
            <PlanView
              plan={plan}
              currentPlan={currentPlan}
              snapshotPlan={snapshotPlan}
              plans={plans}
              selectedPlanKey={selectedPlanKey}
              onSelectPlan={selectPlan}
              onRefresh={handlePlanRefresh}
            />
          )}
          configContent={<ConfigView />}
        />
        <div className="flex-1 flex flex-col">
          <header className="border-b-4 border-brutal-black px-6 py-5 flex items-center justify-between bg-brutal-white shadow-[0_4px_0_0_#000000]">
            <HeaderTitle />
            <div className="flex gap-2">
              <button
                onClick={() => setMainView('chat')}
                className={`px-4 py-2 border-2 border-brutal-black font-bold text-xs uppercase transition-all ${
                  mainView === 'chat'
                    ? 'bg-brutal-black text-brutal-white'
                    : 'bg-white hover:bg-neutral-100 active:translate-x-[2px] active:translate-y-[2px] shadow-[2px_2px_0_0_#000000] active:shadow-none'
                }`}
              >
                Chat
              </button>
              <button
                onClick={() => setMainView('memory')}
                className={`px-4 py-2 border-2 border-brutal-black font-bold text-xs uppercase transition-all ${
                  mainView === 'memory'
                    ? 'bg-brutal-black text-brutal-white'
                    : 'bg-white hover:bg-neutral-100 active:translate-x-[2px] active:translate-y-[2px] shadow-[2px_2px_0_0_#000000] active:shadow-none'
                }`}
              >
                Memory
              </button>
            </div>
          </header>
          {mainView === 'chat' ? (
            <div key="chat" className="flex-1 flex flex-col min-h-0 animate-brutal-drop">
              <ChatWindow />
            </div>
          ) : (
            <div key="memory" className="flex-1 flex flex-col min-h-0 animate-brutal-drop">
              <MemoryView />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default function App() {
  return (
    <ErrorBoundary>
      <ChatProvider>
        <PlanProvider>
          <AppInner />
        </PlanProvider>
      </ChatProvider>
    </ErrorBoundary>
  );
}
