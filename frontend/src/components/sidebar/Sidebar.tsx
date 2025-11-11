import React from 'react';

interface SidebarProps {
  activeTab: 'chats' | 'plan' | 'config';
  onTabChange: (t: 'chats' | 'plan' | 'config') => void;
  chatsContent: React.ReactNode;
  planContent: React.ReactNode;
  configContent: React.ReactNode;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  chatsContent,
  planContent,
  configContent
}) => {
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
        return 'Settings';
      default:
        return tab;
    }
  };

  return (
    <aside className="w-80 border-r-4 border-brutal-black flex flex-col bg-neutral-100">
      <nav className="flex border-b-3 border-brutal-black">
        {['chats', 'plan', 'config'].map(tab => {
          const active = activeTab === tab;
          return (
            <button
              key={tab}
              onClick={() => onTabChange(tab as any)}
              className={`flex-1 py-3 text-xs font-bold uppercase relative active:animate-brutal-shake ${active ? 'bg-brutal-black text-brutal-white' : 'bg-neutral-100 text-brutal-black hover:bg-neutral-200 border-r-3 border-brutal-black last:border-r-0'}`}
            >
              {getTabLabel(tab)}
            </button>
          );
        })}
      </nav>
      <div
        className={`flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-brand-300 ${
          animateContent ? 'sidebar-content-animate' : ''
        }`}
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
