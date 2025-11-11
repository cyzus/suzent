/**
 * Core Memory Block Editor Component
 * Displays and allows editing of individual core memory blocks
 */

import React, { useState, useEffect } from 'react';
import type { CoreMemoryLabel } from '../../types/memory';

interface CoreMemoryBlockProps {
  label: CoreMemoryLabel;
  content: string;
  onUpdate: (label: CoreMemoryLabel, content: string) => Promise<void>;
  maxLength?: number;
}

const LABELS: Record<CoreMemoryLabel, { title: string; description: string }> = {
  persona: {
    title: 'Persona',
    description: 'Your identity, role, and capabilities',
  },
  user: {
    title: 'User',
    description: 'Information about the current user',
  },
  facts: {
    title: 'Facts',
    description: 'Key facts to always remember',
  },
  context: {
    title: 'Context',
    description: 'Current session context and goals',
  },
};

export const CoreMemoryBlock: React.FC<CoreMemoryBlockProps> = ({
  label,
  content,
  onUpdate,
  maxLength = 2048,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(content);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setEditContent(content);
  }, [content]);

  const handleSave = async () => {
    if (editContent === content) {
      setIsEditing(false);
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      await onUpdate(label, editContent);
      setIsEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setEditContent(content);
    setIsEditing(false);
    setError(null);
  };

  const { title, description } = LABELS[label];
  const characterCount = editContent.length;
  const isOverLimit = characterCount > maxLength;

  return (
    <div className="border-3 border-brutal-black bg-white shadow-[4px_4px_0_0_#000000] rounded-none p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-brutal text-lg uppercase tracking-tight text-brutal-black">
            {title}
          </h3>
          <p className="text-sm text-neutral-600 mt-1">{description}</p>
        </div>
        <div className="flex gap-2">
          {!isEditing ? (
            <button
              onClick={() => setIsEditing(true)}
              className="px-3 py-1 border-2 border-brutal-black bg-white hover:bg-neutral-100 active:translate-x-[2px] active:translate-y-[2px] active:shadow-none shadow-[2px_2px_0_0_#000000] font-bold text-xs uppercase transition-all"
            >
              Edit
            </button>
          ) : (
            <>
              <button
                onClick={handleCancel}
                disabled={isSaving}
                className="px-3 py-1 border-2 border-brutal-black bg-white hover:bg-neutral-100 active:translate-x-[2px] active:translate-y-[2px] active:shadow-none shadow-[2px_2px_0_0_#000000] font-bold text-xs uppercase transition-all disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving || isOverLimit}
                className="px-3 py-1 border-2 border-brutal-black bg-brutal-black text-brutal-white hover:bg-neutral-800 active:translate-x-[2px] active:translate-y-[2px] active:shadow-none shadow-[2px_2px_0_0_#000000] font-bold text-xs uppercase transition-all disabled:opacity-50"
              >
                {isSaving ? 'Saving...' : 'Save'}
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-3 p-2 border-2 border-red-500 bg-red-50 text-red-700 text-sm">
          {error}
        </div>
      )}

      {isEditing ? (
        <div>
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            className={`w-full min-h-[120px] p-3 border-3 border-brutal-black rounded-none font-sans text-sm resize-y focus:outline-none focus:ring-4 focus:ring-brutal-black ${
              isOverLimit ? 'border-red-500' : ''
            }`}
            style={{ backgroundColor: '#ffffff', color: '#000000' }}
            placeholder={`Enter ${title.toLowerCase()}...`}
          />
          <div
            className={`text-xs text-right mt-1 ${
              isOverLimit ? 'text-red-600 font-bold' : 'text-neutral-500'
            }`}
          >
            {characterCount} / {maxLength} characters
            {isOverLimit && ' (over limit!)'}
          </div>
        </div>
      ) : (
        <div className="prose prose-sm max-w-none">
          <pre
            className="whitespace-pre-wrap font-sans text-sm p-3 border-3 border-brutal-black rounded-none"
            style={{ backgroundColor: '#ffffff', color: '#000000' }}
          >
            {content || <span className="text-neutral-400 italic">No content yet</span>}
          </pre>
        </div>
      )}
    </div>
  );
};
