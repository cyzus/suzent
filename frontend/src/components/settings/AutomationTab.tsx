import React, { useEffect, useState } from 'react';

import { useI18n } from '../../i18n';
import {
  CronJob,
  CronRun,
  fetchCronJobs,
  createCronJob,
  updateCronJob,
  deleteCronJob,
  triggerCronJob,
  fetchCronStatus,
  fetchCronJobRuns,
  fetchHeartbeatGlobalConfig,
  saveHeartbeatGlobalConfig,
} from '../../lib/api';
import { BrutalMultiSelect } from '../BrutalMultiSelect';
import { BrutalSelect } from '../BrutalSelect';

interface AutomationTabProps {
  models: string[];
  tools?: string[];
}

export function AutomationTab({ models, tools = [] }: AutomationTabProps): React.ReactElement {
  const { t } = useI18n();
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [status, setStatus] = useState<{ scheduler_running: boolean; total_jobs: number; active_jobs: number } | null>(null);
  const [loading, setLoading] = useState(false);

  // Global heartbeat allowed tools
  const [heartbeatAllowedTools, setHeartbeatAllowedTools] = useState<string[]>([]);
  const [useCustomHeartbeatTools, setUseCustomHeartbeatTools] = useState(false);

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
      const [jobList, statusData] = await Promise.all([
        fetchCronJobs(), fetchCronStatus()
      ]);
      setJobs(jobList);
      setStatus(statusData);
    } catch (e) {
      console.error('Failed to load automation data:', e);
    }
  };

  useEffect(() => {
    refresh();
    fetchHeartbeatGlobalConfig().then(cfg => {
      const allowed = cfg.allowed_tools || [];
      setHeartbeatAllowedTools(allowed);
      setUseCustomHeartbeatTools(allowed.length > 0);
    });
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
      alert(e.message || t('settings.automation.failedToCreateJob'));
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
      alert(e.message || t('settings.automation.failedToUpdateJob'));
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
    { value: '', label: t('settings.automation.defaultModel') },
    ...models.map(m => ({ value: m, label: m })),
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-4xl font-brutal font-black uppercase text-brutal-black dark:text-white">{t('settings.automation.title')}</h2>
      </div>

      {/* Status Card */}
      <div className="bg-white dark:bg-zinc-800 dark:text-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6 mb-6">
        <div className="flex items-start gap-4">
          <div className={`w-12 h-12 border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white ${status?.scheduler_running ? 'bg-brutal-green' : 'bg-neutral-400'}`}>
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <h3 className="text-xl font-bold uppercase">{t('settings.automation.schedulerStatusTitle')}</h3>
            <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
              {status?.scheduler_running ? (
                <span className="text-green-700 font-bold">{t('settings.automation.running')}</span>
              ) : (
                <span className="text-red-700 font-bold">{t('settings.automation.stopped')}</span>
              )}
              {status && ` \u2014 ${t('settings.automation.activeOfTotal', { active: String(status.active_jobs), total: String(status.total_jobs) })}`}
            </p>
          </div>
        </div>
      </div>



      {/* Heartbeat Tool Approvals */}
      {tools.length > 0 && (
        <div className="bg-white dark:bg-zinc-800 dark:text-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6 mb-6">
          <div className="flex items-start gap-4 mb-6">
            <div className="w-12 h-12 bg-brutal-green border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-brutal-black">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h3 className="text-xl font-bold uppercase">Heartbeat Tool Approvals</h3>
              <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
                Tools that are automatically approved when heartbeat runs. Leave on <strong>All Tools</strong> to approve everything, or pick <strong>Custom</strong> to restrict.
              </p>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setUseCustomHeartbeatTools(false);
                  setHeartbeatAllowedTools([]);
                  saveHeartbeatGlobalConfig({ allowed_tools: [] });
                }}
                className={`px-3 py-1 text-xs font-bold uppercase border-2 border-brutal-black transition-all ${!useCustomHeartbeatTools ? 'bg-brutal-black text-white' : 'bg-white dark:bg-zinc-700 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-600'}`}
              >
                All Tools
              </button>
              <button
                onClick={() => {
                  setUseCustomHeartbeatTools(true);
                }}
                className={`px-3 py-1 text-xs font-bold uppercase border-2 border-brutal-black transition-all ${useCustomHeartbeatTools ? 'bg-brutal-black text-white' : 'bg-white dark:bg-zinc-700 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-600'}`}
              >
                Custom
              </button>
            </div>
            {useCustomHeartbeatTools && (
              <BrutalMultiSelect
                variant="list"
                value={heartbeatAllowedTools}
                onChange={(newTools) => {
                  setHeartbeatAllowedTools(newTools);
                  saveHeartbeatGlobalConfig({ allowed_tools: newTools });
                }}
                options={tools
                  .filter(t => !['MemorySearchTool', 'MemoryBlockUpdateTool'].includes(t))
                  .map(t => ({
                    value: t,
                    label: t.replace(/Tool$/, '').replace(/([a-z])([A-Z])/g, '$1 $2').toUpperCase(),
                  }))
                }
                emptyMessage="No tools selected"
              />
            )}
          </div>
        </div>
      )}

      {/* Add Job Form */}
      <div className="bg-white dark:bg-zinc-800 dark:text-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6 mb-6">
        <div className="flex items-start gap-4 mb-6">
          <div className="w-12 h-12 bg-brutal-blue border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" /></svg>
          </div>
          <div>
            <h3 className="text-xl font-bold uppercase">{t('settings.automation.addNewJobTitle')}</h3>
            <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{t('settings.automation.addNewJobDesc')}</p>
          </div>
        </div>

        <div className="space-y-4">
          <div className="flex gap-2">
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder={t('settings.automation.jobNamePlaceholder')}
              className="flex-1 bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
            />
            <input
              value={cronExpr}
              onChange={e => setCronExpr(e.target.value)}
              placeholder={t('settings.automation.cronExprPlaceholder')}
              className="w-52 bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
            />
          </div>

          <textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder={t('settings.automation.promptPlaceholder')}
            rows={3}
            className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500 resize-y"
          />

          <div className="flex flex-wrap gap-4 items-center">
            <BrutalSelect
              value={deliveryMode}
              onChange={val => setDeliveryMode(val as 'announce' | 'none')}
              options={[
                { value: 'announce', label: t('settings.automation.announce') },
                { value: 'none', label: t('settings.automation.silent') },
              ]}
              label={t('settings.automation.delivery')}
              className="w-36"
            />

            <BrutalSelect
              value={modelOverride}
              onChange={setModelOverride}
              options={modelOptions}
              label={t('settings.automation.model')}
              className="w-48"
            />

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={isActive}
                onChange={e => setIsActive(e.target.checked)}
                className="w-5 h-5 border-2 border-brutal-black accent-brutal-black"
              />
              <span className="font-bold text-xs uppercase">{t('settings.automation.active')}</span>
            </label>
          </div>

          <button
            onClick={handleCreate}
            disabled={loading || !name.trim() || !cronExpr.trim() || !prompt.trim()}
            className="px-4 py-2 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-brutal-black hover:brightness-110 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
          >
            {loading ? t('settings.automation.creating') : t('settings.automation.addJob')}
          </button>
        </div>
      </div>

      {/* Job List */}
      <div className="bg-white dark:bg-zinc-800 dark:text-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6">
        <div className="flex items-start gap-4 mb-6">
          <div className="w-12 h-12 bg-black border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <div>
            <h3 className="text-xl font-bold uppercase">{t('settings.automation.scheduledJobsTitle')}</h3>
            <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{t('settings.automation.scheduledJobsDesc')}</p>
          </div>
        </div>

        {jobs.length === 0 ? (
          <div className="text-center py-8 text-neutral-500 dark:text-neutral-400 font-bold uppercase">
            {t('settings.automation.noCronJobs')}
          </div>
        ) : (
          <div className="space-y-3">
            {jobs.map(job => (
              <div
                key={job.id}
                className="bg-neutral-50 dark:bg-zinc-900 border-2 border-brutal-black p-4 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
              >
                {editingJobId === job.id ? (
                  /* Edit mode */
                  <div className="space-y-3">
                    <div className="flex gap-2">
                      <input
                        value={editFields.name || ''}
                        onChange={e => setEditFields({ ...editFields, name: e.target.value })}
                        placeholder={t('settings.automation.jobNamePlaceholder')}
                        className="flex-1 bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                      />
                      <input
                        value={editFields.cron_expr || ''}
                        onChange={e => setEditFields({ ...editFields, cron_expr: e.target.value })}
                        placeholder={t('settings.automation.cronExpression')}
                        className="w-52 bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                      />
                    </div>
                    <textarea
                      value={editFields.prompt || ''}
                      onChange={e => setEditFields({ ...editFields, prompt: e.target.value })}
                      rows={3}
                      className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500 resize-y"
                    />
                    <div className="flex flex-wrap gap-4 items-center">
                      <BrutalSelect
                        value={editFields.delivery_mode || 'announce'}
                        onChange={val => setEditFields({ ...editFields, delivery_mode: val as 'announce' | 'none' })}
                        options={[
                          { value: 'announce', label: t('settings.automation.announce') },
                          { value: 'none', label: t('settings.automation.silent') },
                        ]}
                        label={t('settings.automation.delivery')}
                        className="w-36"
                      />
                      <BrutalSelect
                        value={editFields.model_override || ''}
                        onChange={val => setEditFields({ ...editFields, model_override: val || null })}
                        options={modelOptions}
                        label={t('settings.automation.model')}
                        className="w-48"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={handleSaveEdit}
                        disabled={loading}
                        className="px-4 py-1.5 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                      >
                        {t('common.save')}
                      </button>
                      <button
                        onClick={cancelEdit}
                        className="px-4 py-1.5 bg-neutral-200 border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none"
                      >
                        {t('common.cancel')}
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
                          <span className="font-bold text-brutal-black dark:text-white">{job.name}</span>
                          <span className={`text-[10px] px-2 py-0.5 border-2 font-bold uppercase ${job.active ? 'border-brutal-black bg-brutal-green text-brutal-black' : 'border-brutal-black bg-neutral-200 text-brutal-black'}`}>
                            {job.active ? t('common.on') : t('common.off')}
                          </span>
                          <span className="text-[10px] px-2 py-0.5 border border-neutral-400 text-neutral-500 dark:text-neutral-400 uppercase">
                            {job.delivery_mode}
                          </span>
                        </div>
                        <div className="text-xs font-mono text-neutral-500 dark:text-neutral-400 mt-1">
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
                          {t('common.edit')}
                        </button>
                        <button
                          onClick={() => handleTrigger(job)}
                          disabled={loading}
                          className="px-3 py-1 bg-brutal-blue text-white border-2 border-brutal-black font-bold text-xs uppercase hover:brightness-110 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                        >
                          {t('settings.automation.run')}
                        </button>
                        <button
                          onClick={() => handleDelete(job)}
                          disabled={loading}
                          className="px-3 py-1 bg-brutal-red text-white border-2 border-brutal-black font-bold text-xs uppercase hover:bg-red-600 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
                        >
                          {t('common.remove')}
                        </button>
                      </div>
                    </div>

                    {/* Run details */}
                    <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
                      <div>Last run: {formatDate(job.last_run_at)}</div>
                      <div>{t('settings.automation.nextRun')} {formatDate(job.next_run_at)}</div>
                      {job.last_result && (
                        <div className="col-span-2 truncate" title={job.last_result}>
                          {t('settings.automation.result')} {job.last_result.substring(0, 120)}{job.last_result.length > 120 ? '...' : ''}
                        </div>
                      )}
                      {job.last_error && (
                        <div className="col-span-2 text-red-600 dark:text-red-400 truncate" title={job.last_error}>
                          {t('settings.automation.errorLabel')} {job.last_error}
                        </div>
                      )}
                    </div>

                    {/* Prompt preview */}
                    <div className="mt-2 text-xs font-mono text-neutral-400 dark:text-neutral-500 truncate" title={job.prompt}>
                      {job.prompt.substring(0, 150)}{job.prompt.length > 150 ? '...' : ''}
                    </div>

                    {/* History toggle */}
                    <button
                      onClick={() => toggleHistory(job.id)}
                      className="mt-2 text-[10px] font-bold uppercase text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                    >
                      {historyJobId === job.id ? t('settings.automation.hideHistory') : t('settings.automation.showHistory')}
                    </button>

                    {historyJobId === job.id && (
                      <div className="mt-2 border-t border-neutral-200 dark:border-zinc-700 pt-2">
                        {historyRuns.length === 0 ? (
                          <div className="text-xs text-neutral-400 dark:text-neutral-500">{t('settings.automation.noRunHistory')}</div>
                        ) : (
                          <div className="space-y-1">
                            {historyRuns.map(run => (
                              <div key={run.id} className="text-xs flex items-start gap-2">
                                <span className={`font-bold ${run.status === 'success' ? 'text-green-600' : run.status === 'error' ? 'text-red-600' : 'text-yellow-600'}`}>
                                  {run.status === 'success' ? '+' : run.status === 'error' ? 'x' : '~'}
                                </span>
                                <span className="text-neutral-500 dark:text-neutral-400 shrink-0">{formatDate(run.started_at)}</span>
                                <span className="text-neutral-400 dark:text-neutral-500 truncate" title={run.result || run.error || ''}>
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
