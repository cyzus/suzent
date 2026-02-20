import React, { useEffect, useState } from 'react';
import { XMarkIcon, ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline';
import { BrutalButton } from './BrutalButton';
import { FilePreview } from './sidebar/FilePreview';
import { isBinaryServedFile } from '../lib/fileUtils';
import { useI18n } from '../i18n';

interface FileViewerProps {
    filePath: string | null;
    fileName: string | null;
    chatId: string | null;
    onClose: () => void;
}

import { API_BASE } from '../lib/api';

export const FileViewer: React.FC<FileViewerProps> = ({ filePath, fileName, chatId, onClose }) => {
    const { t } = useI18n();
    const [fileContent, setFileContent] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                onClose();
            }
        };

        if (filePath) {
            window.addEventListener('keydown', handleKeyDown);
            fetchFileContent();
        }

        return () => {
            window.removeEventListener('keydown', handleKeyDown);
        };
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

            const response = await fetch(`${API_BASE}/sandbox/read_file?chat_id=${chatId}&path=${encodeURIComponent(filePath)}`);
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
            await fetch(`${API_BASE}/system/open_explorer`, {
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
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-brutal-black/80 backdrop-blur-sm p-4"
            onClick={onClose}
        >
            <div
                className="relative w-full max-w-6xl h-[90vh] bg-white border-4 border-brutal-black shadow-brutal-xl flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b-4 border-brutal-black bg-brutal-yellow shrink-0">
                    <h2 className="text-lg font-bold text-brutal-black truncate font-mono uppercase tracking-wider">
                        {fileName || t('fileViewer.title')}
                    </h2>
                    <div className="flex gap-2">
                        <BrutalButton
                            variant="primary"
                            size="icon"
                            onClick={openInExplorer}
                            title={t('fileViewer.revealInExplorer')}
                        >
                            <ArrowTopRightOnSquareIcon className="w-5 h-5" />
                        </BrutalButton>
                        <BrutalButton
                            variant="danger"
                            size="icon"
                            onClick={onClose}
                            title={t('fileViewer.closeEsc')}
                        >
                            <XMarkIcon className="w-5 h-5" />
                        </BrutalButton>
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-auto bg-white">
                    {loading ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="animate-spin w-12 h-12 border-4 border-brutal-black border-t-neutral-400 rounded-full"></div>
                        </div>
                    ) : error ? (
                        <div className="p-8 m-8 bg-brutal-red/10 border-3 border-brutal-red text-brutal-red text-sm font-bold font-mono">
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
            </div>
        </div>
    );
};
