import React, { useMemo } from 'react';
import { MarkdownRenderer, CodeBlock, MermaidDiagram } from '../';
import {
    isImageFile,
    isPdfFile,
    isHtmlFile,
    isMarkdownFile,
    isMermaidFile,
    getLanguageForFile
} from '../../lib/fileUtils';
import { getApiBase, getSandboxParams } from '../../lib/api';
import { useChatStore } from '../../hooks/useChatStore';

interface FilePreviewProps {
    filename: string;
    content: string | null;
    chatId: string;
    path: string;
}

export const FilePreview: React.FC<FilePreviewProps> = ({ filename, content, chatId, path }) => {
    const { config } = useChatStore();

    // Construct raw serve URL
    // Use the wildcard route to ensure relative paths in HTML/CSS/JS work correctly
    const serveUrl = useMemo(() => {
        // Remove leading slash for clean URL construction
        const cleanPath = path.startsWith('/') ? path.slice(1) : path;

        // Get volume params only (empty chat_id/path as they are in the route)
        const params = getSandboxParams('', '', config.sandbox_volumes);
        const queryPart = params ? `?${params}` : '';

        return `${getApiBase()}/sandbox/serve/${chatId}/${cleanPath}${queryPart}`;
    }, [chatId, path, config.sandbox_volumes]);

    // 1. Images
    if (isImageFile(filename)) {
        return (
            <div className="flex items-center justify-center p-8 bg-neutral-50 dark:bg-zinc-900/50 h-full w-full">
                <img src={serveUrl} alt={filename} className="max-w-full max-h-full object-contain drop-shadow-md rounded-sm" />
            </div>
        );
    }

    // 2. PDF
    if (isPdfFile(filename)) {
        return (
            <iframe
                src={serveUrl}
                className="w-full h-full border-none bg-white"
                title={filename}
            />
        );
    }

    // 3. HTML
    if (isHtmlFile(filename)) {
        return (
            <iframe
                src={serveUrl}
                className="w-full h-full border-none bg-white"
                title={filename}
                sandbox="allow-scripts allow-same-origin"
            />
        );
    }

    // 4. Markdown
    if (isMarkdownFile(filename)) {
        return (
            <div className="prose prose-sm max-w-none p-2">
                <MarkdownRenderer content={content || ''} />
            </div>
        );
    }

    // 5. Mermaid
    if (isMermaidFile(filename)) {
        return (
            <div className="p-2 overflow-auto h-full">
                <MermaidDiagram code={content || ''} />
            </div>
        );
    }

    // 6. Text / Code - Default fallback
    return (
        <div className="p-0 h-full overflow-auto bg-white">
            <CodeBlock
                language={getLanguageForFile(filename)}
                code={content || ''}
            />
        </div>
    );
};
