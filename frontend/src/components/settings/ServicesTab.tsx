import React from 'react';
import { useI18n } from '../../i18n';
import { McpTab } from './McpTab';
import { PluginsTab } from './PluginsTab';
import { SettingsPage } from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';

type McpTabProps = React.ComponentProps<typeof McpTab>;

/** Hosted services a plugin signs in to, then MCP servers the user adds. */
export function ServicesTab({
  onPluginsChanged,
  ...props
}: Omit<McpTabProps, 'embedded'> & {
  onPluginsChanged?: () => Promise<void> | void;
}): React.ReactElement {
  const { t } = useI18n();
  return (
    <SettingsPage>
      <SettingsHeader
        title={t('settings.services.title')}
        subtitle={t('settings.services.subtitle')}
      />
      <PluginsTab scope="services" embedded onPluginsChanged={onPluginsChanged} />
      <McpTab {...props} embedded />
    </SettingsPage>
  );
}
