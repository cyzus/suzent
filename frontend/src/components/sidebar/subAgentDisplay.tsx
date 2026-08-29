/**
 * Shared identity vocabulary for the sub-agent surfaces.
 *
 * The list and the detail panel should introduce an agent the same way, so the
 * avatar and the tool label live here rather than being reinvented per view.
 */
import React from 'react';
import { getProviderInitials, getProviderVisualForModel } from '../../lib/providerVisuals';
import { isSubAgentActive } from '../chat/subAgentStatus';

/**
 * Identity tile. The provider's own colour with its initials -- deliberately
 * not its logo: those are remote CDN URLs and the desktop app's CSP blocks
 * off-origin images, so a logo here would render as a silent blank.
 */
export const AgentAvatar: React.FC<{
  model?: string | null;
  status?: string;
  className?: string;
}> = ({ model, status, className = 'w-7 h-7 text-[9px]' }) => {
  const visual = getProviderVisualForModel(model ?? undefined);
  const background = visual ? `#${visual.color}` : '#525252';
  const initials = visual ? getProviderInitials(visual.label) : 'AI';
  const active = isSubAgentActive(status);

  return (
    <div className="relative shrink-0">
      <div
        className={`flex items-center justify-center border-2 border-brutal-black dark:border-white rounded-sm font-bold tracking-tight text-white ${className}`}
        style={{ backgroundColor: background }}
        aria-hidden="true"
      >
        {initials}
      </div>
      {/* Presence, the way a roster shows it -- additive to the status badge,
          which stays the shared vocabulary across every surface. */}
      <span
        className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white dark:border-zinc-800 ${
          active ? 'bg-brutal-blue animate-pulse' : 'bg-neutral-300 dark:bg-zinc-600'
        }`}
      />
    </div>
  );
};
