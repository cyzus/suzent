import React, { useState } from 'react';
import { Sidebar } from './components/sidebar/Sidebar';
import { ChatWindow } from './components/ChatWindow';
import { PlanView } from './components/sidebar/PlanView';
import { ConfigView } from './components/sidebar/ConfigView';
import { ChatList } from './components/ChatList';
import { ErrorBoundary } from './components/ErrorBoundary';
import { PlanProvider, usePlan } from './hooks/usePlan';
import { ChatProvider, useChatStore } from './hooks/useChatStore.js';

const HeaderTitle: React.FC = () => {
  const { backendConfig } = useChatStore();
  return (
    <h1 className="font-semibold text-lg bg-gradient-to-r from-brand-400 to-brand-600 bg-clip-text text-transparent tracking-tight">
      {backendConfig?.title || 'Suzent'}
    </h1>
  );
};

const AppInner: React.FC = () => {
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'plan' | 'config'>('chats');
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
    <div className="h-full w-full bg-neutral-50 text-neutral-800 font-sans">
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
          <header className="border-b border-neutral-200 px-6 py-3 flex items-center justify-between bg-white/90 backdrop-blur">
            <HeaderTitle />
          </header>
          <ChatWindow />
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
