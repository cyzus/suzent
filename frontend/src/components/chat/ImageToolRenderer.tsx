import React, { useState } from 'react';
import { getApiBase, getSandboxParams } from '../../lib/api';
import { useChatStore } from '../../hooks/useChatStore';
import { useI18n } from '../../i18n';
import { MarkdownRenderer } from './MarkdownRenderer';
import type { ToolRendererProps } from './ToolCallBlock';

export function getImageToolPaths({ toolName, parsedArgs, metadata }: ToolRendererProps): string[] {
  const paths =
    toolName === 'generate_image'
      ? metadata?.saved_paths
      : [metadata?.image_path ?? parsedArgs?.image_path];
  return Array.isArray(paths)
    ? [
        ...new Set(
          paths.filter((path): path is string => typeof path === 'string' && !!path.trim())
        ),
      ]
    : [];
}

const ImagePreview: React.FC<{ src: string; path: string }> = ({ src, path }) => {
  const [failed, setFailed] = useState(false);
  const { t } = useI18n();
  const name = path.split(/[\\/]/).pop() || path;
  return (
    <a href={src} target="_blank" rel="noopener noreferrer" className="block min-w-0">
      {failed ? (
        <span className="text-xs text-neutral-500">{t('imageTool.previewFailed')}</span>
      ) : (
        <img
          src={src}
          alt={name}
          loading="lazy"
          onError={() => setFailed(true)}
          className="max-w-full max-h-80 object-contain rounded-sm border border-neutral-200 dark:border-zinc-700"
        />
      )}
      <span className="block mt-1 text-xs text-neutral-500 break-all">{name}</span>
    </a>
  );
};

export const ImageToolRenderer: React.FC<ToolRendererProps> = (props) => {
  const { currentChatId, config } = useChatStore();
  const paths = getImageToolPaths(props);
  return (
    <div className="space-y-3 min-w-0">
      {currentChatId && paths.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {paths.map((path) => {
            const src = `${getApiBase()}/sandbox/serve?${getSandboxParams(currentChatId, path, config.sandbox_volumes)}`;
            return <ImagePreview key={src} src={src} path={path} />;
          })}
        </div>
      )}
      {props.output && <MarkdownRenderer content={props.output} />}
    </div>
  );
};
