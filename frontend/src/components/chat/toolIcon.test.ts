import {
  ArrowDownOnSquareIcon,
  BoltIcon,
  CalendarDaysIcon,
  ChatBubbleLeftRightIcon,
  ClipboardDocumentCheckIcon,
  ClipboardDocumentListIcon,
  ClockIcon,
  CommandLineIcon,
  CpuChipIcon,
  CursorArrowRaysIcon,
  DocumentPlusIcon,
  DocumentTextIcon,
  EyeIcon,
  FilmIcon,
  FlagIcon,
  FolderOpenIcon,
  GlobeAltIcon,
  MagnifyingGlassIcon,
  NoSymbolIcon,
  PaintBrushIcon,
  PaperAirplaneIcon,
  PencilSquareIcon,
  PhotoIcon,
  PlayIcon,
  QuestionMarkCircleIcon,
  SignalIcon,
  SpeakerWaveIcon,
  Squares2X2Icon,
  StopIcon,
  UserGroupIcon,
  WrenchScrewdriverIcon,
} from '@heroicons/react/24/outline';
import { describe, expect, it } from 'vitest';

import {
  pickToolAnimationKind,
  pickToolIcon,
  pickToolRunningSurfaceClass,
} from './toolGroupIcon';
import { getToolIcon, getToolIconClassName } from './toolIcon';

describe('tool icon helpers', () => {
  it('chooses the pending icon before tool name heuristics', () => {
    expect(getToolIcon('web_search', 'pending')).toBe('⏳');
  });

  it('maps tool names to the shared icon set', () => {
    expect(getToolIcon('web_search')).toBe('🔍');
    expect(getToolIcon('read_file')).toBe('📁');
  });

  it('gives delegation its own mark instead of the generic wrench', () => {
    expect(getToolIcon('agent')).toBe('🤖');
    expect(getToolIcon('subagent')).toBe('🤖');
  });

  it('reads a delegation as delegation even when its name mentions the web', () => {
    // Checked before the substring heuristics: a "web_agent" is an agent, not
    // a search box.
    expect(getToolIcon('web_agent')).toBe('🤖');
  });

  it('still falls back to the wrench for anything unrecognised', () => {
    expect(getToolIcon('some_unknown_tool')).toBe('🔧');
  });

  it('keeps the icon layout class consistent between collapsed and expanded states', () => {
    expect(getToolIconClassName(false, false)).toContain('tool-group-icon');
    expect(getToolIconClassName(true, false)).toContain('animate-pulse');
    expect(getToolIconClassName(true, true)).not.toContain('animate-pulse');
  });

  it('can force grouped icons into monochrome mode', () => {
    expect(getToolIconClassName(false, false, true)).toContain('tool-group-icon--mono');
    expect(getToolIconClassName(false, false, true)).not.toContain('animate-pulse');
  });
});

