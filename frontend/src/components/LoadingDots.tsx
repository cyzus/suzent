import React from 'react';
export const LoadingDots: React.FC = () => (
  <span className="inline-flex gap-1">
    <span className="w-2 h-2 bg-brutal-black animate-bounce" style={{ animationDelay: '0ms' }} />
    <span className="w-2 h-2 bg-brutal-black animate-bounce" style={{ animationDelay: '150ms' }} />
    <span className="w-2 h-2 bg-brutal-black animate-bounce" style={{ animationDelay: '300ms' }} />
  </span>
);
