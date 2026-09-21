import React from 'react';
import { ArrowPathIcon } from '@heroicons/react/24/outline';

import { useI18n } from '../i18n';
import { BrutalIconButton } from './BrutalButton';

type RefreshButtonProps = Omit<
  React.ComponentProps<typeof BrutalIconButton>,
  'children' | 'label'
> & {
  /** Spins the arrow while the data behind the button is being fetched. */
  spinning?: boolean;
  /** Tooltip/aria-label override; defaults to the shared "Refresh" string. */
  label?: string;
};

/**
 * The one refresh control. Every "reload this view" action in the app renders
 * this so they all look the same (icon-only, never a text button) and all spin
 * while the fetch they triggered is in flight.
 */
export const RefreshButton: React.FC<RefreshButtonProps> = ({
  spinning = false,
  label,
  size = 'icon',
  ...props
}) => {
  const { t } = useI18n();
  const iconSize = size === 'icon-lg' ? 'h-5 w-5' : 'h-4 w-4';

  return (
    <BrutalIconButton label={label ?? t('common.refresh')} size={size} {...props}>
      <ArrowPathIcon className={`${iconSize} stroke-2 ${spinning ? 'animate-spin' : ''}`} />
    </BrutalIconButton>
  );
};