describe('ToolGroupIcon semantic icon & animation mapping', () => {
  it('prioritizes pending and denied approval states', () => {
    expect(pickToolIcon('run_command', 'pending')).toBe(ClockIcon);
    expect(pickToolIcon('run_command', 'denied')).toBe(NoSymbolIcon);
    expect(pickToolAnimationKind('run_command', 'pending', false, false)).toBe('pending');
    expect(pickToolAnimationKind('run_command', 'denied', true, false)).toBe('none');
  });

  it('distinguishes file read, write, edit, glob, and grep tools', () => {
    expect(pickToolIcon('read_file')).toBe(DocumentTextIcon);
    expect(pickToolIcon('Read')).toBe(DocumentTextIcon);
    expect(pickToolIcon('write_file')).toBe(DocumentPlusIcon);
    expect(pickToolIcon('edit_file')).toBe(PencilSquareIcon);
    expect(pickToolIcon('glob_search')).toBe(FolderOpenIcon);
    expect(pickToolIcon('grep_search')).toBe(MagnifyingGlassIcon);
  });

  it('maps shell and background process tools instead of falling back to wrench', () => {
    expect(pickToolIcon('run_command')).toBe(CommandLineIcon);
    expect(pickToolIcon('RunCommandTool')).toBe(CommandLineIcon);
    expect(pickToolIcon('start_command')).toBe(PlayIcon);
    expect(pickToolIcon('check_command')).toBe(SignalIcon);
    expect(pickToolIcon('stop_command')).toBe(StopIcon);
  });

  it('separates web search, page fetch, browser action, memory search, and session search', () => {
    expect(pickToolIcon('web_search')).toBe(GlobeAltIcon);
    expect(pickToolIcon('webpage_fetch')).toBe(ArrowDownOnSquareIcon);
    expect(pickToolIcon('browser_action')).toBe(CursorArrowRaysIcon);
    expect(pickToolIcon('memory_search')).toBe(CpuChipIcon);
    expect(pickToolIcon('session_search')).toBe(ChatBubbleLeftRightIcon);
  });

  it('maps goals, tasks, scheduling, skills, and multimodal tools to dedicated icons', () => {
    expect(pickToolIcon('manage_goal')).toBe(FlagIcon);
    expect(pickToolIcon('create_tasks')).toBe(ClipboardDocumentListIcon);
    expect(pickToolIcon('update_task')).toBe(ClipboardDocumentCheckIcon);
    expect(pickToolIcon('list_tasks')).toBe(ClipboardDocumentListIcon);
    expect(pickToolIcon('schedule_cron')).toBe(CalendarDaysIcon);
    expect(pickToolIcon('skill_execute')).toBe(BoltIcon);
    expect(pickToolIcon('render_ui')).toBe(Squares2X2Icon);
    expect(pickToolIcon('ask_question')).toBe(QuestionMarkCircleIcon);
    expect(pickToolIcon('generate_image')).toBe(PhotoIcon);
    expect(pickToolIcon('edit_image')).toBe(PaintBrushIcon);
    expect(pickToolIcon('analyze_image')).toBe(EyeIcon);
    expect(pickToolIcon('generate_video')).toBe(FilmIcon);
    expect(pickToolIcon('speak')).toBe(SpeakerWaveIcon);
    expect(pickToolIcon('social_message')).toBe(PaperAirplaneIcon);
    expect(pickToolIcon('agent')).toBe(UserGroupIcon);
    expect(pickToolIcon('some_unknown_tool')).toBe(WrenchScrewdriverIcon);
  });

  it('activates tool-specific micro-mechanical animations only while streaming without output', () => {
    expect(pickToolAnimationKind('run_command', undefined, false, false)).toBe('none');
    expect(pickToolAnimationKind('run_command', undefined, true, true)).toBe('none');
    expect(pickToolAnimationKind('run_command', undefined, true, false)).toBe('terminal');
    expect(pickToolAnimationKind('read_file', undefined, true, false)).toBe('scan');
    expect(pickToolAnimationKind('edit_file', undefined, true, false)).toBe('typewriter');
    expect(pickToolAnimationKind('grep_search', undefined, true, false)).toBe('radar');
    expect(pickToolAnimationKind('check_command', undefined, true, false)).toBe('signal');
    expect(pickToolAnimationKind('memory_search', undefined, true, false)).toBe('memory');
    expect(pickToolAnimationKind('skill_execute', undefined, true, false)).toBe('snap');
    expect(pickToolAnimationKind('browser_action', undefined, true, false)).toBe('cursor');
  });

  it('assigns semantic running surface backgrounds by tool physical nature', () => {
    // 1. Compute / Shell / Delegation -> 45-deg hazard stripes
    expect(pickToolRunningSurfaceClass('run_command')).toBe('brutal-running-mono');
    expect(pickToolRunningSurfaceClass('start_command')).toBe('brutal-running-mono');
    expect(pickToolRunningSurfaceClass('skill_execute')).toBe('brutal-running-mono');
    expect(pickToolRunningSurfaceClass('agent')).toBe('brutal-running-mono');

    // 2. I/O Transfer / File & Media Mutation -> Punched-tape data dot matrix
    expect(pickToolRunningSurfaceClass('read_file')).toBe('brutal-running-dots');
    expect(pickToolRunningSurfaceClass('write_file')).toBe('brutal-running-dots');
    expect(pickToolRunningSurfaceClass('edit_file')).toBe('brutal-running-dots');
    expect(pickToolRunningSurfaceClass('webpage_fetch')).toBe('brutal-running-dots');
    expect(pickToolRunningSurfaceClass('browser_action')).toBe('brutal-running-dots');
    expect(pickToolRunningSurfaceClass('render_ui')).toBe('brutal-running-dots');
    expect(pickToolRunningSurfaceClass('generate_image')).toBe('brutal-running-dots');
    expect(pickToolRunningSurfaceClass('social_message')).toBe('brutal-running-dots');

    // 3. Search / Recall / Vision -> Vertical laser scan beam
    expect(pickToolRunningSurfaceClass('glob_search')).toBe('brutal-running-scan');
    expect(pickToolRunningSurfaceClass('grep_search')).toBe('brutal-running-scan');
    expect(pickToolRunningSurfaceClass('web_search')).toBe('brutal-running-scan');
    expect(pickToolRunningSurfaceClass('memory_search')).toBe('brutal-running-scan');
    expect(pickToolRunningSurfaceClass('session_search')).toBe('brutal-running-scan');
    expect(pickToolRunningSurfaceClass('analyze_image')).toBe('brutal-running-scan');
  });
});
