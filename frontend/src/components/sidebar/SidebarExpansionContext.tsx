import { createContext, useContext } from 'react';

interface SidebarExpansion {
  expanded: boolean;
  toggle: () => void;
}

export const SidebarExpansionContext = createContext<SidebarExpansion | null>(null);
export const useSidebarExpansion = (): SidebarExpansion | null =>
  useContext(SidebarExpansionContext);
