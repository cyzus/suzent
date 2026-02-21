import React, { useMemo } from 'react';
import { DocumentTextIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../i18n';

interface ClickableContentProps {
    content: string;
    onFileClick?: (filePath: string, fileName: string, shiftKey?: boolean) => void;
}

/**
 * Minimal fallback for clickable file paths in user messages.
 * Only detects absolute paths with extensions (e.g., /persistence/file.txt).
 * Agent messages should use markdown links with file:// protocol instead.
 */
export const ClickableContent: React.FC<ClickableContentProps> = ({ content, onFileClick }) => {
    const { t } = useI18n();
    const segments = useMemo(() => {
        if (!content || !onFileClick) return [];

        // Minimal regex: only absolute paths with extensions
        // Example: /persistence/file.txt or /mnt/data/report.pdf
        // Uses lookbehind to ensure start of path isn't part of a URL (e.g. https://)
        const pathRegex = /(?<![:/])\/(?!\/)[\w\-./]+\.\w{2,5}\b/g;

        const parts: Array<{ type: 'text' | 'path'; value: string; path: string }> = [];
        let lastIndex = 0;
        let match;

        while ((match = pathRegex.exec(content)) !== null) {
            // Add text before the path
            if (match.index > lastIndex) {
                parts.push({
                    type: 'text',
                    value: content.slice(lastIndex, match.index),
                    path: ''
                });
            }

            // Add the path
            parts.push({
                type: 'path',
                value: match[0],
                path: match[0]
            });

            lastIndex = match.index + match[0].length;
        }

        // Add remaining text
        if (lastIndex < content.length) {
            parts.push({
                type: 'text',
                value: content.slice(lastIndex),
                path: ''
            });
        }

        return parts;
    }, [content, onFileClick]);

    if (segments.length === 0) {
        return <>{content}</>;
    }

    return (
        <>
            {segments.map((segment, idx) => {
                if (segment.type === 'text') {
                    return <React.Fragment key={idx}>{segment.value}</React.Fragment>;
                } else {
                    const fileName = segment.path.split('/').pop() || segment.path;

                    return (
                        <button
                            key={idx}
                            type="button"
                            onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                onFileClick?.(segment.path, fileName, e.shiftKey);
                            }}
                            className="inline-flex items-center gap-1 bg-brutal-yellow border-2 border-brutal-black px-2 py-0.5 font-mono text-xs font-bold text-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] brutal-btn cursor-pointer align-middle"
                            title={t('fileLink.clickToView', { path: segment.path })}
                        >
                            <DocumentTextIcon className="w-3 h-3 stroke-[3]" />
                            <span className="break-all">{segment.path}</span>
                        </button>
                    );
                }
            })}
        </>
    );
};
