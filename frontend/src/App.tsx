import React, { useState } from 'react';
import { Sidebar } from './components/sidebar/Sidebar';
import { ChatWindow } from './components/ChatWindow';
import { PlanView } from './components/sidebar/PlanView';
import { ConfigView } from './components/sidebar/ConfigView';
import { ChatList } from './components/ChatList';
import { MemoryView } from './components/memory/MemoryView';
import { ErrorBoundary } from './components/ErrorBoundary';
import { StatusBar } from './components/StatusBar';
import { PlanProvider, usePlan } from './hooks/usePlan';
import { ChatProvider, useChatStore } from './hooks/useChatStore.js';

const HeaderTitle: React.FC<{ text?: string }> = ({ text }) => {
  const { backendConfig } = useChatStore();
  return (
    <div className="flex items-center gap-3">
      <div className="w-3 h-3 bg-brutal-black"></div>
      <h1 className="font-brutal text-3xl text-brutal-black tracking-tighter uppercase leading-none">
        {text || backendConfig?.title || 'SUZENT'}
      </h1>
      <div className="w-3 h-3 bg-brutal-black"></div>
    </div>
  );
};

const AppInner: React.FC = () => {
  const [sidebarTab, setSidebarTab] = useState<'chats' | 'plan' | 'config'>('chats');
  const [mainView, setMainView] = useState<'chat' | 'memory'>('chat');
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const { plan, plans, currentPlan, snapshotPlan, selectedPlanKey, selectPlan, refresh } = usePlan();
  const { currentChatId, setViewSwitcher } = useChatStore();
  const prevSnapshotRef = React.useRef<{ key?: string; phaseCount?: number }>({});
  const chatIdRef = React.useRef<string | null>(null);

  const handlePlanRefresh = React.useCallback(() => {
    refresh(currentChatId);
  }, [refresh, currentChatId]);

  // Set view switcher in context so child components can switch views
  React.useEffect(() => {
    setViewSwitcher?.(setMainView);
  }, [setViewSwitcher, setMainView]);

  // Load plan when chat changes
  React.useEffect(() => {
    console.log('Loading plan for chat:', currentChatId);
    refresh(currentChatId);
    // Track chat change
    chatIdRef.current = currentChatId;
    // Close sidebar on mobile when chat changes (user selected a chat)
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  }, [currentChatId, refresh]);

  // Auto-switch to plan tab when plan is actually updated (has tasks and changed)
  React.useEffect(() => {
    const snapshotKey = snapshotPlan?.versionKey;
    const snapshotPhaseCount = snapshotPlan?.phases.length || 0;

    const prev = prevSnapshotRef.current;

    console.log('Plan update check:', {
      snapshotKey,
      snapshotPhaseCount,
      prevKey: prev.key,
      prevPhaseCount: prev.phaseCount,
      hasSnapshot: !!snapshotPlan
    });

    // Switch to plan tab whenever we have a snapshot with phases AND
    // either we didn't have one before OR it changed
    if (snapshotKey && snapshotPhaseCount > 0) {
      const hadNoPreviousSnapshot = !prev.key;
      const snapshotChanged = prev.key && (snapshotKey !== prev.key || snapshotPhaseCount !== prev.phaseCount);

      if (hadNoPreviousSnapshot || snapshotChanged) {
        console.log('Plan created/updated! Switching to plan tab', { hadNoPreviousSnapshot, snapshotChanged });
        setSidebarTab('plan');
      }
    }

    // Update ref for next comparison
    prevSnapshotRef.current = {
      key: snapshotKey,
      phaseCount: snapshotPhaseCount
    };
  }, [snapshotPlan]);

  return (
    <div className="h-full w-full bg-neutral-50 text-brutal-black font-sans">
      <div className="flex h-full relative">
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
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
        />
        <div className="flex-1 flex flex-col overflow-hidden w-full">
          <header className="border-b-3 border-brutal-black px-4 md:px-6 py-3 md:py-5 flex items-center justify-between bg-brutal-white flex-shrink-0 h-16 md:h-auto">
            <div className="flex items-center gap-2 md:gap-0">
              <button
                onClick={() => setIsSidebarOpen(true)}
                className="md:hidden p-2 -ml-2 mr-1 hover:bg-neutral-100 active:bg-neutral-200 transition-colors"
                aria-label="Open Menu"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="square" strokeLinejoin="miter" d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
              {mainView === 'chat' ? <HeaderTitle /> : <HeaderTitle text="MEMORY SYSTEM" />}
            </div>
            {/* Neo-brutalist physical toggle switch */}
            <div className="relative flex items-center gap-3">
              <span className={`text-xs font-bold uppercase transition-colors ${mainView === 'chat' ? 'text-brutal-black' : 'text-neutral-400'}`}>
                Chat
              </span>
              <button
                onClick={() => setMainView(mainView === 'chat' ? 'memory' : 'chat')}
                className="relative w-20 h-10 bg-neutral-200 border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] active:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:translate-x-[2px] active:translate-y-[2px] transition-all duration-200"
                aria-label={`Switch to ${mainView === 'chat' ? 'memory' : 'chat'} view`}
              >
                {/* Switch track grooves for physical feel */}
                <div className="absolute inset-1 flex gap-0.5">
                  <div className="flex-1 border-l-2 border-brutal-black/20"></div>
                  <div className="flex-1 border-l-2 border-brutal-black/20"></div>
                  <div className="flex-1 border-l-2 border-brutal-black/20"></div>
                </div>
                {/* Toggle knob */}
                <div
                  className={`absolute top-1 h-6 w-9 bg-brutal-black border-2 border-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,0.3)] transition-all duration-300 ease-out ${mainView === 'chat'
                      ? 'left-1'
                      : 'left-[calc(100%-2.375rem)]'
                    }`}
                >
                  {/* Knob grip lines */}
                  <div className="absolute inset-0 flex items-center justify-center gap-0.5">
                    <div className="w-0.5 h-3 bg-white/40"></div>
                    <div className="w-0.5 h-3 bg-white/40"></div>
                    <div className="w-0.5 h-3 bg-white/40"></div>
                  </div>
                </div>
              </button>
              <span className={`text-xs font-bold uppercase transition-colors ${mainView === 'memory' ? 'text-brutal-black' : 'text-neutral-400'}`}>
                Memory
              </span>
            </div>
          </header>

          {/* System Status Line */}
          <StatusBar />

          {mainView === 'chat' ? (
            <div key="chat" className="flex-1 flex flex-col min-h-0 animate-view-fade">
              <ChatWindow />
            </div>
          ) : (
            <div key="memory" className="flex-1 flex flex-col min-h-0 animate-view-fade">
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
