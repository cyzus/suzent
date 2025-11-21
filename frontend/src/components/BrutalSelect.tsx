import React, { useState, useRef, useEffect } from 'react';

interface Option {
  value: string;
  label: string;
}

interface BrutalSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: (string | Option)[];
  label?: string;
  placeholder?: string;
  className?: string;
}

export const BrutalSelect: React.FC<BrutalSelectProps> = ({
  value,
  onChange,
  options,
  label,
  placeholder = 'SELECT...',
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Normalize options to Option objects
  const normalizedOptions: Option[] = options.map(opt => 
    typeof opt === 'string' ? { value: opt, label: opt } : opt
  );

  const selectedOption = normalizedOptions.find(opt => opt.value === value);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      {label && (
        <label className="block font-bold tracking-wide text-brutal-black uppercase mb-1 text-xs">
          {label}
        </label>
      )}
      
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full bg-white border-3 border-brutal-black px-3 py-2 font-bold text-sm text-left flex items-center justify-between transition-all duration-200 hover:bg-brutal-yellow focus:outline-none ${isOpen ? 'shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] translate-x-[1px] translate-y-[1px]' : 'shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]'}`}
      >
        <span className="truncate">
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <svg 
          className={`w-4 h-4 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} 
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24" 
          strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute z-50 w-full mt-1 bg-white border-3 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] max-h-60 overflow-y-auto animate-brutal-drop">
          {normalizedOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
              }}
              className={`w-full text-left px-3 py-2 font-bold text-sm uppercase transition-colors border-b-2 border-neutral-100 last:border-0 ${
                value === option.value
                  ? 'bg-brutal-black text-white'
                  : 'bg-white text-brutal-black hover:bg-brutal-yellow'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
