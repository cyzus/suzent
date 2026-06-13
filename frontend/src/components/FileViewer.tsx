import React, { useEffect, useState } from 'react';
import { XMarkIcon, ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline';
import { BrutalButton } from './BrutalButton';
import { FilePreview } from './sidebar/FilePreview';
import { isBinaryServedFile } from '../lib/fileUtils';
import { useI18n } from '../i18n';
import { FullscreenOverlay } from './FullscreenOverlay';

interface FileViewerProps {
    filePath: string | null;
    fileName: string | null;
    chatId: string | null;
    onClose: () => void;
}

import { getApiBase } from '../lib/api';

export const FileViewer: React.FC<FileViewerProps> = ({ filePath, fileName, chatId, onClose }) => {
    const { t } = useI18n();
    const [fileContent, setFileContent] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (filePath) {
            fetchFileContent();
        }
    }, [filePath, onClose]);

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
                setError("Backend not ready");
                return;
            }
            const response = await fetch(`${base}/sandbox/read_file?chat_id=${chatId}&path=${encodeURIComponent(filePath)}`);
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
        } catch (err) {
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
                    chat_id: chatId
                })
            });
        } catch (e) {
            console.error("Failed to open explorer", e);
        }
    };

    if (!filePath || !chatId) return null;

    return (
        <FullscreenOverlay
            open={Boolean(filePath && chatId)}
            onClose={onClose}
            zIndexClassName="z-50"
            containerClassName="relative w-full max-w-5xl h-[85vh] bg-white dark:bg-zinc-900 border-[3px] border-brutal-black shadow-[6px_6px_0_0_#000] dark:shadow-[6px_6px_0_0_#fff] flex flex-col overflow-hidden"
        >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3 border-b-[3px] border-brutal-black bg-white dark:bg-zinc-800 shrink-0">
                <h2 className="text-sm font-bold text-neutral-700 dark:text-neutral-200 truncate font-mono">
                    {fileName || t('fileViewer.title')}
                </h2>
                <div className="flex gap-2">
                    <button
                        onClick={openInExplorer}
                        title={t('fileViewer.revealInExplorer')}
                        className="p-1 bg-brutal-blue text-white border-2 border-brutal-black hover:bg-blue-600"
                    >
                        <ArrowTopRightOnSquareIcon className="w-5 h-5 stroke-[2.5]" />
                    </button>
                    <button
                        onClick={onClose}
                        title={t('fileViewer.closeEsc')}
                        className="p-1 bg-brutal-red text-white border-2 border-brutal-black hover:bg-red-600"
                    >
                        <XMarkIcon className="w-5 h-5 stroke-[2.5]" />
                    </button>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto bg-white dark:bg-zinc-900">
                {loading ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="animate-spin w-8 h-8 border-2 border-neutral-300 border-t-brutal-blue rounded-full"></div>
                    </div>
                ) : error ? (
                    <div className="p-8 m-8 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-brutal-red dark:text-red-400 text-sm font-medium rounded">
                        {t('fileViewer.errorPrefix')}{error}
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
        </FullscreenOverlay>
    );
};
