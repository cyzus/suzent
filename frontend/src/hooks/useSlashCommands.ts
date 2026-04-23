import { useState, useEffect, useMemo } from 'react';
import { getApiBase } from '../lib/api';

export interface SlashCommand {
  name: string;
  aliases: string[];
  description: string;
  usage: string;
  surfaces: string[];
  category: string;
  options?: Record<string, string>;
  isOption?: boolean;
  parentCmd?: string;
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
    
    // Split the input into the command word and arguments
    const parts = input.split(' ');
    const query = parts[0].toLowerCase();
    const hasSpace = input.includes(' ');
    
    let filtered = commands.filter(cmd =>
      cmd.aliases.some(a => a.toLowerCase().startsWith(query))
    );
    
    if (hasSpace) {
      // Find the exactly matching command
      const exactCmd = filtered.find(cmd => 
        cmd.aliases.some(a => a.toLowerCase() === query)
      );
      
      if (exactCmd && exactCmd.options && Object.keys(exactCmd.options).length > 0) {
          // If we have options, and are writing the second word
          const optionQuery = parts.slice(1).join(' ').toLowerCase().trim();
          
          if (parts.length <= 2) {
              // We are exactly on the option typing phase
              const optionKeys = Object.keys(exactCmd.options).filter(k => k.toLowerCase().startsWith(optionQuery));
              
              if (optionKeys.length > 0) {
                  // Map options into synthetic SlashCommands for the UI to consume
                  return optionKeys.map(key => ({
                      name: `${exactCmd.name}-${key}`,
                      aliases: [key],
                      description: exactCmd.options![key],
                      usage: `${exactCmd.aliases[0]} ${key}`, // shows full text
                      surfaces: exactCmd.surfaces,
                      category: exactCmd.category,
                      options: {},
                      isOption: true,
                      parentCmd: exactCmd.aliases[0]
                  }) as SlashCommand).sort((a, b) => a.aliases[0].localeCompare(b.aliases[0]));
              }
          }
      }
      
      // Fallback: passive hint
      filtered = exactCmd ? [exactCmd] : [];
    }
    
    return filtered.sort((a, b) => (a.category || 'tools').localeCompare(b.category || 'tools'));
  }, [input, commands]);

  return suggestions;
}
