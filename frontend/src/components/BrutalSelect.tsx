import React, { useState, useRef, useEffect, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../i18n';

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
  dropUp?: boolean;
  className?: string;
  dropdownClassName?: string;
}

export const BrutalSelect: React.FC<BrutalSelectProps> = ({
  value,
  onChange,
  options,
  label,
  placeholder,
  dropUp = false,
  className = '',
  dropdownClassName = '',
}) => {
  const { t } = useI18n();
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState<{ top: number; left: number; width: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Normalize options to Option objects
  const normalizedOptions: Option[] = options.map(opt =>
    typeof opt === 'string' ? { value: opt, label: opt } : opt
  );

  const selectedOption = normalizedOptions.find(opt => opt.value === value);
  const resolvedPlaceholder = placeholder ?? t('select.placeholder');

  // Heuristic for scrollbar: average item height is ~38px. max-h-60 is 240px. 6 items ~ 228px.
  const showScrollbar = normalizedOptions.length > 6;

  // Auto-flip determination
  const [effectiveDropUp, setEffectiveDropUp] = useState(dropUp);

  // Calculate dropdown position
  const updatePosition = React.useCallback(() => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const dropdownHeight = Math.min(normalizedOptions.length * 40, 240); // Estimate height

      const spaceAbove = rect.top;
      const spaceBelow = window.innerHeight - rect.bottom;

      let shouldDropUp = dropUp;

      // Auto-flip logic
      if (dropUp && spaceAbove < dropdownHeight && spaceBelow > dropdownHeight) {
        shouldDropUp = false;
      } else if (!dropUp && spaceBelow < dropdownHeight && spaceAbove > dropdownHeight) {
        shouldDropUp = true;
      }

      setEffectiveDropUp(shouldDropUp);

      if (shouldDropUp) {
        setDropdownPosition({
          top: rect.top - dropdownHeight - 4,
          left: rect.left,
          width: rect.width,
        });
      } else {
        setDropdownPosition({
          top: rect.bottom + 4,
          left: rect.left,
          width: rect.width,
        });
      }
    }
  }, [dropUp, normalizedOptions.length]);

  useLayoutEffect(() => {
    if (isOpen) {
      updatePosition();

      window.addEventListener('resize', updatePosition);
      window.addEventListener('scroll', updatePosition, true); // Capture scroll on any element

      return () => {
        window.removeEventListener('resize', updatePosition);
        window.removeEventListener('scroll', updatePosition, true);
      };
    }
  }, [isOpen, updatePosition]);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      const isOutsideContainer = containerRef.current && !containerRef.current.contains(target);
      const isOutsideDropdown = dropdownRef.current && !dropdownRef.current.contains(target);

      if (isOutsideContainer && isOutsideDropdown) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const dropdown = isOpen && dropdownPosition && createPortal(
    <div
      ref={dropdownRef}
      className={`fixed z-[9999] bg-white border-3 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] max-h-60 overflow-y-auto overflow-x-hidden animate-brutal-drop scrollbar-thin ${dropdownClassName}`}
      style={{
        top: dropdownPosition.top,
        left: dropdownPosition.left,
        width: dropdownPosition.width,
      }}
    >
      {normalizedOptions.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => {
            onChange(option.value);
            setIsOpen(false);
          }}
          className={`w-full text-left px-3 py-2 font-bold text-sm uppercase transition-colors border-b-2 border-neutral-100 last:border-0 ${value === option.value
            ? 'bg-brutal-black text-white'
            : 'bg-white text-brutal-black hover:bg-brutal-yellow'
            }`}
        >
          {option.label}
        </button>
      ))}
    </div>,
    document.body
  );

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      {label && (
        <label className="block font-bold tracking-wide text-brutal-black uppercase mb-1 text-xs">
          {label}
        </label>
      )}

      <button
        ref={buttonRef}
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full bg-white border-3 border-brutal-black px-3 py-2 font-bold text-sm text-left flex items-center justify-between transition-all duration-200 hover:bg-brutal-yellow focus:outline-none ${isOpen ? 'shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] translate-x-[1px] translate-y-[1px]' : 'shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] brutal-btn'}`}
      >
        <span className="truncate">
          {selectedOption ? selectedOption.label : resolvedPlaceholder}
        </span>
        <svg
          className={`w-4 h-4 transition-transform duration-200 ${isOpen ? (effectiveDropUp ? 'rotate-0' : 'rotate-180') : (effectiveDropUp ? 'rotate-180' : 'rotate-0')}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {dropdown}
    </div>
  );
};
