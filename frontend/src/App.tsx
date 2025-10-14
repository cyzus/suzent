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
  
  const handlePlanRefresh = React.useCallback(() => {
    refresh(currentChatId);
  }, [refresh, currentChatId]);

  // Load plan when chat changes
  React.useEffect(() => {
    console.log('Loading plan for chat:', currentChatId);
    refresh(currentChatId);
  }, [currentChatId, refresh]);

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
