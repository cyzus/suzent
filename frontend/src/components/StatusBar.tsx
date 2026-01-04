import React from 'react';
import { useStatusStore, StatusType } from '../hooks/useStatusStore';

const getStatusStyles = (type: StatusType) => {
  switch (type) {
    case 'error':
      return 'bg-brutal-red text-white';
    case 'success':
      return 'bg-brutal-green text-brutal-black';
    case 'warning':
      return 'bg-brutal-yellow text-brutal-black';
    case 'info':
      return 'bg-brutal-blue text-white';
    case 'idle':
    default:
      return 'bg-neutral-200 text-neutral-500';
  }
};

const getStatusIcon = (type: StatusType) => {
  switch (type) {
    case 'error': return '!';
    case 'success': return '✓';
    case 'warning': return '⚠';
    case 'info': return 'i';
    case 'idle': return '•';
    default: return '';
  }
};

export const StatusBar: React.FC = () => {
  const { message, type } = useStatusStore();

  return (
    <div className={`
      w-full h-7 flex items-center px-4 md:px-6 
      border-b-3 border-brutal-black 
      font-mono text-[10px] md:text-xs font-bold uppercase tracking-wider
      transition-colors duration-200
      ${getStatusStyles(type)}
    `}>
      <div className="flex items-center gap-3 w-full">
        <span className="flex-shrink-0 w-4 text-center">{getStatusIcon(type)}</span>
        <span className="truncate flex-1">{message}</span>
        <span className="hidden md:inline opacity-50">
          {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
      </div>
    </div>
  );
};
