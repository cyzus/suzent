/**
 * Daily Logs Panel Component
 * Displays daily memory log dates and their markdown content
 */

import { useState, useEffect } from 'react';
import { memoryApi } from '../../lib/memoryApi';
import { useI18n } from '../../i18n';

function formatDateLabel(dateStr: string, t: (key: string, params?: Record<string, string>) => string): string {
  try {
    const date = new Date(dateStr + 'T00:00:00');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diff = Math.floor((today.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

    if (diff === 0) return t('dailyLogs.today');
    if (diff === 1) return t('dailyLogs.yesterday');
    if (diff < 7) return t('dailyLogs.daysAgo', { count: String(diff) });

    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

function LogContentArea({ loading, error, content }: {
  loading: boolean;
  error: string | null;
  content: string | null;
}): JSX.Element | null {
  const { t } = useI18n();
  if (loading) {
    return (
      <div className="border-3 border-brutal-black bg-white p-8 text-center">
        <div className="w-4 h-4 border-3 border-brutal-black border-t-transparent animate-spin rounded-full mx-auto mb-2"></div>
        <p className="text-sm font-bold uppercase">{t('dailyLogs.loading')}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="border-3 border-brutal-black bg-white p-6">
        <p className="text-sm text-brutal-black font-mono">{error}</p>
      </div>
    );
  }

  if (content) {
    return (
      <div className="border-3 border-brutal-black bg-white shadow-brutal">
        <pre className="whitespace-pre-wrap font-mono text-sm p-6 max-h-[65vh] overflow-y-auto scrollbar-thin leading-relaxed text-brutal-black">
          {content}
        </pre>
      </div>
    );
  }

  return null;
}

export const DailyLogsPanel: React.FC = () => {
  const { t } = useI18n();
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadLog = async (date: string) => {
    setSelectedDate(date);
    setLoading(true);
    setError(null);
    try {
      const result = await memoryApi.getDailyLog(date);
      setContent(result.content);
    } catch (err) {
      setContent(null);
      setError(err instanceof Error ? err.message : t('dailyLogs.loadLogFailed'));
    } finally {
      setLoading(false);
    }
  };

  const loadDates = async () => {
    setListLoading(true);
    setError(null);
    try {
      const result = await memoryApi.listDailyLogs();
      setDates(result.dates);
      if (result.dates.length > 0) {
        loadLog(result.dates[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('dailyLogs.loadDatesFailed'));
    } finally {
      setListLoading(false);
    }
  };

  useEffect(() => {
    loadDates();
  }, []);

  if (listLoading) {
    return (
      <div className="border-3 border-brutal-black bg-white p-6 shadow-brutal">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 border-3 border-brutal-black border-t-transparent animate-spin rounded-full"></div>
          <span className="font-bold uppercase text-sm">{t('dailyLogs.loading')}</span>
        </div>
      </div>
    );
  }

  if (error && dates.length === 0) {
    return (
      <div className="border-3 border-brutal-black bg-white p-6 shadow-brutal">
        <h3 className="font-brutal text-xl text-brutal-black mb-2 uppercase">{t('common.error')}</h3>
        <p className="text-sm text-brutal-black font-mono mb-4">{error}</p>
        <button
          onClick={loadDates}
          className="px-6 py-2 border-3 border-brutal-black bg-white hover:bg-neutral-100 font-bold uppercase shadow-[2px_2px_0_0_#000] brutal-btn transition-all"
        >
          {t('common.retry')}
        </button>
      </div>
    );
  }

  if (dates.length === 0) {
    return (
      <div className="border-3 border-brutal-black bg-white p-12 text-center shadow-brutal">
        <h4 className="font-brutal text-2xl uppercase mb-2">{t('dailyLogs.emptyTitle')}</h4>
        <p className="text-neutral-600 text-sm max-w-md mx-auto">
          {t('dailyLogs.emptyDesc')}
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* Date List */}
      <div className="lg:col-span-3 space-y-2">
        <div className="bg-brutal-black text-white p-3 border-3 border-brutal-black">
          <h3 className="font-brutal text-lg uppercase tracking-tight">{t('dailyLogs.title')}</h3>
          <p className="text-xs text-neutral-300 font-mono">{t('dailyLogs.entries', { count: String(dates.length) })}</p>
        </div>
        <div className="border-3 border-brutal-black bg-white shadow-brutal max-h-[60vh] overflow-y-auto scrollbar-thin">
          {dates.map((date) => (
            <button
              key={date}
              onClick={() => loadLog(date)}
              className={`w-full text-left px-4 py-3 border-b-2 border-neutral-200 last:border-b-0 transition-colors ${
                selectedDate === date
                  ? 'bg-brutal-black text-white'
                  : 'bg-white hover:bg-neutral-50 text-brutal-black'
              }`}
            >
              <div className="font-mono text-sm font-bold">{date}</div>
              <div className="text-xs mt-0.5 opacity-70">{formatDateLabel(date, t)}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Log Content */}
      <div className="lg:col-span-9">
        {selectedDate && (
          <div className="space-y-4">
            <div className="flex items-center justify-between bg-white p-3 border-b-3 border-brutal-black">
              <div>
                <h3 className="font-brutal text-xl uppercase tracking-tight text-brutal-black">
                  {selectedDate}
                </h3>
                <p className="text-xs text-neutral-600 font-mono">
                  {formatDateLabel(selectedDate, t)}
                </p>
              </div>
              <button
                onClick={() => loadLog(selectedDate)}
                className="px-3 py-1 border-2 border-brutal-black bg-white hover:bg-neutral-100 font-bold text-xs uppercase shadow-[2px_2px_0_0_#000] brutal-btn transition-all"
              >
                Refresh
              </button>
            </div>

            <LogContentArea loading={loading} error={error} content={content} />
          </div>
        )}
      </div>
    </div>
  );
};
