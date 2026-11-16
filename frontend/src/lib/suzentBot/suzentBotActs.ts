/**
 * Full-body physical acts & stage mapping for the Suzent Bot Engine.
 *
 * Individual full-body act choreographies live in `./acts/`:
 * - `./acts/thinkingActs.ts` (`thought_cloud`, `full_gear`, `question_eureka`, `eureka_levitate`)
 * - `./acts/readingActs.ts` (`speed_reader`, `chomp_file`, `floating_doc`)
 * - `./acts/searchingActs.ts` (`big_loupe`, `binoculars`, `bright_beam`, `peek_radar`)
 * - `./acts/executionActs.ts` (`fountain_pen`, `workout`, `laptop_type`, `turbo_sprinter`, `dj_groove`)
 * - `./acts/subagentActs.ts` (`constellation_command`, `agent_twin_split`, `agent_portal_spawn`, `agent_megaphone_rally`, `agent_antenna_dispatch`, `agent_squad_march`)
 */

import { normalizeToolName } from '../../components/chat/toolSummary';
import {
  ActEvalContext,
  FullBodyActPose,
  SuzentBotStageId,
  SuzentFullBodyAct,
  SuzentGrokBaseState,
  SuzentMorphId,
  SuzentStageSpec,
  createDefaultActPose,
} from './acts/actTypes';
import {
  GEAR_COG_RING,
  evalEurekaLevitate,
  evalFullGear,
  evalQuestionEureka,
  evalThoughtCloud,
} from './acts/thinkingActs';
import { evalChompFile, evalFloatingDoc, evalSpeedReader } from './acts/readingActs';
import { evalBigLoupe, evalBinoculars, evalBrightBeam, evalPeekRadar } from './acts/searchingActs';
import {
  evalDjGroove,
  evalFountainPen,
  evalLaptopType,
  evalTurboSprinter,
  evalWorkout,
} from './acts/executionActs';
import {
  buildMitosisPinchRing,
  evalAgentAntennaDispatch,
  evalAgentMegaphoneRally,
  evalAgentPortalSpawn,
  evalAgentSquadMarch,
  evalAgentTwinSplit,
  evalConstellationCommand,
} from './acts/subagentActs';

export type {
  ActEvalContext,
  FullBodyActPose,
  SuzentBotStageId,
  SuzentFullBodyAct,
  SuzentGrokBaseState,
  SuzentMorphId,
  SuzentStageSpec,
};
export { GEAR_COG_RING, buildMitosisPinchRing };

