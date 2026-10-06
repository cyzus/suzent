import React, { useCallback, useEffect, useState, useRef } from 'react';
import QRCode from 'qrcode';
import { DevicePhoneMobileIcon, QrCodeIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { getApiBase, type NodeAuthConfig } from '../../lib/api';
import {
  mobileRequest,
  cancelMobileInvitation,
  mobilePairingPayload,
  mobilePairingOrigins,
  type MobileDevice,
  type MobileInvitation,
  type MobilePending,
  type MobilePermissions,
} from '../../lib/mobileApi';
import { BrutalButton } from '../BrutalButton';
import { BrutalMultiSelect } from '../BrutalMultiSelect';
import {
  Badge,
  SectionCardHeader,
  SettingsCard,
  SettingsGrid,
  SettingsListItem,
  SettingsListAction,
} from './SettingsCard';
import { CopyButton } from './CopyButton';

const emptyPermissions = (): MobilePermissions => ({
  chat_ids: [],
  all_chats: false,
  create_chats: false,
  manage_chats: false,
  send: false,
  stop: false,
  approve_tools: false,
});
const fullPermissions = (): MobilePermissions => ({
  ...emptyPermissions(),
  all_chats: true,
  create_chats: true,
  manage_chats: true,
  send: true,
  stop: true,
  approve_tools: true,
});

function PermissionPicker({
  permissions,
  setPermissions,
  chats,
  busy,
}: {
  permissions: MobilePermissions;
  setPermissions: (value: MobilePermissions) => void;
  chats: { id: string; title: string }[];
  busy: boolean;
}): React.ReactElement {
  const { t } = useI18n();
  return (
    <div className="space-y-3">
      <BrutalMultiSelect
        variant="list"
        disabled={busy}
        value={(
          ['all_chats', 'create_chats', 'manage_chats', 'send', 'stop', 'approve_tools'] as const
        ).filter((key) => permissions[key])}
        options={(
          ['all_chats', 'create_chats', 'manage_chats', 'send', 'stop', 'approve_tools'] as const
        ).map((key) => ({ value: key, label: t(`mobileAccess.${key}`) }))}
        onChange={(selected) =>
          setPermissions({
            ...permissions,
            all_chats: selected.includes('all_chats'),
            create_chats: selected.includes('create_chats'),
            manage_chats: selected.includes('manage_chats'),
            send: selected.includes('send'),
            stop: selected.includes('stop'),
            approve_tools: selected.includes('approve_tools'),
          })
        }
      />
      {!permissions.all_chats && (
        <BrutalMultiSelect
          variant="list"
          label={t('mobileAccess.sharedChats')}
          disabled={busy}
          value={permissions.chat_ids}
          options={chats.map((chat) => ({ value: chat.id, label: chat.title }))}
          onChange={(chat_ids) => setPermissions({ ...permissions, chat_ids })}
        />
      )}
      <p className="text-xs text-neutral-500">{t('mobileAccess.toolPolicy')}</p>
    </div>
  );
}

function ApprovePhone({
  device,
  chats,
  busy,
  decide,
}: {
  device: MobilePending;
  chats: { id: string; title: string }[];
  busy: boolean;
  decide: (id: string, permissions: MobilePermissions | null) => void;
}): React.ReactElement {
  const { t } = useI18n();
  const [permissions, setPermissions] = useState<MobilePermissions>(emptyPermissions);
  return (
    <div className="border-2 border-brutal-black dark:border-white p-4 space-y-3">
      <strong>
        {device.display_name} · {device.platform}
      </strong>
      <p className="text-sm">
        {t('mobileAccess.compare', { code: device.pairing_id.slice(0, 6) })}
      </p>
      <PermissionPicker
        permissions={permissions}
        setPermissions={setPermissions}
        chats={chats}
        busy={busy}
      />
      <div className="flex gap-2">
        <BrutalButton
          disabled={busy}
          variant="warning"
          onClick={() => decide(device.pairing_id, permissions)}
        >
          {t('mobileAccess.approve')}
        </BrutalButton>
        <BrutalButton disabled={busy} onClick={() => decide(device.pairing_id, null)}>
          {t('mobileAccess.deny')}
        </BrutalButton>
      </div>
    </div>
  );
}

export function MobileAccessCard({
  config,
}: {
  config: NodeAuthConfig | null;
}): React.ReactElement {
  const { t } = useI18n();
  const [origin, setOrigin] = useState('');
  const [permissions, setPermissions] = useState<MobilePermissions>(() => ({
    ...fullPermissions(),
    manage_chats: false,
  }));
  const invitationRef = useRef<MobileInvitation | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    const discard = () => {
      const active = invitationRef.current;
      invitationRef.current = null;
      if (active) void cancelMobileInvitation(active.pairing_id).catch(() => {});
    };
    window.addEventListener('pagehide', discard);
    return () => {
      mounted.current = false;
      window.removeEventListener('pagehide', discard);
      discard();
    };
  }, []);
  const [invitation, setInvitation] = useState<MobileInvitation | null>(null);
  const [payload, setPayload] = useState('');
  const [qr, setQR] = useState('');
  const [now, setNow] = useState(Date.now());
  const [pending, setPending] = useState<MobilePending[]>([]);
  const [devices, setDevices] = useState<MobileDevice[]>([]);
  const [chats, setChats] = useState<{ id: string; title: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState<{
    deviceId: string;
    permissions: MobilePermissions;
  } | null>(null);
  useEffect(() => {
    if (config?.lan_host)
      setOrigin((current) => current || `http://${config.lan_host}:${config.port}`);
  }, [config]);
  const refresh = useCallback(async () => {
    const [pendingResult, deviceResult] = await Promise.all([
      mobileRequest<{ pending: MobilePending[] }>('pairing/pending'),
      mobileRequest<{ devices: MobileDevice[] }>('devices'),
    ]);
    setPending(pendingResult.pending);
    setDevices(deviceResult.devices);
  }, []);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        if (alive) await refresh();
      } catch {
        if (alive) setError(t('mobileAccess.loadError'));
      }
      if (alive) timer = setTimeout(poll, 2000);
    };
    void poll();
    const clock = setInterval(() => setNow(Date.now()), 1000);
    void fetch(`${getApiBase()}/chats?limit=1000`)
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const result = await response.json();
        if (alive) setChats(result.chats);
      })
      .catch(() => {
        if (alive) setError(t('mobileAccess.loadError'));
      });
    return () => {
      alive = false;
      clearTimeout(timer);
      clearInterval(clock);
    };
  }, [refresh, t]);
  const act = async (operation: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await operation();
      await refresh();
    } catch {
      setError(t('mobileAccess.actionError'));
    } finally {
      setBusy(false);
    }
  };
  const clearInvitation = () => {
    invitationRef.current = null;
    setInvitation(null);
    setPayload('');
    setQR('');
  };
  const cancelActive = async () => {
    const active = invitationRef.current;
    if (active) await cancelMobileInvitation(active.pairing_id);
    clearInvitation();
  };
  const generate = () =>
    void act(async () => {
      const candidates = mobilePairingOrigins(origin, config?.addresses);
      mobilePairingPayload(origin, { pairing_id: '', invitation: '', expires_at: 0 }, candidates);
      await cancelActive();
      const next = await mobileRequest<MobileInvitation>('pairing/invite', {
        permissions,
        local_tls: new URL(origin).protocol !== 'https:',
      });
      if (!mounted.current || next.approval !== 'phone') {
        await cancelMobileInvitation(next.pairing_id);
        if (mounted.current) throw new Error('Update the desktop backend');
        return;
      }
      invitationRef.current = next;
      try {
        const value = mobilePairingPayload(origin, next, candidates);
        const image = await QRCode.toDataURL(value, {
          errorCorrectionLevel: 'M',
          margin: 2,
          width: 320,
        });
        if (!mounted.current || invitationRef.current !== next) return;
        setInvitation(next);
        setPayload(value);
        setQR(image);
      } catch (error) {
        await cancelMobileInvitation(next.pairing_id);
        invitationRef.current = null;
        throw error;
      }
    });
  const decide = (id: string, permissions: MobilePermissions | null) =>
    void act(async () => {
      await mobileRequest(`pairing/${id}/decide`, { permissions });
      if (invitation?.pairing_id === id) {
        setInvitation(null);
        setPayload('');
        setQR('');
      }
    });
  const expired = invitation !== null && invitation.expires_at * 1000 <= now;
  const invitationActive = invitation !== null && !expired;
  return (
    <SettingsCard>
      <div className="space-y-5">
        <SectionCardHeader
          icon={<DevicePhoneMobileIcon className="h-6 w-6" />}
          title={t('mobileAccess.title')}
          actions={<Badge>{t('mobileAccess.deviceCount', { count: devices.length })}</Badge>}
        />
        {error && (
          <p
            role="alert"
            className="border-2 border-brutal-red bg-red-50 p-3 text-sm text-brutal-red dark:bg-red-950/20"
          >
            {error}
          </p>
        )}
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.85fr)]">
          <div className="min-w-0 space-y-4">
            <ol className="space-y-4">
              {(['prepareStep', 'scanStep', 'confirmStep'] as const).map((step, index) => (
                <li key={step} className="flex items-start gap-3">
                  <span
                    className="flex h-7 w-7 shrink-0 items-center justify-center border-2 border-brutal-black bg-brutal-yellow text-sm font-black text-brutal-black"
                    aria-hidden="true"
                  >
                    {index + 1}
                  </span>
                  <p className="pt-1 text-sm font-bold">{t(`mobileAccess.${step}`)}</p>
                </li>
              ))}
            </ol>
            <details className="border-2 border-brutal-black p-3 dark:border-white">
              <summary className="cursor-pointer text-sm font-bold">
                {t('mobileAccess.accessSettings')}
              </summary>
              <div className="space-y-3 pt-3">
                <PermissionPicker
                  permissions={permissions}
                  setPermissions={setPermissions}
                  chats={chats}
                  busy={busy || invitationActive}
                />
              </div>
            </details>
            <details className="border-2 border-brutal-black p-3 dark:border-white">
              <summary className="cursor-pointer text-sm font-bold">
                {t('mobileAccess.networkSettings')}
              </summary>
              <div className="space-y-3 pt-3">
                <label className="block space-y-1 text-sm">
                  <span>{t('mobileAccess.origin')}</span>
                  <input
                    className="w-full border-2 border-brutal-black bg-transparent p-2 dark:border-white"
                    value={origin}
                    disabled={busy || invitationActive}
                    onChange={(event) => setOrigin(event.target.value)}
                  />
                </label>
                <p className="text-xs leading-relaxed text-neutral-600 dark:text-neutral-400">
                  {t('mobileAccess.network')}
                </p>
                {config?.addresses?.map((address) => (
                  <p key={address.gateway_url} className="break-all font-mono text-xs">
                    {address.label}: {address.host}
                  </p>
                ))}
              </div>
            </details>
          </div>
          <div className="flex flex-col items-center justify-center gap-4 border-2 border-brutal-black bg-neutral-50 p-4 text-center dark:border-white dark:bg-zinc-900">
            {invitationActive ? (
              <>
                <Badge tone="amber">{t('mobileAccess.waiting')}</Badge>
                <img
                  src={qr}
                  alt={t('mobileAccess.qrAlt')}
                  className="h-auto w-full max-w-64 border-2 border-brutal-black bg-white"
                />
                <p className="font-mono text-xs">
                  {t('mobileAccess.expires', {
                    seconds: Math.max(0, Math.ceil(invitation!.expires_at - now / 1000)),
                  })}
                </p>
                <p className="max-w-sm text-xs leading-relaxed text-neutral-600 dark:text-neutral-400">
                  {t('mobileAccess.scan')}
                </p>
                <div className="flex items-center gap-2 text-xs">
                  <span>{t('mobileAccess.copy')}</span>
                  <CopyButton value={payload} label={t('mobileAccess.copy')} />
                </div>
              </>
            ) : (
              <>
                <QrCodeIcon className="h-16 w-16 text-neutral-400" aria-hidden="true" />
                <p className="text-sm font-bold" role="status">
                  {t(expired ? 'mobileAccess.expired' : 'mobileAccess.ready')}
                </p>
                <BrutalButton
                  variant="warning"
                  disabled={busy || !origin.trim()}
                  onClick={generate}
                >
                  {t(
                    busy
                      ? 'mobileAccess.generating'
                      : expired
                        ? 'mobileAccess.regenerate'
                        : 'mobileAccess.generate'
                  )}
                </BrutalButton>
              </>
            )}
            {invitation && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void act(cancelActive)}
                className="text-xs font-medium text-neutral-500 underline decoration-neutral-300 underline-offset-4 transition-colors hover:text-brutal-black hover:decoration-current focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 disabled:cursor-not-allowed disabled:opacity-50 dark:text-neutral-400 dark:decoration-neutral-600 dark:hover:text-white"
              >
                {t('mobileAccess.cancelInvitation')}
              </button>
            )}
          </div>
        </div>
        {pending
          .filter((device) => device.expires_at * 1000 > now)
          .map((device) => (
            <ApprovePhone
              key={device.pairing_id}
              device={device}
              chats={chats}
              busy={busy}
              decide={decide}
            />
          ))}
        <div className="border-t-2 border-brutal-black pt-4 dark:border-white">
          <h4 className="text-sm font-black">{t('mobileAccess.pairedDevices')}</h4>
          {devices.length === 0 && (
            <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-400">
              {t('mobileAccess.noDevices')}
            </p>
          )}
        </div>
        <SettingsGrid density="compact">
          {devices.map((device) => (
            <SettingsListItem key={device.device_id}>
              <div className="flex items-center gap-3 p-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center border-2 border-brutal-black bg-white text-brutal-black dark:bg-zinc-800 dark:text-white">
                  <DevicePhoneMobileIcon className="h-5 w-5" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <h5 className="truncate text-sm font-black" title={device.display_name}>
                    {device.display_name}
                  </h5>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">
                    {device.platform === 'ios' ? 'iOS' : 'Android'}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 px-3 pb-3">
                <Badge>
                  {device.permissions.all_chats
                    ? t('mobileAccess.shortAllChats')
                    : t('mobileAccess.chatCount', { count: device.permissions.chat_ids.length })}
                </Badge>
                {(['create_chats', 'manage_chats', 'send', 'stop', 'approve_tools'] as const)
                  .filter((key) => device.permissions[key])
                  .map((key) => (
                    <Badge key={key}>{t(`mobileAccess.short_${key}`)}</Badge>
                  ))}
                {!device.permissions.create_chats &&
                  !device.permissions.manage_chats &&
                  !device.permissions.send &&
                  !device.permissions.stop &&
                  !device.permissions.approve_tools && <Badge>{t('mobileAccess.readOnly')}</Badge>}
              </div>
              <div className="flex items-start justify-between gap-3 border-t-2 border-brutal-black bg-white p-3 dark:bg-zinc-800">
                <SettingsListAction
                  disabled={busy || editing !== null}
                  onClick={() =>
                    setEditing({
                      deviceId: device.device_id,
                      permissions: {
                        ...device.permissions,
                        chat_ids: [...device.permissions.chat_ids],
                      },
                    })
                  }
                >
                  {t('mobileAccess.editPermissions')}
                </SettingsListAction>
                <SettingsListAction
                  tone="red"
                  disabled={busy}
                  onClick={() =>
                    void act(async () => {
                      await mobileRequest(`devices/${device.device_id}/revoke`, {});
                    })
                  }
                >
                  {t('mobileAccess.revoke')}
                </SettingsListAction>
              </div>
              {editing?.deviceId === device.device_id && (
                <div className="space-y-3 border-t-2 border-brutal-black p-3">
                  <PermissionPicker
                    permissions={editing.permissions}
                    chats={chats}
                    busy={busy}
                    setPermissions={(permissions) =>
                      setEditing({ deviceId: device.device_id, permissions })
                    }
                  />
                  <div className="flex justify-end gap-2">
                    <BrutalButton size="xs" disabled={busy} onClick={() => setEditing(null)}>
                      {t('mobileAccess.cancelEdit')}
                    </BrutalButton>
                    <BrutalButton
                      size="xs"
                      variant="primary"
                      disabled={busy}
                      onClick={() =>
                        void act(async () => {
                          await mobileRequest(`devices/${device.device_id}/permissions`, {
                            permissions: editing.permissions,
                          });
                          setEditing(null);
                        })
                      }
                    >
                      {t('mobileAccess.savePermissions')}
                    </BrutalButton>
                  </div>
                </div>
              )}
            </SettingsListItem>
          ))}
        </SettingsGrid>
      </div>
    </SettingsCard>
  );
}
