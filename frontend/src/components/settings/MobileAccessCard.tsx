import React, { useCallback, useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { useI18n } from '../../i18n';
import { getApiBase, type NodeAuthConfig } from '../../lib/api';
import {
  mobileRequest,
  mobilePairingPayload,
  type MobileDevice,
  type MobileInvitation,
  type MobilePending,
  type MobilePermissions,
} from '../../lib/mobileApi';
import { BrutalButton } from '../BrutalButton';
import { SettingsCard } from './SettingsCard';
import { CopyButton } from './CopyButton';

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
  const [permissions, setPermissions] = useState<MobilePermissions>({
    chat_ids: [],
    all_chats: false,
    create_chats: false,
    send: false,
    stop: false,
  });
  return (
    <div className="border-2 border-brutal-black dark:border-white p-4 space-y-3">
      <strong>
        {device.display_name} · {device.platform}
      </strong>
      <p className="text-sm">
        {t('mobileAccess.compare', { code: device.pairing_id.slice(0, 6) })}
      </p>
      {(['all_chats', 'create_chats', 'send', 'stop'] as const).map((key) => (
        <label key={key} className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={permissions[key]}
            disabled={busy}
            onChange={(event) => setPermissions({ ...permissions, [key]: event.target.checked })}
          />
          {t(`mobileAccess.${key}`)}
        </label>
      ))}
      {!permissions.all_chats && (
        <fieldset className="max-h-48 overflow-auto space-y-2">
          <legend className="text-sm font-bold">{t('mobileAccess.sharedChats')}</legend>
          {chats.map((chat) => (
            <label key={chat.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={permissions.chat_ids.includes(chat.id)}
                disabled={busy}
                onChange={(event) =>
                  setPermissions({
                    ...permissions,
                    chat_ids: event.target.checked
                      ? [...permissions.chat_ids, chat.id]
                      : permissions.chat_ids.filter((id) => id !== chat.id),
                  })
                }
              />
              {chat.title}
            </label>
          ))}
        </fieldset>
      )}
      <p className="text-xs text-neutral-500">{t('mobileAccess.toolPolicy')}</p>
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
  const [invitation, setInvitation] = useState<MobileInvitation | null>(null);
  const [payload, setPayload] = useState('');
  const [qr, setQR] = useState('');
  const [now, setNow] = useState(Date.now());
  const [pending, setPending] = useState<MobilePending[]>([]);
  const [devices, setDevices] = useState<MobileDevice[]>([]);
  const [chats, setChats] = useState<{ id: string; title: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
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
  const generate = () =>
    void act(async () => {
      mobilePairingPayload(origin, { pairing_id: '', invitation: '', expires_at: 0 });
      const next = await mobileRequest<MobileInvitation>('pairing/invite', {});
      const value = mobilePairingPayload(origin, next);
      const image = await QRCode.toDataURL(value, {
        errorCorrectionLevel: 'M',
        margin: 2,
        width: 320,
      });
      setInvitation(next);
      setPayload(value);
      setQR(image);
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
  return (
    <SettingsCard>
      <div className="p-4 space-y-4">
        <h3 className="font-black text-lg">{t('mobileAccess.title')}</h3>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          {t('mobileAccess.description')}
        </p>
        {error && (
          <p role="alert" className="text-brutal-red">
            {error}
          </p>
        )}
        <label className="block space-y-1 text-sm">
          <span>{t('mobileAccess.origin')}</span>
          <input
            className="w-full border-2 border-brutal-black dark:border-white bg-transparent p-2"
            value={origin}
            onChange={(event) => {
              setOrigin(event.target.value);
              setInvitation(null);
              setQR('');
              setPayload('');
            }}
          />
        </label>
        <p className="text-xs text-neutral-500">{t('mobileAccess.network')}</p>
        <BrutalButton variant="warning" disabled={busy || !origin} onClick={generate}>
          {t('mobileAccess.generate')}
        </BrutalButton>
        {invitation &&
          (expired ? (
            <p>{t('mobileAccess.expired')}</p>
          ) : (
            <div className="flex flex-wrap items-center gap-4">
              <img
                src={qr}
                alt={t('mobileAccess.qrAlt')}
                className="w-64 h-64 border-2 border-brutal-black"
              />
              <div className="space-y-2">
                <p>{t('mobileAccess.scan')}</p>
                <p>
                  {t('mobileAccess.expires', {
                    seconds: Math.max(0, Math.ceil(invitation.expires_at - now / 1000)),
                  })}
                </p>
                <div className="flex items-center gap-2">
                  <span>{t('mobileAccess.copy')}</span>
                  <CopyButton value={payload} />
                </div>
              </div>
            </div>
          ))}
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
        {devices.map((device) => (
          <div
            key={device.device_id}
            className="border-t border-neutral-300 dark:border-neutral-700 pt-3 flex justify-between gap-4"
          >
            <div>
              <strong>
                {device.display_name} · {device.platform}
              </strong>
              <p className="text-xs">
                {device.permissions.all_chats
                  ? t('mobileAccess.all_chats')
                  : t('mobileAccess.chatCount', { count: device.permissions.chat_ids.length })}
              </p>
              <p className="text-xs">
                {(['create_chats', 'send', 'stop'] as const)
                  .filter((key) => device.permissions[key])
                  .map((key) => t(`mobileAccess.${key}`))
                  .join(' · ') || t('mobileAccess.readOnly')}
              </p>
            </div>
            <BrutalButton
              disabled={busy}
              variant="danger"
              onClick={() =>
                void act(async () => {
                  await mobileRequest(`devices/${device.device_id}/revoke`, {});
                })
              }
            >
              {t('mobileAccess.revoke')}
            </BrutalButton>
          </div>
        ))}
      </div>
    </SettingsCard>
  );
}