export const STAGE_SPECS: Record<SuzentBotStageId, SuzentStageSpec> = {
  idle: {
    id: 'idle',
    baseState: 'idle',
    act: 'none',
    acts: ['none'],
    cycleMorph: 'none',
    expressionPool: [0, 8, 2, 20],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  thinking: {
    id: 'thinking',
    baseState: 'suspicious',
    act: 'thought_cloud',
    acts: ['thought_cloud', 'full_gear', 'eureka_levitate'],
    cycleMorph: 'dots',
    expressionPool: [5, 14, 9, 18, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  searching: {
    id: 'searching',
    baseState: 'searching',
    act: 'big_loupe',
    acts: ['big_loupe', 'peek_radar'],
    cycleMorph: 'radar',
    expressionPool: [6, 9, 18, 12, 22],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  reading: {
    id: 'reading',
    baseState: 'curious',
    act: 'speed_reader',
    acts: ['speed_reader'],
    cycleMorph: 'receive',
    expressionPool: [0, 8, 9, 2, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  ingesting: {
    id: 'ingesting',
    baseState: 'curious',
    act: 'chomp_file',
    acts: ['chomp_file'],
    cycleMorph: 'receive',
    expressionPool: [0, 8, 9, 2, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  writing: {
    id: 'writing',
    baseState: 'working',
    act: 'fountain_pen',
    acts: ['fountain_pen'],
    cycleMorph: 'pencil',
    expressionPool: [7, 10, 24, 6],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  bash: {
    id: 'bash',
    baseState: 'working',
    act: 'laptop_type',
    acts: ['laptop_type', 'dj_groove'],
    cycleMorph: 'wave',
    expressionPool: [10, 16, 7, 24],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  starting: {
    id: 'starting',
    baseState: 'working',
    act: 'workout',
    acts: ['workout'],
    cycleMorph: 'wave',
    expressionPool: [7, 10, 24, 6],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  subagent: {
    id: 'subagent',
    baseState: 'playful',
    act: 'constellation_command',
    acts: ['constellation_command', 'agent_twin_split', 'agent_portal_spawn'],
    cycleMorph: 'orbit',
    expressionPool: [17, 23, 6, 10, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  vision: {
    id: 'vision',
    baseState: 'curious',
    act: 'big_loupe',
    acts: ['big_loupe', 'speed_reader'],
    cycleMorph: 'gather',
    expressionPool: [9, 18, 15, 6, 3],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  skill: {
    id: 'skill',
    baseState: 'playful',
    act: 'full_gear',
    acts: ['full_gear', 'eureka_levitate'],
    cycleMorph: 'orbit',
    expressionPool: [16, 3, 10, 2, 17],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  social: {
    id: 'social',
    baseState: 'playful',
    act: 'none',
    acts: ['none'],
    cycleMorph: 'send',
    expressionPool: [2, 8, 3, 19, 0],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  tasks: {
    id: 'tasks',
    baseState: 'curious',
    act: 'thought_cloud',
    acts: ['thought_cloud', 'eureka_levitate'],
    cycleMorph: 'progress',
    expressionPool: [9, 18, 6, 3, 24],
    humming: false,
    notifying: false,
    celebrating: false,
  },
  approval: {
    id: 'approval',
    baseState: 'notifying',
    act: 'none',
    acts: ['none'],
    cycleMorph: 'bang',
    expressionPool: [21, 3, 1],
    humming: false,
    notifying: true,
    celebrating: false,
  },
  error: {
    id: 'error',
    baseState: 'notifying',
    act: 'none',
    acts: ['none'],
    cycleMorph: 'bang',
    expressionPool: [21, 5, 7],
    humming: false,
    notifying: true,
    celebrating: false,
  },
  done: {
    id: 'done',
    baseState: 'celebrate',
    act: 'none',
    acts: ['none'],
    cycleMorph: 'none',
    expressionPool: [2, 3, 19, 11],
    humming: false,
    notifying: false,
    celebrating: true,
  },
};

export function resolveSuzentStage(options: {
  isThinking?: boolean;
  hasPending?: boolean;
  isError?: boolean;
  toolName?: string;
  isActive?: boolean;
}): SuzentBotStageId {
  if (options.hasPending) return 'approval';
  if (options.isError) return 'error';
  if (options.isThinking) return 'thinking';
  if (!options.toolName) return options.isActive ? 'thinking' : 'idle';

  const canonical = normalizeToolName(options.toolName);
  switch (canonical) {
    case 'read_file':
    case 'agent_read':
      return 'reading';
    case 'webpage_fetch':
      return 'ingesting';
    case 'write_file':
    case 'edit_file':
      return 'writing';
    case 'glob_search':
    case 'grep_search':
    case 'web_search':
    case 'search_tools':
      return 'searching';
    case 'memory_search':
    case 'session_search':
      return 'ingesting';
    case 'run_command':
    case 'check_command':
      return 'bash';
    case 'start_command':
    case 'stop_command':
      return 'starting';
    case 'agent':
    case 'agent_send':
    case 'agent_list':
    case 'agent_stop':
      return 'subagent';
    case 'analyze_visual':
    case 'analyze_image':
    case 'render_ui':
    case 'browser_action':
    case 'generate_image':
    case 'edit_image':
    case 'generate_video':
      return 'vision';
    case 'skill_execute':
    case 'run_code':
      return 'skill';
    case 'send_file':
    case 'social_message':
    case 'speak':
    case 'ask_question':
      return 'social';
    case 'create_tasks':
    case 'update_task':
    case 'list_tasks':
    case 'manage_goal':
    case 'schedule_cron':
      return 'tasks';
    default:
      if (
        canonical.includes('search') ||
        canonical.includes('grep') ||
        canonical.includes('glob')
      ) {
        return 'searching';
      }
      if (canonical.includes('read') || canonical.includes('fetch')) return 'reading';
      if (canonical.includes('write') || canonical.includes('edit')) return 'writing';
      if (canonical.includes('agent')) return 'subagent';
      return 'bash';
  }
}

const ACT_EVALUATORS: Partial<Record<SuzentFullBodyAct, (ctx: ActEvalContext) => FullBodyActPose>> =
  {
    thought_cloud: evalThoughtCloud,
    full_gear: evalFullGear,
    question_eureka: evalQuestionEureka,
    eureka_levitate: evalEurekaLevitate,
    speed_reader: evalSpeedReader,
    chomp_file: evalChompFile,
    floating_doc: evalFloatingDoc,
    big_loupe: evalBigLoupe,
    binoculars: evalBinoculars,
    bright_beam: evalBrightBeam,
    peek_radar: evalPeekRadar,
    fountain_pen: evalFountainPen,
    workout: evalWorkout,
    laptop_type: evalLaptopType,
    turbo_sprinter: evalTurboSprinter,
    dj_groove: evalDjGroove,
    constellation_command: evalConstellationCommand,
    agent_twin_split: evalAgentTwinSplit,
    agent_portal_spawn: evalAgentPortalSpawn,
    agent_megaphone_rally: evalAgentMegaphoneRally,
    agent_antenna_dispatch: evalAgentAntennaDispatch,
    agent_squad_march: evalAgentSquadMarch,
  };

/**
 * Evaluate the current full-body physical act pose and foreground/background SVG layers.
 */
export function evaluateFullBodyAct(
  act: SuzentFullBodyAct,
  elapsedSec: number,
  morphAmount: number,
  headPose: { x: number; y: number; rot: number }
): FullBodyActPose {
  const fade = Math.max(0, 1 - morphAmount * 1.5);
  if (act === 'none' || fade <= 0.02) return createDefaultActPose();
  const evaluator = ACT_EVALUATORS[act];
  if (!evaluator) return createDefaultActPose();
  return evaluator({ t: Math.max(0, elapsedSec), fade, headPose });
}
