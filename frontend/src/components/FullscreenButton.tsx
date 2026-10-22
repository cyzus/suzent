import React from 'react';
import { ArrowsPointingInIcon, ArrowsPointingOutIcon } from '@heroicons/react/24/outline';
import { BrutalIconButton } from './BrutalButton';
import { useI18n } from '../i18n';
interface FullscreenButtonProps {
  expanded?: boolean;
  onClick: React.MouseEventHandler<HTMLButtonElement>;
  disabled?: boolean;
}
export function FullscreenButton({
  expanded = false,
  onClick,
  disabled,
}: FullscreenButtonProps): React.ReactElement {
  const { t } = useI18n();
  const label = t(expanded ? 'workspaceView.shrink' : 'workspaceView.fullscreen');
  const Icon = expanded ? ArrowsPointingInIcon : ArrowsPointingOutIcon;
  return (
    <BrutalIconButton
      type="button"
      onClick={onClick}
      disabled={disabled}
      label={label}
      className="shrink-0 self-start"
    >
      <Icon className="h-4 w-4 stroke-2" />
    </BrutalIconButton>
  );
}
