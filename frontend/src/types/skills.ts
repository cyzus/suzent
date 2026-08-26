export interface Skill {
  id: string;
  name: string;
  enabled: boolean;
  description?: string;
  body?: string;
  hostPath?: string;
  path: string;
  source?: string;
  sourceId?: string;
}
