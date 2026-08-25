import {
  DocumentTextIcon,
  DocumentIcon,
  TableCellsIcon,
  CodeBracketIcon,
  PhotoIcon,
  VideoCameraIcon,
  MusicalNoteIcon,
  ArchiveBoxIcon,
  CircleStackIcon,
} from '@heroicons/react/24/outline';

interface FileIconProps {
  mimeType: string;
  className?: string;
}

export function FileIcon({ mimeType, className = 'w-4 h-4' }: FileIconProps) {
  const getIcon = () => {
    // PDF
    if (mimeType === 'application/pdf') {
      return <DocumentTextIcon className={className} />;
    }

    // Documents
    if (
      mimeType.includes('word') ||
      mimeType.includes('document') ||
      mimeType === 'application/vnd.oasis.opendocument.text'
    ) {
      return <DocumentTextIcon className={className} />;
    }

    // Spreadsheets
    if (mimeType.includes('sheet') || mimeType.includes('excel') || mimeType === 'text/csv') {
      return <TableCellsIcon className={className} />;
    }

    // Presentations
    if (mimeType.includes('presentation') || mimeType.includes('powerpoint')) {
      return <DocumentTextIcon className={className} />;
    }

    // Code files
    if (
      mimeType.includes('javascript') ||
      mimeType.includes('typescript') ||
      mimeType.includes('python') ||
      mimeType.includes('java') ||
      mimeType.includes('c++') ||
      mimeType.includes('rust') ||
      mimeType.includes('go') ||
      mimeType === 'text/html' ||
      mimeType === 'text/css' ||
      mimeType === 'application/xml' ||
      mimeType === 'text/x-python' ||
      mimeType === 'text/x-java' ||
      mimeType === 'text/x-c' ||
      mimeType === 'text/x-rust'
    ) {
      return <CodeBracketIcon className={className} />;
    }

    // JSON
    if (mimeType === 'application/json') {
      return <CodeBracketIcon className={className} />;
    }

    // Images
    if (mimeType.startsWith('image/')) {
      return <PhotoIcon className={className} />;
    }

    // Videos
    if (mimeType.startsWith('video/')) {
      return <VideoCameraIcon className={className} />;
    }

    // Audio
    if (mimeType.startsWith('audio/')) {
      return <MusicalNoteIcon className={className} />;
    }

    // Archives
    if (
      mimeType.includes('zip') ||
      mimeType.includes('rar') ||
      mimeType.includes('tar') ||
      mimeType.includes('7z') ||
      mimeType.includes('gzip') ||
      mimeType.includes('compress')
    ) {
      return <ArchiveBoxIcon className={className} />;
    }

    // Databases
    if (mimeType.includes('sqlite') || mimeType.includes('database')) {
      return <CircleStackIcon className={className} />;
    }

    // Plain text
    if (mimeType.startsWith('text/')) {
      return <DocumentTextIcon className={className} />;
    }

    // Default
    return <DocumentIcon className={className} />;
  };

  return getIcon();
}
