import { describe, expect, it } from 'vitest';
import { buildSuggestions, type SlashCommand } from './useSlashCommands';

const command = (name: string, options: Record<string, string> = {}): SlashCommand => ({
  name,
  aliases: [`/${name}`],
  description: name,
  usage: `/${name}`,
  surfaces: ['all'],
  category: 'tools',
  options,
});

const commands = [
  command('skill', { '<name>': 'static placeholder' }),
  command('model', { ls: 'List models' }),
];
const skills = { writer: 'Writes prose', painter: 'Paints pictures' };

describe('buildSuggestions', () => {
  it('offers the /skill command while its name is typed', () => {
    expect(buildSuggestions('/sk', commands, skills).map((c) => c.name)).toEqual(['skill']);
  });

  it('completes skill names after /skill, not its static options', () => {
    const suggestions = buildSuggestions('/skill ', commands, skills);
    expect(suggestions.map((c) => c.aliases[0])).toEqual(['painter', 'writer']);
    expect(suggestions.every((c) => c.isOption && c.parentCmd === '/skill')).toBe(true);
  });

  it('filters skill names by the typed prefix', () => {
    const suggestions = buildSuggestions('/skill wr', commands, skills);
    expect(suggestions.map((c) => c.aliases[0])).toEqual(['writer']);
    expect(suggestions[0].description).toBe('Writes prose');
  });

  it('falls back to a passive hint once the task is being typed', () => {
    const suggestions = buildSuggestions('/skill writer draft a note', commands, skills);
    expect(suggestions.map((c) => c.name)).toEqual(['skill']);
    expect(suggestions[0].isOption).toBeUndefined();
  });

  it('keeps static options for other commands', () => {
    expect(buildSuggestions('/model ', commands, skills).map((c) => c.aliases[0])).toEqual(['ls']);
  });
});
