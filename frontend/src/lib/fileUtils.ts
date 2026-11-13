/**
 * File utility functions and constants
 */

// File type categories
export const FILE_TYPES = {
  IMAGE: ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'],
  PDF: ['pdf'],
  VIDEO: ['mp4', 'mov', 'webm', 'm4v'],
  AUDIO: ['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac', 'opus'],
  HTML: ['html', 'htm'],
  MARKDOWN: ['md'],
  MERMAID: ['mermaid'],
  CODE: ['js', 'jsx', 'ts', 'tsx', 'py', 'json', 'yml', 'yaml', 'css', 'xml', 'sh'],
} as const;

// Combined file types for specific use cases
export const BINARY_SERVED_FILES = [
  ...FILE_TYPES.PDF,
  ...FILE_TYPES.IMAGE,
  ...FILE_TYPES.VIDEO,
  ...FILE_TYPES.AUDIO,
  ...FILE_TYPES.HTML,
] as const;

/**
 * Extract file extension from filename
 */
export function getFileExtension(filename: string): string {
  return filename.split('.').pop()?.toLowerCase() || '';
}

/**
 * Check if file is an image
 */
export function isImageFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return FILE_TYPES.IMAGE.includes(ext as any);
}

/**
 * Check if file is a video the webview can play
 */
export function isVideoFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return FILE_TYPES.VIDEO.includes(ext as any);
}

/**
 * Check if file is audio the webview can play
 */
export function isAudioFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return FILE_TYPES.AUDIO.includes(ext as any);
}

/**
 * Check if file is a PDF
 */
export function isPdfFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return FILE_TYPES.PDF.includes(ext as any);
}

/**
 * Check if file is HTML
 */
export function isHtmlFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return FILE_TYPES.HTML.includes(ext as any);
}

/**
 * Check if file is Markdown
 */
export function isMarkdownFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return FILE_TYPES.MARKDOWN.includes(ext as any);
}

/**
 * Check if file is Mermaid diagram
 */
export function isMermaidFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return FILE_TYPES.MERMAID.includes(ext as any);
}

/**
 * Check if file is a code file
 */
export function isCodeFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return FILE_TYPES.CODE.includes(ext as any);
}

/**
 * Check if file should be served directly (not fetched as text)
 * Includes: images, PDFs, HTML
 */
export function isBinaryServedFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return BINARY_SERVED_FILES.includes(ext as any);
}

/**
 * Get programming language for syntax highlighting
 */
export function getLanguageForFile(filename: string): string {
  const ext = getFileExtension(filename);
  return isCodeFile(filename) ? ext : 'text';
}
