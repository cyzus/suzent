import React, { useMemo } from 'react';
import { MarkdownRenderer, CodeBlock } from '../';

interface FilePreviewProps {
    filename: string;
    content: string | null;
    chatId: string;
    path: string;
}

export const FilePreview: React.FC<FilePreviewProps> = ({ filename, content, chatId, path }) => {
    const fileExt = useMemo(() => filename.split('.').pop()?.toLowerCase() || '', [filename]);

    // Construct raw serve URL
    // Use the wildcard route to ensure relative paths in HTML/CSS/JS work correctly
    const serveUrl = useMemo(() => {
        // Remove leading slash for clean URL construction
        const cleanPath = path.startsWith('/') ? path.slice(1) : path;
        return `/api/sandbox/serve/${chatId}/${cleanPath}`;
    }, [chatId, path]);

    // 1. Images
    if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(fileExt)) {
        return (
            <div className="flex items-center justify-center p-4 bg-neutral-100 min-h-[50%]">
                <img src={serveUrl} alt={filename} className="max-w-full max-h-full object-contain shadow-md border border-neutral-300" />
            </div>
        );
    }

    // 2. PDF
    if (fileExt === 'pdf') {
        return (
            <iframe
                src={serveUrl}
                className="w-full h-full border-none bg-white"
                title={filename}
            />
        );
    }

    // 3. HTML
    if (fileExt === 'html' || fileExt === 'htm') {
        return (
            <iframe
                src={serveUrl}
                className="w-full h-full border-none bg-white"
                title={filename}
                sandbox="allow-scripts allow-same-origin" // Relaxed sandbox for HTML previews to work reasonably well
            />
        );
    }

    // 4. Markdown
    if (fileExt === 'md') {
        return (
            <div className="prose prose-sm max-w-none p-2">
                <MarkdownRenderer content={content || ''} />
            </div>
        );
    }

    // 5. Mermaid (Basic integration attempt via CodeBlock or future hook)
    // For now, let's treat mermaid as a code block. 
    // Ideally we would want a specific mermaid renderer, but for this iteration, 
    // keeping it as text/code is a safe fallback if we don't have the lib ready.
    // However, the request asked for mermaid support.
    // Since we don't have a mermaid component handy in the plan without adding deps unpredictably (though mermaid is standard),
    // let's stick to CodeBlock for now but tag it 'mermaid', or if content is available, maybe we can try to render it?
    // Let's assume the user wants at least syntax highlighting for now or we could use an iframe to a simple wrapper if we had one.
    // Plan V1: Code block.
    if (fileExt === 'mermaid') {
        return (
            <div className="p-2">
                <CodeBlock
                    language="mermaid"
                    code={content || ''}
                />
            </div>
        );
    }

    // 6. Text / Code (JSX, TSX, PY, etc)
    // Improve TXT rendering: Not black text on black background (if that was the issue).
    // Our CodeBlock handles syntax highlighting using language inference.
    // For .txt, we should ensure it's legible.
    const isCode = ['js', 'jsx', 'ts', 'tsx', 'py', 'json', 'yml', 'yaml', 'css', 'xml', 'sh'].includes(fileExt);

    // Default fallback (includes .txt)
    return (
        <div className="p-0 h-full overflow-auto bg-white">
            <CodeBlock
                language={isCode ? fileExt : 'text'}
                code={content || ''}
            />
        </div>
    );
};
