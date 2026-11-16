import { Point2D } from '../suzentBotGeometry';

export type SuzentBotStageId =
  | 'idle'
  | 'thinking'
  | 'searching'
  | 'reading'
  | 'ingesting'
  | 'writing'
  | 'bash'
  | 'starting'
  | 'subagent'
  | 'vision'
  | 'skill'
  | 'social'
  | 'tasks'
  | 'approval'
  | 'error'
  | 'done';

export type SuzentFullBodyAct =
  | 'none'
  | 'workout'
  | 'eureka_levitate'
  | 'speed_reader'
  | 'chomp_file'
  | 'floating_doc'
  | 'thought_cloud'
  | 'full_gear'
  | 'question_eureka'
  | 'big_loupe'
  | 'bright_beam'
  | 'binoculars'
  | 'laptop_type'
  | 'fountain_pen'
  | 'turbo_sprinter'
  | 'dj_groove'
  | 'peek_radar'
  | 'constellation_command'
  | 'agent_twin_split'
  | 'agent_portal_spawn'
  | 'agent_megaphone_rally'
  | 'agent_antenna_dispatch'
  | 'agent_squad_march';

export type SuzentMorphId =
  | 'none'
  | 'dots'
  | 'orbit'
  | 'radar'
  | 'progress'
  | 'gather'
  | 'wave'
  | 'send'
  | 'receive'
  | 'pencil'
  | 'bang';

export type SuzentGrokBaseState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'searching'
  | 'working'
  | 'suspicious'
  | 'curious'
  | 'playful'
  | 'humming'
  | 'notifying'
  | 'celebrate';

export interface SuzentStageSpec {
  id: SuzentBotStageId;
  baseState: SuzentGrokBaseState;
  act: SuzentFullBodyAct;
  /** Multiple full-body acts that rotate automatically while the bot stays in this stage. */
  acts: readonly SuzentFullBodyAct[];
  cycleMorph: SuzentMorphId;
  expressionPool: readonly number[];
  humming: boolean;
  notifying: boolean;
  celebrating: boolean;
}

export interface FullBodyActPose {
  x: number;
  y: number;
  rot: number;
  sx: number;
  sy: number;
  gazeX: number;
  gazeY: number;
  backHtml: string;
  frontHtml: string;
  targetRing?: readonly Point2D[];
  ringBlend?: number;
  hideEyes?: boolean;
}

export interface ActEvalContext {
  t: number;
  fade: number;
  headPose: { x: number; y: number; rot: number };
}

export function createDefaultActPose(): FullBodyActPose {
  return {
    x: 0,
    y: 0,
    rot: 0,
    sx: 1,
    sy: 1,
    gazeX: 0,
    gazeY: 0,
    backHtml: '',
    frontHtml: '',
  };
}
