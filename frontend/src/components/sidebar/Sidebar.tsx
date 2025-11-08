import React from 'react';

interface SidebarProps {
  activeTab: 'chats' | 'plan' | 'config';
  onTabChange: (t: 'chats' | 'plan' | 'config') => void;
  chatsContent: React.ReactNode;
  planContent: React.ReactNode;
  configContent: React.ReactNode;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab, onTabChange, chatsContent, planContent, configContent }) => {
  const [animateContent, setAnimateContent] = React.useState(false);
  const [mountedTabs, setMountedTabs] = React.useState<Set<'chats' | 'plan' | 'config'>>(() => new Set(['chats']));

  React.useEffect(() => {
    setAnimateContent(true);
    const timeout = window.setTimeout(() => setAnimateContent(false), 200);
    return () => window.clearTimeout(timeout);
  }, [activeTab]);

  React.useEffect(() => {
    setMountedTabs(prev => {
      if (prev.has(activeTab)) return prev;
      const next = new Set(prev);
      next.add(activeTab);
      return next;
    });
  }, [activeTab]);

  const getTabLabel = (tab: string) => {
    switch (tab) {
      case 'chats':
        return 'Chats';
      case 'plan':
        return 'Plan';
      case 'config':
        return 'Configuration';
      default:
        return tab;
    }
  };

  return (
    <aside className="w-80 border-r border-brand-200 flex flex-col bg-brand-50">
      <nav className="flex border-b border-brand-200">
        {['chats', 'plan', 'config'].map(tab => {
          const active = activeTab === tab;
          return (
            <button
              key={tab}
              onClick={() => onTabChange(tab as any)}
              className={`flex-1 py-3 text-sm font-medium relative transition-all ${active ? 'text-brand-900' : 'text-brand-600 hover:text-brand-800'}`}
            >
              {getTabLabel(tab)}
              {active && <span className="absolute left-1/2 -translate-x-1/2 -bottom-px h-0.5 w-12 bg-brand-900 rounded-full" />}
            </button>
          );
        })}
      </nav>
      <div
        className={`flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-brand-300 ${
          animateContent ? 'sidebar-content-animate' : ''
        }`}
        style={{ scrollbarGutter: 'stable both-edges' }}
      >
        <div className={activeTab === 'chats' ? '' : 'hidden'} aria-hidden={activeTab !== 'chats'}>
          {mountedTabs.has('chats') ? chatsContent : null}
        </div>
        <div className={`${activeTab === 'plan' ? '' : 'hidden'} p-4 space-y-4`} aria-hidden={activeTab !== 'plan'}>
          {mountedTabs.has('plan') ? planContent : null}
        </div>
        <div className={`${activeTab === 'config' ? '' : 'hidden'} p-4 space-y-4`} aria-hidden={activeTab !== 'config'}>
          {mountedTabs.has('config') ? configContent : null}
        </div>
      </div>
    </aside>
  );
};
