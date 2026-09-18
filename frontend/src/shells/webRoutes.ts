/**
 * The console's destinations.
 *
 * One list, grouped the way the settings sidebar groups its categories. The
 * console used to keep two: an icon rail of promoted pages and a settings
 * sidebar holding the rest, with a derived set to stop the second from
 * offering a route the first already had. Nothing told the reader which half a
 * given page lived in, so "Devices" was missing from the only list that had
 * labels. Merging them is what removes that question -- and the bookkeeping
 * that came with it.
 *
 * Kept as data rather than JSX so the sidebar, the router and the tests read
 * one list. A destination that is listed but unrouted -- or routed but
 * unreachable -- is the failure mode this shape rules out.
 */

import type { ComponentType, SVGProps } from 'react';
import {
  AdjustmentsHorizontalIcon,
  BoltIcon,
  ChartBarIcon,
  ChatBubbleLeftRightIcon,
  CircleStackIcon,
  ClockIcon,
  CloudArrowUpIcon,
  ComputerDesktopIcon,
  CpuChipIcon,
  InformationCircleIcon,
  PaintBrushIcon,
  ServerStackIcon,
  ShareIcon,
  ShieldCheckIcon,
  WrenchScrewdriverIcon,
} from '@heroicons/react/24/outline';

import type { SettingsCategory } from '../components/settings/SettingsNavigation';

export interface WebDestination {
  /** Hash path: "/devices" is reached as #/devices. */
  path: string;
  /** i18n key, used for both the sidebar label and the page heading. */
  labelKey: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /**
   * The settings category this destination shows, when it shows one.
   *
   * Most console pages are a settings category rendered as a page of its own.
   * The exceptions are chat, and operations -- whose desktop counterpart drives
   * Tauri commands a browser cannot reach, so the console has its own.
   */
  category?: SettingsCategory;
  /**
   * Whether the console draws its scrolling page frame around it. The chat
   * workspace brings its own full-height chrome and wants the whole area.
   */
  framed: boolean;
  /** Usage renders wide tables and needs the extra column. */
  wide?: boolean;
}

export interface WebDestinationGroup {
  /** Empty for the ungrouped entries that sit above the first heading. */
  labelKey: string;
  destinations: WebDestination[];
}

export const WEB_DESTINATION_GROUPS: WebDestinationGroup[] = [
  {
    labelKey: '',
    destinations: [
      { path: '/', labelKey: 'console.nav.chat', icon: ChatBubbleLeftRightIcon, framed: false },
    ],
  },
  {
    labelKey: 'settings.groups.agent',
    destinations: [
      {
        path: '/providers',
        labelKey: 'settings.categories.providers',
        icon: ServerStackIcon,
        category: 'providers',
        framed: true,
      },
      {
        path: '/roles',
        labelKey: 'settings.categories.roles',
        icon: AdjustmentsHorizontalIcon,
        category: 'roles',
        framed: true,
      },
      {
        path: '/memory',
        labelKey: 'settings.categories.memory',
        icon: CircleStackIcon,
        category: 'memory',
        framed: true,
      },
      {
        path: '/automation',
        labelKey: 'settings.categories.automation',
        icon: ClockIcon,
        category: 'automation',
        framed: true,
      },
    ],
  },
  {
    labelKey: 'settings.groups.connections',
    destinations: [
      {
        path: '/social',
        labelKey: 'settings.categories.social',
        icon: ChatBubbleLeftRightIcon,
        category: 'social',
        framed: true,
      },
      {
        path: '/mcp',
        labelKey: 'settings.categories.mcp',
        icon: WrenchScrewdriverIcon,
        category: 'mcp',
        framed: true,
      },
      {
        path: '/acp-agents',
        labelKey: 'settings.categories.acpAgents',
        icon: BoltIcon,
        category: 'acp-agents',
        framed: true,
      },
      {
        path: '/devices',
        labelKey: 'settings.categories.devices',
        icon: ComputerDesktopIcon,
        category: 'devices',
        framed: true,
      },
      {
        path: '/mesh',
        labelKey: 'settings.categories.mesh',
        icon: ShareIcon,
        category: 'mesh',
        framed: true,
      },
    ],
  },
  {
    labelKey: 'settings.groups.application',
    destinations: [
      {
        path: '/appearance',
        labelKey: 'settings.categories.appearance',
        icon: PaintBrushIcon,
        category: 'appearance',
        framed: true,
      },
      // No `category`: the desktop's Background Service tab drives Tauri
      // commands, so the console answers the same question over /ops/*.
      { path: '/ops', labelKey: 'console.nav.ops', icon: CpuChipIcon, framed: true },
      {
        path: '/security',
        labelKey: 'settings.categories.security',
        icon: ShieldCheckIcon,
        category: 'security',
        framed: true,
      },
      {
        path: '/data',
        labelKey: 'settings.categories.data',
        icon: CloudArrowUpIcon,
        category: 'data',
        framed: true,
      },
      {
        path: '/usage',
        labelKey: 'settings.categories.usage',
        icon: ChartBarIcon,
        category: 'usage',
        framed: true,
        wide: true,
      },
      {
        path: '/about',
        labelKey: 'settings.categories.about',
        icon: InformationCircleIcon,
        category: 'about',
        framed: true,
      },
    ],
  },
];

export const WEB_DESTINATIONS: WebDestination[] = WEB_DESTINATION_GROUPS.flatMap(
  (group) => group.destinations
);

/**
 * Where "/settings" goes now that settings is not a place.
 *
 * The console used to host the whole settings modal at one route. Every
 * category is its own page now, but that URL is in released docs and in
 * whatever anyone bookmarked, so it lands on the first of them.
 */
export const LEGACY_SETTINGS_PATH = '/settings';
export const LEGACY_SETTINGS_TARGET = '/providers';

/**
 * The console route showing a settings category, if one does.
 *
 * Chat is the one page the console renders without its navigation, so the
 * chat sidebar's Settings button has to navigate rather than open the
 * desktop's modal. This is how it finds where to go.
 */
export function consolePathForCategory(category: string): string | null {
  return WEB_DESTINATIONS.find((destination) => destination.category === category)?.path ?? null;
}
