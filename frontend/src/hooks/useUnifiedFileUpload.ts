import { useState, useRef, useCallback, useEffect } from 'react';
import { listen } from '@tauri-apps/api/event';
import { readFile } from '@tauri-apps/plugin-fs';
import { FileAttachment, ImageAttachment } from '../types/api';
import { getApiBase } from '../lib/api'; // import { API_BASE } from '../lib/api';

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB per file
const MAX_TOTAL_SIZE = 100 * 1024 * 1024; // 100 MB total

interface UploadResult {
  fileMetadata: FileAttachment[];
  imagePreviews: ImageAttachment[];
}

export function useUnifiedFileUpload() {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const dragCounterRef = useRef(0);

  const validateFiles = useCallback((files: File[]): { valid: File[]; error?: string } => {
    const validFiles: File[] = [];
    let totalSize = 0;

    for (const file of files) {
      // Check individual file size
      if (file.size > MAX_FILE_SIZE) {
        return { valid: [], error: `File "${file.name}" exceeds 50 MB limit` };
      }

      totalSize += file.size;

      // Check total size
      if (totalSize > MAX_TOTAL_SIZE) {
        return { valid: [], error: 'Total file size exceeds 100 MB limit' };
      }

      validFiles.push(file);
    }

    return { valid: validFiles };
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const { valid, error: validationError } = validateFiles(files);

    if (validationError) {
      setError(validationError);
      return;
    }

    setSelectedFiles(prev => [...prev, ...valid]);
    setError(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [validateFiles]);

  const handlePaste = useCallback((files: File[]) => {
    const { valid, error: validationError } = validateFiles(files);

    if (validationError) {
      setError(validationError);
      return;
    }

    if (valid.length > 0) {
      setSelectedFiles(prev => [...prev, ...valid]);
      setError(null);
    }
  }, [validateFiles]);

  const removeFile = useCallback((index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
    setError(null);
  }, []);

  const clearFiles = useCallback(() => {
    setSelectedFiles([]);
    setError(null);
    setUploadProgress(0);
    // Reset drag state as safety measure
    dragCounterRef.current = 0;
    setIsDragging(false);
  }, []);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (e.dataTransfer.types.includes('Files')) {
      dragCounterRef.current += 1;
      setIsDragging(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    dragCounterRef.current -= 1;
    if (dragCounterRef.current === 0) {
      setIsDragging(false);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    // Reset drag state
    dragCounterRef.current = 0;
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    const { valid, error: validationError } = validateFiles(files);

    if (validationError) {
      setError(validationError);
      return;
    }

    if (valid.length > 0) {
      setSelectedFiles(prev => [...prev, ...valid]);
      setError(null);
    }
  }, [validateFiles]);

  // Handle Tauri Drag and Drop
  useEffect(() => {
    // Check if running in Tauri by checking for window.__TAURI__ or similar if needed, 
    // but the listen function works gracefully or we can just try/catch.
    // Actually, explicit check is better to avoid errors in browser mode if imports usually fail?
    // The imports are standard modules handled by Vite, so they exist but might throw or no-op.

    let unlistenDrop: (() => void) | undefined;
    let unlistenEnter: (() => void) | undefined;
    let unlistenLeave: (() => void) | undefined;

    const setupListener = async () => {
      try {
        unlistenDrop = await listen<{ paths: string[] }>('tauri://drag-drop', async (event) => {
          setIsDragging(false); // Ensure drag state is cleared on drop
          const files: File[] = [];
          for (const path of event.payload.paths) {
            try {
              const content = await readFile(path);
              const name = path.split(/[\\/]/).pop() || 'unknown';
              const type = getMimeType(name);
              files.push(new File([content], name, { type }));
            } catch (err) {
              console.error('Failed to read dropped file:', path, err);
            }
          }

          if (files.length > 0) {
            const { valid, error: validationError } = validateFiles(files);
            if (validationError) {
              setError(validationError);
            } else {
              setSelectedFiles(prev => [...prev, ...valid]);
              setError(null);
            }
          }
        });

        unlistenEnter = await listen('tauri://drag-enter', () => {
          setIsDragging(true);
        });

        unlistenLeave = await listen('tauri://drag-leave', () => {
          setIsDragging(false);
        });

      } catch (err) {
        // Not in Tauri or plugin not initialized
        console.debug('Tauri drag-drop listener failed to initialize (expected in browser)', err);
      }
    };

    setupListener();

    return () => {
      if (unlistenDrop) unlistenDrop();
      if (unlistenEnter) unlistenEnter();
      if (unlistenLeave) unlistenLeave();
    };
  }, [validateFiles]);

  // Convert images to base64 for preview
  const convertImagesToBase64 = useCallback(async (images: File[]): Promise<ImageAttachment[]> => {
    const promises = images.map(file => {
      return new Promise<ImageAttachment>((resolve) => {
        const reader = new FileReader();
        reader.onload = (e) => {
          const dataUrl = e.target?.result as string;
          const base64Data = dataUrl.split(',')[1];
          resolve({
            id: crypto.randomUUID(),
            data: base64Data,
            mime_type: file.type,
            filename: file.name
          });
        };
        reader.readAsDataURL(file);
      });
    });
    return Promise.all(promises);
  }, []);

  // Upload all files to server and generate image previews
  const uploadFiles = useCallback(async (files: File[], chatId: string): Promise<UploadResult> => {
    setIsUploading(true);
    setUploadProgress(0);
    setError(null);

    try {
      // Step 1: Upload ALL files to server
      const formData = new FormData();
      files.forEach(file => {
        formData.append('files', file);
      });

      const fileMetadata = await new Promise<FileAttachment[]>((resolve, reject) => {
        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            const progress = (e.loaded / e.total) * 100;
            setUploadProgress(progress);
          }
        });

        xhr.addEventListener('load', () => {
          if (xhr.status === 200) {
            try {
              const response = JSON.parse(xhr.responseText);
              setUploadProgress(100);
              resolve(response.files);
            } catch (err) {
              reject(new Error('Failed to parse upload response'));
            }
          } else {
            reject(new Error(`Upload failed with status ${xhr.status}`));
          }
        });

        xhr.addEventListener('error', () => {
          reject(new Error('Upload failed due to network error'));
        });

        xhr.addEventListener('abort', () => {
          reject(new Error('Upload was cancelled'));
        });

        xhr.open('POST', `${getApiBase()}/sandbox/upload?chat_id=${chatId}`);
        xhr.send(formData);
      });

      // Step 2: For images, ALSO convert to base64 for preview
      const imageFiles = files.filter(f => f.type.startsWith('image/'));
      const imagePreviews = imageFiles.length > 0
        ? await convertImagesToBase64(imageFiles)
        : [];

      return { fileMetadata, imagePreviews };
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Upload failed';
      setError(errorMessage);
      throw err;
    } finally {
      setIsUploading(false);
    }
  }, [convertImagesToBase64]);

  return {
    selectedFiles,
    setSelectedFiles,
    isDragging,
    uploadProgress,
    isUploading,
    error,
    fileInputRef,
    handleFileSelect,
    handlePaste,
    removeFile,
    clearFiles,
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
    uploadFiles,
  };
}

// Helper to guess mime type
function getMimeType(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase();
  if (!ext) return 'application/octet-stream';

  const mimeMap: Record<string, string> = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp',
    'svg': 'image/svg+xml',
    'pdf': 'application/pdf',
    'txt': 'text/plain',
    'md': 'text/markdown',
    'json': 'application/json',
    'js': 'text/javascript',
    'jsx': 'text/javascript',
    'ts': 'text/typescript',
    'tsx': 'text/typescript',
    'py': 'text/x-python',
    'html': 'text/html',
    'css': 'text/css',
  };

  return mimeMap[ext] || 'application/octet-stream';
}
