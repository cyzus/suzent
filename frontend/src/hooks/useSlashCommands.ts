import { useState, useEffect, useMemo } from 'react';
import { getApiBase } from '../lib/api';

export interface SlashCommand {
  name: string;
  aliases: string[];
  description: string;
  usage: string;
  surfaces: string[];
}

let _cache: SlashCommand[] | null = null;

async function fetchCommands(): Promise<SlashCommand[]> {
  if (_cache) return _cache;
  const res = await fetch(`${getApiBase()}/commands?surface=frontend`);
  if (!res.ok) return [];
  _cache = await res.json();
  return _cache!;
}

export function useSlashCommands(input: string) {
  const [commands, setCommands] = useState<SlashCommand[]>([]);

  useEffect(() => {
    fetchCommands().then(setCommands).catch(() => {});
  }, []);

  const suggestions = useMemo(() => {
    if (!input.startsWith('/')) return [];
    // Only suggest while on the first word (no space yet)
    if (input.includes(' ')) return [];
    const query = input.toLowerCase();
    return commands.filter(cmd =>
      cmd.aliases.some(a => a.toLowerCase().startsWith(query))
    );
  }, [input, commands]);

  return suggestions;
}
