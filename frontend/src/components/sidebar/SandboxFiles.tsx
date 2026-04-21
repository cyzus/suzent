import React, { useState, useEffect, useCallback } from 'react';
import { getApiBase } from '../../lib/api';
import { useI18n } from '../../i18n';
import { BrutalButton } from '../BrutalButton';
import { useChatStore } from '../../hooks/useChatStore';
import { FilePreview } from './FilePreview';
import { isBinaryServedFile, isImageFile, isMarkdownFile, isCodeFile } from '../../lib/fileUtils';
import {
    FolderIcon,
    FolderOpenIcon,
    DocumentIcon,
    ChevronLeftIcon,
    ChevronRightIcon,
    ChevronDownIcon,
    ArrowPathIcon,
    DocumentTextIcon,
    CodeBracketIcon,
    PhotoIcon,
    ArrowUpTrayIcon,
    ArrowsPointingOutIcon,
    ArrowTopRightOnSquareIcon
} from '@heroicons/react/24/outline';

interface FileItem {
    name: string;
    is_dir: boolean;
    size: number;
    mtime: number;
}

interface FileListResponse {
    path: string;
    items: FileItem[];
    error?: string;
}

interface SandboxFilesProps {
    onViewModeChange?: (isViewingFile: boolean) => void;
    externalFilePath?: string | null;
    externalFileName?: string | null;
    onMaximize?: (filePath: string, fileName: string) => void;
}

const ROOT_PATH = '/';

interface FileTreeNodeProps {
    path: string;
    name: string;
    isDir: boolean;
    depth: number;
    size: number;
    expandedDirs: Set<string>;
    dirContents: Map<string, FileItem[]>;
    loadingDirs: Set<string>;
    selectedFile: string | null;
    onToggleDir: (path: string) => void;
    onSelectFile: (path: string, name: string) => void;
    formatSize: (bytes: number) => string;
}

const FileTreeNode: React.FC<FileTreeNodeProps> = ({
    path, name, isDir, depth, size,
    expandedDirs, dirContents, loadingDirs, selectedFile,
    onToggleDir, onSelectFile, formatSize,
}) => {
    const isExpanded = isDir && expandedDirs.has(path);
    const isLoading = isDir && loadingDirs.has(path);
    const isSelected = !isDir && selectedFile === path;
    const children = dirContents.get(path) || [];

    const getIcon = () => {
        const cls = "w-3.5 h-3.5 shrink-0 stroke-2";
        if (isDir) {
            return isExpanded
                ? <FolderOpenIcon className={`${cls} text-brutal-yellow`} />
                : <FolderIcon className={`${cls} dark:text-zinc-300`} />;
        }
        if (isImageFile(name)) return <PhotoIcon className={`${cls} text-brutal-blue`} />;
        if (isMarkdownFile(name) || name.endsWith('.txt') || name.endsWith('.log'))
            return <DocumentTextIcon className={`${cls} text-brutal-green`} />;
        if (isCodeFile(name)) return <CodeBracketIcon className={`${cls} text-brutal-blue`} />;
        return <DocumentIcon className={`${cls} text-neutral-400 dark:text-zinc-500`} />;
    };

    return (
        <div>
            <button
                onClick={() => isDir ? onToggleDir(path) : onSelectFile(path, name)}
                title={path}
                className={`
                    w-full flex items-center gap-1.5 py-[3px] pr-2 text-left
                    font-mono text-xs transition-colors duration-75
                    ${isSelected
                        ? 'bg-brutal-yellow text-brutal-black border-l-2 border-brutal-black'
                        : 'border-l-2 border-transparent hover:bg-neutral-100 dark:hover:bg-zinc-700/60 dark:text-zinc-200'
                    }
                `}
                style={{ paddingLeft: `${depth * 10 + 4}px` }}
            >
                <span className="w-3 h-3 flex items-center justify-center shrink-0">
                    {isDir && (
                        isLoading
                            ? <span className="w-2.5 h-2.5 border border-current border-t-transparent rounded-full animate-spin block" />
                            : isExpanded
                                ? <ChevronDownIcon className="w-2.5 h-2.5 stroke-[3]" />
                                : <ChevronRightIcon className="w-2.5 h-2.5 stroke-[3]" />
                    )}
                </span>

                {getIcon()}

                <span className={`flex-1 truncate ml-0.5 ${isDir ? 'font-bold' : ''}`}>
                    {name}{isDir ? '/' : ''}
                </span>

                {!isDir && size > 0 && (
                    <span className="text-[9px] text-neutral-400 dark:text-zinc-500 shrink-0 tabular-nums">
                        {formatSize(size)}
                    </span>
                )}
            </button>

            {isDir && isExpanded && (
                <div>
                    {children.length === 0 && !isLoading ? (
                        <div className="text-[9px] font-mono text-neutral-400 dark:text-zinc-600 py-0.5 pl-3 italic">
                            empty
                        </div>
                    ) : (
                        children.map((child, idx) => (
                            <FileTreeNode
                                key={idx}
                                path={`${path}/${child.name}`}
                                name={child.name}
                                isDir={child.is_dir}
                                depth={depth + 1}
                                size={child.size}
                                expandedDirs={expandedDirs}
                                dirContents={dirContents}
                                loadingDirs={loadingDirs}
                                selectedFile={selectedFile}
                                onToggleDir={onToggleDir}
                                onSelectFile={onSelectFile}
                                formatSize={formatSize}
                            />
                        ))
                    )}
                </div>
            )}
        </div>
    );
};

