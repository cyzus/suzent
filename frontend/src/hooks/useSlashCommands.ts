import { useState, useEffect, useMemo } from 'react';
import { getApiBase } from '../lib/api';
import { fetchSkills } from '../lib/skillsApi';

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

// The last list fetched, shown while a fresh one loads. It is refetched each
// time a slash command is started, so commands the backend gained since the
// page loaded (a restart, a plugin) appear without reloading the window.
let lastCommands: SlashCommand[] = [];

async function fetchCommands(): Promise<SlashCommand[]> {
  const res = await fetch(`${getApiBase()}/commands?surface=frontend`);
  if (!res.ok) throw new Error(`Failed to fetch commands: ${res.statusText}`);
  const cmds: SlashCommand[] = await res.json();
  lastCommands = cmds.sort((a, b) => (a.category || 'tools').localeCompare(b.category || 'tools'));
  return lastCommands;
}

// `/skill` completes from the enabled skills, which depend on the chat's
// repository, so they are fetched per chat rather than cached with the commands.
const SKILL_COMMAND = 'skill';

export function buildSuggestions(
  input: string,
  commands: SlashCommand[],
  skillOptions: Record<string, string>
): SlashCommand[] {
  if (!input.startsWith('/')) return [];

  // Split the input into the command word and arguments
  const parts = input.split(' ');
  const query = parts[0].toLowerCase();
  const hasSpace = input.includes(' ');

  let filtered = commands.filter((cmd) =>
    cmd.aliases.some((a) => a.toLowerCase().startsWith(query))
  );

  if (hasSpace) {
    // Find the exactly matching command
    const exactCmd = filtered.find((cmd) => cmd.aliases.some((a) => a.toLowerCase() === query));

    const options = exactCmd?.name === SKILL_COMMAND ? skillOptions : exactCmd?.options;
    if (exactCmd && options && Object.keys(options).length > 0) {
      // If we have options, and are writing the second word
      const optionQuery = parts.slice(1).join(' ').toLowerCase().trim();

      if (parts.length <= 2) {
        // We are exactly on the option typing phase
        const optionKeys = Object.keys(options).filter((k) =>
          k.toLowerCase().startsWith(optionQuery)
        );

        if (optionKeys.length > 0) {
          // Map options into synthetic SlashCommands for the UI to consume
          return optionKeys
            .map(
              (key) =>
                ({
                  name: `${exactCmd.name}-${key}`,
                  aliases: [key],
                  description: options[key],
                  usage: `${exactCmd.aliases[0]} ${key}`, // shows full text
                  surfaces: exactCmd.surfaces,
                  category: exactCmd.category,
                  options: {},
                  isOption: true,
                  parentCmd: exactCmd.aliases[0],
                }) as SlashCommand
            )
            .sort((a, b) => a.aliases[0].localeCompare(b.aliases[0]));
        }
      }
    }

    // Fallback: passive hint
    filtered = exactCmd ? [exactCmd] : [];
  }

  return filtered;
}

export function useSlashCommands(input: string, chatId?: string | null) {
  const [commands, setCommands] = useState<SlashCommand[]>(lastCommands);
  const typingCommand = input.startsWith('/');
  const [skillOptions, setSkillOptions] = useState<Record<string, string>>({});
  const wantsSkills = /^\/skills? /i.test(input);

  useEffect(() => {
    if (!wantsSkills) return;
    let cancelled = false;
    fetchSkills(chatId)
      .then((skills) => {
        if (cancelled) return;
        setSkillOptions(
          Object.fromEntries(
            skills.filter((s) => s.enabled).map((s) => [s.name, s.description ?? ''])
          )
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [wantsSkills, chatId]);

  useEffect(() => {
    if (!typingCommand) return;
    let cancelled = false;
    fetchCommands()
      .then((cmds) => {
        if (!cancelled) setCommands(cmds);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [typingCommand]);

  return useMemo(
    () => buildSuggestions(input, commands, skillOptions),
    [input, commands, skillOptions]
  );
}
