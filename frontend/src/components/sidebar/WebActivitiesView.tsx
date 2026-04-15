import React, { useState, useEffect } from 'react';
import { useI18n } from '../../i18n';
import { BrowserView } from './BrowserView';
import { WebSearchSidebarView } from './WebSearchSidebarView';
import { WebPageReaderView } from './WebPageReaderView';
import { useWebHistory } from '../../hooks/useWebHistory';
import type { Message } from '../../types/api';

interface WebActivitiesViewProps {
  messages: Message[];
  isBrowserStreamActive: boolean;
  onBrowserStreamActive: (isActive: boolean) => void;
  // Allows parent to force an activity context
  forcedContextId?: string | null;
  onClearForcedContext?: () => void;
}

export const WebActivitiesView: React.FC<WebActivitiesViewProps> = ({
  messages,
  isBrowserStreamActive,
  onBrowserStreamActive,
  forcedContextId,
  onClearForcedContext,
}) => {
  const { t } = useI18n();
  const history = useWebHistory(messages);

  const [activeViewId, setActiveViewId] = useState<string>('browser_active');
  const [isTimelineOpen, setIsTimelineOpen] = useState(false);

  // Auto-switch back to browser if it becomes active
  useEffect(() => {
    if (isBrowserStreamActive) {
      setActiveViewId('browser_active');
      setIsTimelineOpen(false);
    }
  }, [isBrowserStreamActive]);

  // Handle external forced navigation
  useEffect(() => {
    if (forcedContextId) {
      setActiveViewId(forcedContextId);
      setIsTimelineOpen(false);
      onClearForcedContext?.();
    }
  }, [forcedContextId, onClearForcedContext]);

  // Ensure active view is valid after history updates (e.g., switching chats)
  useEffect(() => {
    if (activeViewId !== 'browser_active' && !history.find(h => h.id === activeViewId)) {
      setActiveViewId('browser_active');
    }
  }, [history, activeViewId]);

  const [lastHistoryCount, setLastHistoryCount] = useState(history.length);
  useEffect(() => {
    if (history.length > lastHistoryCount) {
      // New item added, switch to it ONLY if browser is not streaming right now
      if (!isBrowserStreamActive) {
         setActiveViewId(history[history.length - 1].id);
         setIsTimelineOpen(false);
      }
    }
    setLastHistoryCount(history.length);
  }, [history, isBrowserStreamActive, lastHistoryCount]);


  const renderContent = () => {
    if (activeViewId === 'browser_active') {
      return <BrowserView onStreamActive={onBrowserStreamActive} />;
    }

    const log = history.find(h => h.id === activeViewId);
    if (!log) {
      // Fallback: silently render BrowserView (it will handle dead states itself)
      return <BrowserView onStreamActive={onBrowserStreamActive} />;
    }

    if (log.type === 'search') {
      return <WebSearchSidebarView output={log.output} />;
    } else if (log.type === 'page') {
       let parsedArgs = { url: '' };
       try { parsedArgs = JSON.parse(log.args || '{}'); } catch {}
       return <WebPageReaderView markdown={log.output} title={log.title} url={parsedArgs.url} />;
    }

    return null;
  };

  const hasHistory = history.length > 0;
  
  const getActiveTitle = () => {
    if (activeViewId === 'browser_active') {
      return isBrowserStreamActive ? '⚡ LIVE BROWSER' : '🌐 IDLE BROWSER';
    }
    const log = history.find(h => h.id === activeViewId);
    return log ? log.title : '🌐 IDLE BROWSER';
  };

  return (
    <div className="flex flex-col h-full bg-white dark:bg-zinc-900 w-full min-h-0 relative">
      {/* Neo-brutalist Header Bar */}
      <div className="shrink-0 flex items-stretch justify-between bg-white dark:bg-zinc-900 border-b-4 border-brutal-black dark:border-black w-full min-w-0 z-30">
        
        {/* Left Side: Current Context Button (Switches to Browser if clicked) */}
        <button 
          onClick={() => { setActiveViewId('browser_active'); setIsTimelineOpen(false); }}
          className={`group flex-1 min-w-0 px-4 py-2 relative text-left transition-all border-r-2 border-brutal-black dark:border-black hover:bg-neutral-100 dark:hover:bg-zinc-800 ${activeViewId === 'browser_active' ? 'bg-brutal-yellow/20 dark:bg-brutal-yellow/10 cursor-default' : 'cursor-pointer'}`}
          disabled={activeViewId === 'browser_active'}
        >
           <div className={`transition-opacity duration-200 ${activeViewId !== 'browser_active' ? 'group-hover:opacity-0' : ''}`}>
             <div className="text-[10px] font-black uppercase text-neutral-500 dark:text-neutral-400 mb-0.5 tracking-wider">
               Current View
             </div>
             <div className="text-xs font-mono font-bold text-brutal-black dark:text-neutral-200 uppercase truncate">
               {getActiveTitle()}
             </div>
           </div>

           {/* Return to browser hover state */}
           {activeViewId !== 'browser_active' && (
             <div className="absolute inset-0 flex items-center gap-2 px-4 opacity-0 group-hover:opacity-100 transition-opacity duration-200 text-brutal-black dark:text-white bg-brutal-yellow dark:bg-brutal-yellow/20">
               <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                 <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
               </svg>
               <span className="text-xs font-black uppercase tracking-widest">Return to Browser</span>
             </div>
           )}
        </button>

        {/* Right Side: Timeline Toggle */}
        <button 
          onClick={() => setIsTimelineOpen(!isTimelineOpen)}
          className={`shrink-0 px-4 flex flex-col justify-center items-center font-mono font-bold transition-all border-l-2 border-brutal-black dark:border-black ${isTimelineOpen ? 'bg-brutal-black text-white hover:bg-neutral-800 dark:bg-white dark:text-black hover:dark:bg-neutral-200' : 'bg-brutal-yellow text-brutal-black hover:bg-yellow-300 dark:bg-brutal-yellow/80 hover:dark:bg-brutal-yellow'}`}
          disabled={!hasHistory}
        >
           <div className="text-[10px] uppercase tracking-widest opacity-80 mb-0.5">History</div>
           <div className="text-sm flex items-center gap-1">
              <span>{history.length}</span>
              <svg className={`w-3.5 h-3.5 transition-transform duration-200 ${isTimelineOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
           </div>
        </button>
      </div>

      {/* Timeline Overlay */}
      {isTimelineOpen && hasHistory && (
        <div className="absolute top-[52px] left-0 right-0 max-h-[65%] bg-white dark:bg-zinc-900 z-20 border-b-4 border-brutal-black dark:border-black shadow-[0_6px_0_0_rgba(0,0,0,1)] dark:shadow-[0_6px_0_0_rgba(0,0,0,0.5)] overflow-y-auto animate-fade-in origin-top scrollbar-thin">
          <div className="p-4 py-6">
            <div className="relative pl-6 ml-2 border-l-2 border-brutal-black dark:border-zinc-700 space-y-5">
              {history.map((item, idx) => {
                const isActive = activeViewId === item.id;
                
                return (
                  <div key={item.id} className="relative group cursor-pointer" onClick={() => { setActiveViewId(item.id); setIsTimelineOpen(false); }}>
                    {/* Node Mark */}
                    <div className={`absolute -left-[31px] top-1.5 w-3.5 h-3.5 transition-all border-2
                      ${isActive ? 'border-brutal-black bg-brutal-black dark:border-white dark:bg-white scale-[1.2]' : 'border-brutal-black bg-white dark:border-zinc-500 dark:bg-zinc-900 group-hover:bg-brutal-yellow dark:group-hover:bg-brutal-yellow dark:group-hover:border-brutal-black'}`} 
                    />
                    
                    {/* Minimalist Event Content */}
                    <div className={`flex flex-col gap-1 -mt-1 p-2 -ml-2 rounded-sm transition-all
                        ${isActive 
                           ? 'bg-neutral-100 dark:bg-zinc-800' 
                           : 'hover:bg-neutral-50 dark:hover:bg-zinc-800/80 group-hover:-translate-y-0.5 group-hover:translate-x-1'}`}
                    >
                      <span className={`text-sm md:text-xs font-bold leading-tight font-mono tracking-tight truncate 
                        ${isActive ? 'text-brutal-blue dark:text-blue-400' : 'text-brutal-black dark:text-neutral-300'}`}>
                        {item.title}
                      </span>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-[10px] font-black uppercase tracking-wider px-1.5 py-0.5 border
                          ${item.type === 'search' ? 'border-neutral-800 dark:border-neutral-400 border-dashed text-neutral-800 dark:text-neutral-400' : 'border-neutral-800 dark:border-neutral-400 border-solid text-neutral-800 dark:text-neutral-400'}`}>
                          {item.type}
                        </span>
                        <span className="text-[10px] font-mono font-bold text-neutral-500 dark:text-zinc-500">
                           {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Dynamic View Container */}
      <div className="flex-1 w-full min-h-0 min-w-0 relative">
        {/* 
          IMPORTANT: BrowserView is always in DOM when activeViewId !== 'browser_active'
          to cleanly maintain the WebSocket connection without disconnections. 
          We use hidden class to suppress it when history is viewed.
        */}
        <div className={`absolute inset-0 w-full h-full ${activeViewId === 'browser_active' ? 'flex flex-col' : 'hidden'}`}>
           <BrowserView onStreamActive={onBrowserStreamActive} />
        </div>
        
        {activeViewId !== 'browser_active' && (
           <div className="absolute inset-0 w-full h-full flex flex-col bg-white dark:bg-zinc-900 z-10 animate-fade-in">
             {renderContent()}
           </div>
        )}
      </div>
    </div>
  );
};
