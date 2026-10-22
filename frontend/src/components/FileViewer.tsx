import { BrutalIconButton } from './BrutalButton';
import { ExpandedSurfaceCard } from './ExpandedSurfaceCard';
import React, { useEffect, useState } from 'react';
import { ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline';
import { FilePreview } from './sidebar/FilePreview';
import { isBinaryServedFile } from '../lib/fileUtils';
import { useI18n } from '../i18n';
import { WorkspacePanel } from './WorkspacePanel';
import { useChatStore } from '../hooks/useChatStore';
import { getApiBase, getSandboxParams } from '../lib/api';

interface FileViewerProps {
  filePath: string | null;
  fileName: string | null;
  chatId: string | null;
  onClose: () => void;
  controlAnchor?: DOMRect;
}

export const FileViewer: React.FC<FileViewerProps> = ({
  filePath,
  fileName,
  chatId,
  onClose,
  controlAnchor,
}) => {
  const { t } = useI18n();
  const { config } = useChatStore();
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (filePath) {
      fetchFileContent();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filePath, chatId, fileName]);

  const fetchFileContent = async () => {
    if (!filePath || !chatId) return;

    setLoading(true);
    setError(null);
    setFileContent(null);

    try {
      // Skip content fetching for binary/served files
      if (fileName && isBinaryServedFile(fileName)) {
        // These files are served directly via iframe/img in FilePreview
        setLoading(false);
        return;
      }

      const base = getApiBase();
      if (!base) {
        setError('Backend not ready');
        return;
      }
      const params = getSandboxParams(chatId, filePath, config.sandbox_volumes);
      const response = await fetch(`${base}/sandbox/read_file?${params}`);
      if (!response.ok) {
        const text = await response.text();
        try {
          const data = JSON.parse(text);
          setError(data.error || `Server error: ${response.status}`);
        } catch {
          setError(`Server error: ${response.status}`);
        }
        return;
      }
      const data = await response.json();

      if (data.error) {
        setError(data.error);
      } else {
        setFileContent(data.content);
      }
    } catch {
      setError(t('fileViewer.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  const openInExplorer = async () => {
    if (!filePath) return;
    try {
      await fetch(`${getApiBase()}/system/open_explorer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: filePath,
          chat_id: chatId,
        }),
      });
    } catch (e) {
      console.error('Failed to open explorer', e);
    }
  };

  if (!filePath || !chatId) return null;

  return (
    <WorkspacePanel open={Boolean(filePath && chatId)} onClose={onClose}>
      <ExpandedSurfaceCard
        title={fileName || t('fileViewer.title')}
        dockedToolbar
        controlAnchor={controlAnchor}
        onShrink={onClose}
        actions={
          <BrutalIconButton onClick={openInExplorer} label={t('fileViewer.revealInExplorer')}>
            <ArrowTopRightOnSquareIcon className="w-4 h-4 stroke-2" />
          </BrutalIconButton>
        }
      >
        {/* Content */}
        <div className="min-h-0 flex-1 overflow-auto scrollbar-thin bg-white dark:bg-zinc-900">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="animate-spin w-8 h-8 border-2 border-neutral-300 border-t-brutal-blue rounded-full"></div>
            </div>
          ) : error ? (
            <div className="p-8 m-8 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-brutal-red dark:text-red-400 text-sm font-medium rounded">
              {t('fileViewer.errorPrefix')}
              {error}
            </div>
          ) : (
            <FilePreview
              filename={fileName || 'file'}
              content={fileContent}
              chatId={chatId}
              path={filePath}
            />
          )}
        </div>
      </ExpandedSurfaceCard>
    </WorkspacePanel>
  );
};
