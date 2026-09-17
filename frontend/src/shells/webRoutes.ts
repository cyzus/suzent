/**
 * The console's destinations.
 *
 * Kept as data rather than JSX so the rail, the router and the tests read one
 * list. A destination that is listed but unrouted -- or routed but unreachable
 * -- is the failure mode this shape rules out.
 */

import type { ComponentType, SVGProps } from 'react';
import {
  ChatBubbleLeftRightIcon,
  ComputerDesktopIcon,
  ServerStackIcon,
  ShareIcon,
  ChartBarIcon,
  Cog6ToothIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline';

export interface WebDestination {
  /** Hash path: "/devices" is reached as #/devices. */
  path: string;
  /** i18n key, used for both the rail label and the page heading. */
  labelKey: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /**
   * Whether the console draws the page frame around it. The chat workspace
   * brings its own full-height chrome and wants the whole area.
   */
  framed: boolean;
  /**
   * The settings category this destination supersedes, if any.
   *
   * The console promotes a handful of settings categories to destinations of
   * their own. Declaring that here is what stops the settings sidebar from
   * offering a second route to the same page -- the duplication is invisible
   * from either list alone, so neither list is allowed to be the only record
   * of it.
   */
  settingsCategory?: string;
}

export const WEB_DESTINATIONS: WebDestination[] = [
  { path: '/', labelKey: 'console.nav.chat', icon: ChatBubbleLeftRightIcon, framed: false },
  {
    path: '/ops',
    labelKey: 'console.nav.ops',
    icon: ServerStackIcon,
    framed: true,
    settingsCategory: 'service',
  },
  {
    path: '/devices',
    labelKey: 'console.nav.devices',
    icon: ComputerDesktopIcon,
    framed: true,
    settingsCategory: 'devices',
  },
  {
    path: '/mesh',
    labelKey: 'console.nav.mesh',
    icon: ShareIcon,
    framed: true,
    settingsCategory: 'mesh',
  },
  {
    path: '/usage',
    labelKey: 'console.nav.usage',
    icon: ChartBarIcon,
    framed: true,
    settingsCategory: 'usage',
  },
  { path: '/settings', labelKey: 'console.nav.settings', icon: Cog6ToothIcon, framed: false },
  {
    path: '/about',
    labelKey: 'console.nav.about',
    icon: InformationCircleIcon,
    framed: true,
    settingsCategory: 'about',
  },
];

/**
 * Settings categories the console reaches through its own nav rail.
 *
 * Derived rather than listed again: the settings sidebar hides exactly what
 * the rail already offers, and adding a destination above is all it takes.
 */
export const CONSOLE_HOSTED_CATEGORIES: ReadonlySet<string> = new Set(
  WEB_DESTINATIONS.map((destination) => destination.settingsCategory).filter(
    (category): category is string => category !== undefined
  )
);
