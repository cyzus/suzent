import React, { useEffect, useState } from 'react';

import {
  CronJob,
  CronRun,
  HeartbeatStatus,
  fetchCronJobs,
  createCronJob,
  updateCronJob,
  deleteCronJob,
  triggerCronJob,
  fetchCronStatus,
  fetchCronJobRuns,
  fetchHeartbeatStatus,
  enableHeartbeat,
  disableHeartbeat,
  triggerHeartbeat,
  fetchHeartbeatMd,
  saveHeartbeatMd,
} from '../../lib/api';
import { BrutalSelect } from '../BrutalSelect';

interface AutomationTabProps {
  models: string[];
}

export function AutomationTab({ models }: AutomationTabProps): React.ReactElement {
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [status, setStatus] = useState<{ scheduler_running: boolean; total_jobs: number; active_jobs: number } | null>(null);
  const [heartbeat, setHeartbeat] = useState<HeartbeatStatus | null>(null);
  const [loading, setLoading] = useState(false);

  // Heartbeat MD editor state
  const [mdContent, setMdContent] = useState('');
  const [mdEditing, setMdEditing] = useState(false);
  const [mdSaving, setMdSaving] = useState(false);
  const [mdDirty, setMdDirty] = useState(false);

  // Form state (new job)
  const [name, setName] = useState('');
  const [cronExpr, setCronExpr] = useState('');
  const [prompt, setPrompt] = useState('');
  const [deliveryMode, setDeliveryMode] = useState<'announce' | 'none'>('announce');
  const [modelOverride, setModelOverride] = useState('');
  const [isActive, setIsActive] = useState(true);

  // Edit state
  const [editingJobId, setEditingJobId] = useState<number | null>(null);
  const [editFields, setEditFields] = useState<Partial<CronJob>>({});

  // History state
  const [historyJobId, setHistoryJobId] = useState<number | null>(null);
  const [historyRuns, setHistoryRuns] = useState<CronRun[]>([]);

  const refresh = async () => {
    try {
      const [jobList, statusData, hbStatus, md] = await Promise.all([
        fetchCronJobs(), fetchCronStatus(), fetchHeartbeatStatus(), fetchHeartbeatMd(),
      ]);
      setJobs(jobList);
      setStatus(statusData);
      setHeartbeat(hbStatus);
      if (!mdDirty) {
        setMdContent(md.content);
      }
    } catch (e) {
      console.error('Failed to load automation data:', e);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleCreate = async () => {
    if (!name.trim() || !cronExpr.trim() || !prompt.trim()) return;
    setLoading(true);
    try {
      await createCronJob({
        name: name.trim(),
        cron_expr: cronExpr.trim(),
        prompt: prompt.trim(),
        active: isActive,
        delivery_mode: deliveryMode,
        model_override: modelOverride || null,
      });
      setName('');
      setCronExpr('');
      setPrompt('');
      setDeliveryMode('announce');
      setModelOverride('');
      setIsActive(true);
      await refresh();
    } catch (e: any) {
      alert(e.message || 'Failed to create job');
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (job: CronJob) => {
    setLoading(true);
    try {
      await updateCronJob(job.id, { active: !job.active });
      await refresh();
    } finally {
      setLoading(false);
    }
  };

  const handleTrigger = async (job: CronJob) => {
    setLoading(true);
    try {
      await triggerCronJob(job.id);
      setTimeout(refresh, 2000);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (job: CronJob) => {
    setLoading(true);
    try {
      await deleteCronJob(job.id);
      await refresh();
    } finally {
      setLoading(false);
    }
  };

  const startEdit = (job: CronJob) => {
    setEditingJobId(job.id);
    setEditFields({
      name: job.name,
      cron_expr: job.cron_expr,
      prompt: job.prompt,
      delivery_mode: job.delivery_mode,
      model_override: job.model_override,
    });
  };

  const cancelEdit = () => {
    setEditingJobId(null);
    setEditFields({});
  };

  const handleSaveEdit = async () => {
    if (editingJobId === null) return;
    setLoading(true);
    try {
      await updateCronJob(editingJobId, editFields);
      setEditingJobId(null);
      setEditFields({});
      await refresh();
    } catch (e: any) {
      alert(e.message || 'Failed to update job');
    } finally {
      setLoading(false);
    }
  };

  const toggleHistory = async (jobId: number) => {
    if (historyJobId === jobId) {
      setHistoryJobId(null);
      setHistoryRuns([]);
      return;
    }
    setHistoryJobId(jobId);
    const runs = await fetchCronJobRuns(jobId);
    setHistoryRuns(runs);
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return '-';
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  const modelOptions = [
    { value: '', label: 'Default' },
    ...models.map(m => ({ value: m, label: m })),
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-4xl font-brutal font-black uppercase text-brutal-black">Automation</h2>
      </div>

      {/* Status Card */}
      <div className="bg-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6 mb-6">
        <div className="flex items-start gap-4">
          <div className={`w-12 h-12 border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white ${status?.scheduler_running ? 'bg-brutal-green' : 'bg-neutral-400'}`}>
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <h3 className="text-xl font-bold uppercase">Scheduler Status</h3>
            <p className="text-sm text-neutral-600 mt-1">
              {status?.scheduler_running ? (
                <span className="text-green-700 font-bold">Running</span>
              ) : (
                <span className="text-red-700 font-bold">Stopped</span>
              )}
              {status && ` \u2014 ${status.active_jobs} active / ${status.total_jobs} total jobs`}
            </p>
          </div>
        </div>
      </div>

      {/* Heartbeat Card */}
      <div className="bg-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6 mb-6">
        <div className="flex items-start gap-4 mb-4">
          <div className={`w-12 h-12 border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white ${heartbeat?.enabled ? 'bg-brutal-green' : 'bg-neutral-400'}`}>
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
            </svg>
          </div>
          <div className="flex-1">
            <h3 className="text-xl font-bold uppercase">Heartbeat</h3>
            <p className="text-sm text-neutral-600 mt-1">
              Periodic agent check-in using <span className="font-mono text-xs">/shared/HEARTBEAT.md</span> checklist.
              {heartbeat?.enabled
                ? ` Running every ${heartbeat.interval_minutes}m in a persistent session.`
                : heartbeat?.heartbeat_md_exists
                  ? ' Disabled. Enable to start periodic check-ins.'
                  : ' Create /shared/HEARTBEAT.md to enable.'}
            </p>
          </div>
        </div>

        {heartbeat && (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <button
                onClick={async () => {
                  setLoading(true);
                  try {
                    if (heartbeat.enabled) {
                      await disableHeartbeat();
                    } else {
                      await enableHeartbeat();
                    }
                    await refresh();
                  } catch (e: any) {
                    alert(e.message);
                  } finally {
                    setLoading(false);
                  }
                }}
                disabled={loading || !heartbeat.heartbeat_md_exists}
                className={`px-4 py-2 border-2 border-brutal-black font-bold uppercase text-xs transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50 ${heartbeat.enabled ? 'bg-neutral-200 text-brutal-black' : 'bg-brutal-green text-brutal-black'}`}
              >
                {heartbeat.enabled ? 'Disable' : 'Enable'}
              </button>
              <button
                onClick={async () => {
                  setLoading(true);
                  try {
                    await triggerHeartbeat();
                    setTimeout(refresh, 3000);
                  } finally {
                    setLoading(false);
                  }
                }}
                disabled={loading || !heartbeat.heartbeat_md_exists}
                className="px-4 py-2 bg-brutal-blue text-white border-2 border-brutal-black font-bold uppercase text-xs transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
              >
                Run Now
              </button>
            </div>

            {/* HEARTBEAT.md Editor */}
            <div className="border-2 border-brutal-black">
              <button
                onClick={async () => {
                  if (!mdEditing) {
                    const md = await fetchHeartbeatMd();
                    setMdContent(md.content);
                    setMdDirty(false);
                  }
                  setMdEditing(!mdEditing);
                }}
                className="w-full px-3 py-2 text-left text-xs font-bold uppercase bg-neutral-100 hover:bg-neutral-200 transition-colors flex items-center justify-between"
              >
                <span>HEARTBEAT.md</span>
                <span className="text-neutral-400">{mdEditing ? 'collapse' : 'edit'}</span>
              </button>
              {mdEditing && (
                <div className="p-3 space-y-2">
                  <textarea
                    value={mdContent}
                    onChange={e => { setMdContent(e.target.value); setMdDirty(true); }}
                    rows={10}
                    placeholder="# Heartbeat Checklist&#10;&#10;- Check for anything urgent&#10;- Review pending tasks"
                    className="w-full bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 resize-y"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={async () => {
                        setMdSaving(true);
                        try {
                          await saveHeartbeatMd(mdContent);
                          setMdDirty(false);
                          await refresh();
                        } finally {
                          setMdSaving(false);
                        }
                      }}
                      disabled={mdSaving || !mdDirty}
                      className="px-4 py-1.5 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                    >
                      {mdSaving ? 'Saving...' : 'Save'}
                    </button>
                  </div>
                </div>
              )}
            </div>

            {heartbeat.last_run_at && (
              <div className="text-xs text-neutral-500 space-y-1">
                <div>Last run: {formatDate(heartbeat.last_run_at)}</div>
                {heartbeat.last_result && (
                  <div className="truncate" title={heartbeat.last_result}>
                    Result: {heartbeat.last_result === 'HEARTBEAT_OK' ? 'OK (nothing needed attention)' : heartbeat.last_result.substring(0, 120)}
                  </div>
                )}
                {heartbeat.last_error && (
                  <div className="text-red-600 truncate" title={heartbeat.last_error}>
                    Error: {heartbeat.last_error}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Add Job Form */}
      <div className="bg-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6 mb-6">
        <div className="flex items-start gap-4 mb-6">
          <div className="w-12 h-12 bg-brutal-blue border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" /></svg>
          </div>
          <div>
            <h3 className="text-xl font-bold uppercase">Add New Job</h3>
            <p className="text-sm text-neutral-600 mt-1">Schedule a prompt to run automatically on a cron schedule.</p>
          </div>
        </div>

        <div className="space-y-4">
          <div className="flex gap-2">
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Job name"
              className="flex-1 bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
            />
            <input
              value={cronExpr}
              onChange={e => setCronExpr(e.target.value)}
              placeholder="Cron expr (e.g. */5 * * * *)"
              className="w-52 bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
            />
          </div>

          <textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder="Prompt to execute on schedule..."
            rows={3}
            className="w-full bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 resize-y"
          />

          <div className="flex flex-wrap gap-4 items-center">
            <BrutalSelect
              value={deliveryMode}
              onChange={val => setDeliveryMode(val as 'announce' | 'none')}
              options={[
                { value: 'announce', label: 'Announce' },
                { value: 'none', label: 'Silent' },
              ]}
              label="Delivery"
              className="w-36"
            />

            <BrutalSelect
              value={modelOverride}
              onChange={setModelOverride}
              options={modelOptions}
              label="Model"
              className="w-48"
            />

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={isActive}
                onChange={e => setIsActive(e.target.checked)}
                className="w-5 h-5 border-2 border-brutal-black accent-brutal-black"
              />
              <span className="font-bold text-xs uppercase">Active</span>
            </label>
          </div>

          <button
            onClick={handleCreate}
            disabled={loading || !name.trim() || !cronExpr.trim() || !prompt.trim()}
            className="px-4 py-2 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-brutal-black hover:brightness-110 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
          >
            {loading ? 'Creating...' : 'Add Job'}
          </button>
        </div>
      </div>

      {/* Job List */}
      <div className="bg-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6">
        <div className="flex items-start gap-4 mb-6">
          <div className="w-12 h-12 bg-black border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <div>
            <h3 className="text-xl font-bold uppercase">Scheduled Jobs</h3>
            <p className="text-sm text-neutral-600 mt-1">Manage your automated tasks. Toggle, trigger, edit, or remove jobs.</p>
          </div>
        </div>

        {jobs.length === 0 ? (
          <div className="text-center py-8 text-neutral-500 font-bold uppercase">
            No cron jobs configured yet.
          </div>
        ) : (
          <div className="space-y-3">
            {jobs.map(job => (
              <div
                key={job.id}
                className="bg-neutral-50 border-2 border-brutal-black p-4 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
              >
                {editingJobId === job.id ? (
                  /* Edit mode */
                  <div className="space-y-3">
                    <div className="flex gap-2">
                      <input
                        value={editFields.name || ''}
                        onChange={e => setEditFields({ ...editFields, name: e.target.value })}
                        placeholder="Job name"
                        className="flex-1 bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
                      />
                      <input
                        value={editFields.cron_expr || ''}
                        onChange={e => setEditFields({ ...editFields, cron_expr: e.target.value })}
                        placeholder="Cron expression"
                        className="w-52 bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50"
                      />
                    </div>
                    <textarea
                      value={editFields.prompt || ''}
                      onChange={e => setEditFields({ ...editFields, prompt: e.target.value })}
                      rows={3}
                      className="w-full bg-white border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 resize-y"
                    />
                    <div className="flex flex-wrap gap-4 items-center">
                      <BrutalSelect
                        value={editFields.delivery_mode || 'announce'}
                        onChange={val => setEditFields({ ...editFields, delivery_mode: val as 'announce' | 'none' })}
                        options={[
                          { value: 'announce', label: 'Announce' },
                          { value: 'none', label: 'Silent' },
                        ]}
                        label="Delivery"
                        className="w-36"
                      />
                      <BrutalSelect
                        value={editFields.model_override || ''}
                        onChange={val => setEditFields({ ...editFields, model_override: val || null })}
                        options={modelOptions}
                        label="Model"
                        className="w-48"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={handleSaveEdit}
                        disabled={loading}
                        className="px-4 py-1.5 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                      >
                        Save
                      </button>
                      <button
                        onClick={cancelEdit}
                        className="px-4 py-1.5 bg-neutral-200 border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  /* View mode */
                  <>
                    <div className="flex items-center gap-4 mb-2">
                      <input
                        type="checkbox"
                        checked={job.active}
                        onChange={() => handleToggle(job)}
                        disabled={loading}
                        className="w-5 h-5 border-2 border-brutal-black accent-brutal-black"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-brutal-black">{job.name}</span>
                          <span className={`text-[10px] px-2 py-0.5 border-2 font-bold uppercase ${job.active ? 'border-brutal-black bg-brutal-green text-brutal-black' : 'border-brutal-black bg-neutral-200 text-brutal-black'}`}>
                            {job.active ? 'ON' : 'OFF'}
                          </span>
                          <span className="text-[10px] px-2 py-0.5 border border-neutral-400 text-neutral-500 uppercase">
                            {job.delivery_mode}
                          </span>
                        </div>
                        <div className="text-xs font-mono text-neutral-500 mt-1">
                          <span className="font-bold">{job.cron_expr}</span>
                          {job.model_override && <span className="ml-2">model: {job.model_override}</span>}
                        </div>
                      </div>
                      <div className="flex gap-2 shrink-0">
                        <button
                          onClick={() => startEdit(job)}
                          disabled={loading}
                          className="px-3 py-1 bg-neutral-200 text-brutal-black border-2 border-brutal-black font-bold text-xs uppercase hover:bg-neutral-300 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleTrigger(job)}
                          disabled={loading}
                          className="px-3 py-1 bg-brutal-blue text-white border-2 border-brutal-black font-bold text-xs uppercase hover:brightness-110 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                        >
                          Run
                        </button>
                        <button
                          onClick={() => handleDelete(job)}
                          disabled={loading}
                          className="px-3 py-1 bg-brutal-red text-white border-2 border-brutal-black font-bold text-xs uppercase hover:bg-red-600 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                        >
                          Remove
                        </button>
                      </div>
                    </div>

                    {/* Run details */}
                    <div className="text-xs text-neutral-500 mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
                      <div>Last run: {formatDate(job.last_run_at)}</div>
                      <div>Next run: {formatDate(job.next_run_at)}</div>
                      {job.last_result && (
                        <div className="col-span-2 truncate" title={job.last_result}>
                          Result: {job.last_result.substring(0, 120)}{job.last_result.length > 120 ? '...' : ''}
                        </div>
                      )}
                      {job.last_error && (
                        <div className="col-span-2 text-red-600 truncate" title={job.last_error}>
                          Error: {job.last_error}
                        </div>
                      )}
                    </div>

                    {/* Prompt preview */}
                    <div className="mt-2 text-xs font-mono text-neutral-400 truncate" title={job.prompt}>
                      {job.prompt.substring(0, 150)}{job.prompt.length > 150 ? '...' : ''}
                    </div>

                    {/* History toggle */}
                    <button
                      onClick={() => toggleHistory(job.id)}
                      className="mt-2 text-[10px] font-bold uppercase text-neutral-400 hover:text-neutral-600 transition-colors"
                    >
                      {historyJobId === job.id ? 'Hide History' : 'Show History'}
                    </button>

                    {historyJobId === job.id && (
                      <div className="mt-2 border-t border-neutral-200 pt-2">
                        {historyRuns.length === 0 ? (
                          <div className="text-xs text-neutral-400">No run history yet.</div>
                        ) : (
                          <div className="space-y-1">
                            {historyRuns.map(run => (
                              <div key={run.id} className="text-xs flex items-start gap-2">
                                <span className={`font-bold ${run.status === 'success' ? 'text-green-600' : run.status === 'error' ? 'text-red-600' : 'text-yellow-600'}`}>
                                  {run.status === 'success' ? '+' : run.status === 'error' ? 'x' : '~'}
                                </span>
                                <span className="text-neutral-500 shrink-0">{formatDate(run.started_at)}</span>
                                <span className="text-neutral-400 truncate" title={run.result || run.error || ''}>
                                  {run.error ? `ERROR: ${run.error.substring(0, 80)}` : run.result ? run.result.substring(0, 80) : ''}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
