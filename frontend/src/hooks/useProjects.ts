import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { Project } from '../types/api';
import { getApiBase } from '../lib/api';

const DEFAULT_PROJECT_SLUG = 'default';

interface ProjectContextValue {
  projects: Project[];
  loading: boolean;
  /**
   * The project that newly-created chats will be assigned to. Persisted in
   * localStorage so the picker remembers the user's last choice.
   */
  currentProjectId: string | null;
  setCurrentProjectId: (id: string | null) => void;
  refresh: () => Promise<void>;
  createProject: (name: string, slug?: string) => Promise<Project | null>;
  renameProject: (id: string, name: string) => Promise<void>;
  archiveProject: (id: string, archived: boolean) => Promise<void>;
  deleteProject: (id: string) => Promise<{ success: boolean; error?: string }>;
  moveChat: (chatId: string, projectId: string) => Promise<boolean>;
  getProject: (id: string | null | undefined) => Project | undefined;
  getProjectBySlug: (slug: string) => Project | undefined;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

const PROJECT_STORAGE_KEY = 'suzent.currentProjectId';

export const ProjectProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [currentProjectId, setCurrentProjectIdState] = useState<string | null>(() => {
    try {
      return localStorage.getItem(PROJECT_STORAGE_KEY);
    } catch {
      return null;
    }
  });

  const setCurrentProjectId = useCallback((id: string | null) => {
    setCurrentProjectIdState(id);
    try {
      if (id) localStorage.setItem(PROJECT_STORAGE_KEY, id);
      else localStorage.removeItem(PROJECT_STORAGE_KEY);
    } catch {
      // ignore storage errors
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${getApiBase()}/projects`);
      if (!res.ok) {
        setProjects([]);
        return;
      }
      const data: Project[] = await res.json();
      setProjects(data);

      // If the stored currentProjectId doesn't exist anymore, fall back to default
      setCurrentProjectIdState((prev) => {
        if (prev && data.some((p) => p.id === prev)) return prev;
        const fallback = data.find((p) => p.slug === DEFAULT_PROJECT_SLUG) || data[0];
        const next = fallback?.id ?? null;
        try {
          if (next) localStorage.setItem(PROJECT_STORAGE_KEY, next);
          else localStorage.removeItem(PROJECT_STORAGE_KEY);
        } catch {
          // ignore
        }
        return next;
      });
    } catch (e) {
      console.warn('Failed to load projects:', e);
      setProjects([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const createProject = useCallback(async (name: string, slug?: string): Promise<Project | null> => {
    try {
      const res = await fetch(`${getApiBase()}/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, slug }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        console.warn('createProject failed:', err);
        return null;
      }
      const project: Project = await res.json();
      setProjects((prev) => [...prev, project]);
      return project;
    } catch (e) {
      console.warn('createProject error:', e);
      return null;
    }
  }, []);

  const renameProject = useCallback(async (id: string, name: string) => {
    setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, name } : p)));
    try {
      await fetch(`${getApiBase()}/projects/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
    } catch (e) {
      console.warn('renameProject error:', e);
      await refresh();
    }
  }, [refresh]);

  const archiveProject = useCallback(async (id: string, archived: boolean) => {
    setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, archived } : p)));
    try {
      await fetch(`${getApiBase()}/projects/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archived }),
      });
    } catch (e) {
      console.warn('archiveProject error:', e);
      await refresh();
    }
  }, [refresh]);

  const deleteProject = useCallback(async (id: string): Promise<{ success: boolean; error?: string }> => {
    try {
      const res = await fetch(`${getApiBase()}/projects/${id}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        return { success: false, error: err.error || `HTTP ${res.status}` };
      }
      setProjects((prev) => prev.filter((p) => p.id !== id));
      return { success: true };
    } catch (e: any) {
      return { success: false, error: String(e) };
    }
  }, []);

  const moveChat = useCallback(async (chatId: string, projectId: string): Promise<boolean> => {
    try {
      const res = await fetch(`${getApiBase()}/chats/${chatId}/project`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (!res.ok) return false;
      // Bump chat counts optimistically
      setProjects((prev) =>
        prev.map((p) => {
          if (p.id === projectId) return { ...p, chatCount: p.chatCount + 1 };
          return p;
        }),
      );
      return true;
    } catch (e) {
      console.warn('moveChat error:', e);
      return false;
    }
  }, []);

  const getProject = useCallback(
    (id: string | null | undefined) => projects.find((p) => p.id === id),
    [projects],
  );

  const getProjectBySlug = useCallback(
    (slug: string) => projects.find((p) => p.slug === slug),
    [projects],
  );

  const contextValue: ProjectContextValue = useMemo(
    () => ({
      projects,
      loading,
      currentProjectId,
      setCurrentProjectId,
      refresh,
      createProject,
      renameProject,
      archiveProject,
      deleteProject,
      moveChat,
      getProject,
      getProjectBySlug,
    }),
    [
      projects,
      loading,
      currentProjectId,
      setCurrentProjectId,
      refresh,
      createProject,
      renameProject,
      archiveProject,
      deleteProject,
      moveChat,
      getProject,
      getProjectBySlug,
    ],
  );

  return React.createElement(ProjectContext.Provider, { value: contextValue }, children);
};

export function useProjects() {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error('useProjects must be used within ProjectProvider');
  return ctx;
}
