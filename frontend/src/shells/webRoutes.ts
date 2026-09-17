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
}

export const WEB_DESTINATIONS: WebDestination[] = [
  { path: '/', labelKey: 'console.nav.chat', icon: ChatBubbleLeftRightIcon, framed: false },
  { path: '/ops', labelKey: 'console.nav.ops', icon: ServerStackIcon, framed: true },
  { path: '/devices', labelKey: 'console.nav.devices', icon: ComputerDesktopIcon, framed: true },
  { path: '/mesh', labelKey: 'console.nav.mesh', icon: ShareIcon, framed: true },
  { path: '/usage', labelKey: 'console.nav.usage', icon: ChartBarIcon, framed: true },
  { path: '/settings', labelKey: 'console.nav.settings', icon: Cog6ToothIcon, framed: false },
  { path: '/about', labelKey: 'console.nav.about', icon: InformationCircleIcon, framed: true },
];