export const SandboxFiles: React.FC<SandboxFilesProps> = ({
    onViewModeChange,
    externalFilePath,
    externalFileName,
    onMaximize
}) => {
    const { t } = useI18n();
    const { currentChatId, config } = useChatStore();

    const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set([ROOT_PATH]));
    const [dirContents, setDirContents] = useState<Map<string, FileItem[]>>(new Map());
    const [loadingDirs, setLoadingDirs] = useState<Set<string>>(new Set());

    const [selectedFile, setSelectedFile] = useState<string | null>(null);
    const [fileContent, setFileContent] = useState<string | null>(null);
    const [loadingFile, setLoadingFile] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchDirContents = useCallback(async (path: string) => {
        if (!currentChatId) return;

        setLoadingDirs(prev => { const s = new Set(prev); s.add(path); return s; });
        try {
            const base = getApiBase();
            const volumesParam = JSON.stringify(config.sandbox_volumes || []);
            const res = await fetch(`${base}/sandbox/files?chat_id=${currentChatId}&path=${encodeURIComponent(path)}&volumes=${encodeURIComponent(volumesParam)}`);
            if (!res.ok) return;
            const data: FileListResponse = await res.json();
            if (!data.error) {
                setDirContents(prev => new Map(prev).set(path, data.items || []));
            }
        } catch {
            // silent - tree just won't expand
        } finally {
            setLoadingDirs(prev => { const s = new Set(prev); s.delete(path); return s; });
        }
    }, [currentChatId, config.sandbox_volumes]);

    useEffect(() => {
        if (currentChatId) {
            setExpandedDirs(new Set([ROOT_PATH]));
            setDirContents(new Map());
            setSelectedFile(null);
            setFileContent(null);
            setError(null);
            fetchDirContents(ROOT_PATH);
        }
    }, [currentChatId]);

    const handleToggleDir = useCallback((path: string) => {
        if (expandedDirs.has(path)) {
            setExpandedDirs(prev => { const s = new Set(prev); s.delete(path); return s; });
        } else {
            setExpandedDirs(prev => new Set(prev).add(path));
            if (!dirContents.has(path)) {
                fetchDirContents(path);
            }
        }
    }, [expandedDirs, dirContents, fetchDirContents]);

    const handleRefresh = useCallback(() => {
        setDirContents(new Map());
        setExpandedDirs(new Set([ROOT_PATH]));
        fetchDirContents(ROOT_PATH);
    }, [fetchDirContents]);

    const fetchFileContent = useCallback(async (path: string) => {
        if (!currentChatId) return;

        setLoadingFile(true);
        setError(null);
        try {
            const base = getApiBase();
            const volumesParam = JSON.stringify(config.sandbox_volumes || []);
            const response = await fetch(`${base}/sandbox/read_file?chat_id=${currentChatId}&path=${encodeURIComponent(path)}&volumes=${encodeURIComponent(volumesParam)}`);
            if (!response.ok) {
                setError(`Server error: ${response.status}`);
                return;
            }
            const data = await response.json();
            if (data.error) setError(data.error);
            else setFileContent(data.content);
        } catch {
            setError("Failed to fetch file content");
        } finally {
            setLoadingFile(false);
        }
    }, [currentChatId, config.sandbox_volumes]);

    const handleSelectFile = useCallback((path: string, name: string) => {
        setSelectedFile(path);
        setError(null);
        setFileContent(null);
        if (!isBinaryServedFile(name)) {
            fetchFileContent(path);
        }
        onViewModeChange?.(true);
    }, [fetchFileContent, onViewModeChange]);

    const handleBack = () => {
        setSelectedFile(null);
        setFileContent(null);
        setError(null);
        onViewModeChange?.(false);
    };

    useEffect(() => {
        if (externalFilePath && externalFileName) {
            setSelectedFile(externalFilePath);
            setError(null);
            setFileContent(null);
            if (!isBinaryServedFile(externalFileName)) {
                fetchFileContent(externalFilePath);
            }
            onViewModeChange?.(true);
        }
    }, [externalFilePath, externalFileName, fetchFileContent, onViewModeChange]);

    const openRootInExplorer = async () => {
        if (!currentChatId) return;
        try {
            await fetch(`${getApiBase()}/system/open_explorer`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: '/persistence', chat_id: currentChatId })
            });
        } catch (e) {
            console.error("Failed to open explorer", e);
        }
    };

    const handleUploadClick = () => {
        document.getElementById('sandbox-file-upload')?.click();
    };

    const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const files = event.target.files;
        if (!files || files.length === 0 || !currentChatId) return;

        setError(null);
        try {
            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                const cleanName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
                const targetPath = `/persistence/${cleanName}`;
                const text = await file.text();
                const base = getApiBase();
                const volumesParam = JSON.stringify(config.sandbox_volumes || []);
                const res = await fetch(`${base}/sandbox/file?chat_id=${currentChatId}&volumes=${encodeURIComponent(volumesParam)}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: targetPath, content: text })
                });
                if (!res.ok) {
                    const data = await res.json();
                    throw new Error(data.error || `Failed to upload ${file.name}`);
                }
            }
            fetchDirContents(ROOT_PATH);
        } catch (err) {
            setError(String(err));
        } finally {
            event.target.value = '';
        }
    };

    const formatSize = (bytes: number) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    };

    if (!currentChatId) {
        return <div className="text-xs font-mono p-4 text-center border-2 border-brutal-black m-2 bg-brutal-yellow">{t('sandbox.selectChat')}</div>;
    }

    // File Content View
    if (selectedFile) {
        const filename = selectedFile.split('/').pop() || selectedFile;

        return (
            <div className="flex flex-col h-full bg-white dark:bg-zinc-900">
                <div className="flex items-center gap-3 p-3 border-b-3 border-brutal-black bg-white dark:bg-zinc-800 shrink-0 sticky top-0 z-20 shadow-[0_2px_0_0_rgba(0,0,0,1)]">
                    <BrutalButton onClick={handleBack} title={t('sandbox.back')} size="icon">
                        <ChevronLeftIcon className="w-5 h-5 stroke-2" />
                    </BrutalButton>
                    <div className="bg-white dark:bg-zinc-700 border-2 border-brutal-black px-3 py-1.5 flex-1 min-w-0 shadow-[2px_2px_0_0_#000]">
                        <span className="font-bold text-xs truncate block font-mono uppercase tracking-wider dark:text-white">
                            {filename}
                        </span>
                    </div>
                    <BrutalButton
                        size="icon"
                        onClick={() => {
                            setFileContent(null);
                            setError(null);
                            if (!isBinaryServedFile(filename)) fetchFileContent(selectedFile);
                        }}
                        title={t('sandbox.refresh')}
                        className={loadingFile ? 'animate-spin' : ''}
                    >
                        <ArrowPathIcon className="w-4 h-4 stroke-2" />
                    </BrutalButton>
                    {onMaximize && (
                        <BrutalButton
                            variant="warning"
                            size="icon"
                            onClick={() => onMaximize(selectedFile, filename)}
                            title={t('sandbox.maximize')}
                        >
                            <ArrowsPointingOutIcon className="w-5 h-5 stroke-2" />
                        </BrutalButton>
                    )}
                </div>

                <div className="flex-1 overflow-auto p-4 relative bg-white dark:bg-zinc-900">
                    {loadingFile ? (
                        <div className="flex items-center justify-center h-full">
                            <div className="animate-spin w-8 h-8 border-4 border-brutal-black border-t-neutral-400 rounded-full"></div>
                        </div>
                    ) : error ? (
                        <div className="p-4 bg-red-100 border-2 border-brutal-black text-red-700 text-xs font-bold font-mono">
                            {t('sandbox.errorPrefix')}{error}
                        </div>
                    ) : (
                        <div className="h-full">
                            <FilePreview
                                filename={filename}
                                content={fileContent}
                                chatId={currentChatId}
                                path={selectedFile}
                            />
                        </div>
                    )}
                </div>
            </div>
        );
    }

    // Tree View
    const isRootLoading = loadingDirs.has(ROOT_PATH);
    const totalItems = Array.from(dirContents.values()).reduce((acc, items) => acc + items.length, 0);

    return (
        <div className="flex flex-col h-full bg-white dark:bg-zinc-900">
            {/* Toolbar */}
            <div className="bg-white dark:bg-zinc-800 p-2 border-b-3 border-brutal-black flex items-center gap-2 shrink-0">
                <BrutalButton
                    onClick={handleRefresh}
                    className={isRootLoading ? 'animate-spin' : ''}
                    title={t('sandbox.refresh')}
                    size="icon"
                >
                    <ArrowPathIcon className="w-4 h-4 stroke-2" />
                </BrutalButton>
                <BrutalButton onClick={openRootInExplorer} title={t('sandbox.openInExplorer')} size="icon">
                    <ArrowTopRightOnSquareIcon className="w-4 h-4 stroke-2" />
                </BrutalButton>
                <BrutalButton onClick={handleUploadClick} title={t('sandbox.uploadFile')} size="icon">
                    <ArrowUpTrayIcon className="w-4 h-4 stroke-2" />
                </BrutalButton>
                <input
                    type="file"
                    id="sandbox-file-upload"
                    className="hidden"
                    onChange={handleFileChange}
                    multiple
                />
                <div className="flex-1 overflow-hidden">
                    <div className="text-[10px] font-mono font-bold truncate px-2 py-1 bg-neutral-100 dark:bg-zinc-700 border-2 border-brutal-black dark:text-white shadow-[2px_2px_0_0_#000] uppercase tracking-wider">
                        Sandbox
                    </div>
                </div>
            </div>

            {/* Tree */}
            <div className="flex-1 overflow-y-auto bg-white dark:bg-zinc-900 py-1 scrollbar-thin scrollbar-track-neutral-200 dark:scrollbar-track-zinc-700 scrollbar-thumb-brutal-black">
                {isRootLoading && !dirContents.has(ROOT_PATH) ? (
                    <div className="flex flex-col items-center justify-center h-full opacity-50 space-y-4">
                        <div className="animate-spin w-8 h-8 border-4 border-brutal-black border-t-neutral-400 rounded-full"></div>
                        <span className="font-bold text-xs font-mono">{t('sandbox.scanning')}</span>
                    </div>
                ) : error ? (
                    <div className="p-3 bg-red-100 border-2 border-brutal-black text-red-600 text-xs font-mono m-2 shadow-[4px_4px_0_0_#000]">
                        {error}
                    </div>
                ) : (
                    (dirContents.get(ROOT_PATH) || []).map((item, idx) => (
                        <FileTreeNode
                            key={idx}
                            path={`/${item.name}`}
                            name={item.name}
                            isDir={item.is_dir}
                            depth={0}
                            size={item.size}
                            expandedDirs={expandedDirs}
                            dirContents={dirContents}
                            loadingDirs={loadingDirs}
                            selectedFile={selectedFile}
                            onToggleDir={handleToggleDir}
                            onSelectFile={handleSelectFile}
                            formatSize={formatSize}
                        />
                    ))
                )}
            </div>

            {/* Status Footer */}
            <div className="bg-white dark:bg-zinc-800 text-brutal-black dark:text-white p-2 flex justify-between items-center text-[10px] font-mono border-t-3 border-brutal-black select-none">
                <span className="font-bold tracking-wider">{t('sandbox.itemsCount', { count: String(totalItems) })}</span>
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-none border border-black ${loadingDirs.size > 0 ? 'bg-neutral-400 animate-pulse' : 'bg-brutal-green'}`}></div>
                    <span className="uppercase">{loadingDirs.size > 0 ? t('sandbox.status.syncing') : t('sandbox.status.ready')}</span>
                </div>
            </div>
        </div>
    );
};
