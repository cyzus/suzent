import React from 'react';
import { useTheme } from '../../hooks/useTheme';

const DEFAULT_LIGHT_COLOR = '#FFE666';
const DEFAULT_DARK_COLOR = '#FF6600';

export function AppearanceTab(): React.ReactElement {
  const { theme, lightColor, darkColor, setLightColor, setDarkColor } = useTheme();

  return (
    <div className="space-y-6">
      <div className="bg-brutal-black text-white p-3 border-3 border-brutal-black">
        <h3 className="font-brutal text-xl uppercase tracking-tight">Appearance</h3>
        <p className="text-xs text-neutral-300 font-mono">Customize accent colors for light and dark mode</p>
      </div>

      <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal p-6 space-y-6">
        {/* Light mode color */}
        <div>
          <label className="block text-xs font-bold uppercase text-neutral-600 dark:text-neutral-400 mb-3">
            Light Mode Accent Color
          </label>
          <div className="flex items-center gap-4">
            <div
              className="w-12 h-12 border-3 border-brutal-black flex-shrink-0"
              style={{ backgroundColor: lightColor }}
            />
            <input
              type="color"
              value={lightColor}
              onChange={(e) => setLightColor(e.target.value)}
              className="w-12 h-12 border-3 border-brutal-black cursor-pointer bg-transparent p-0.5"
            />
            <div className="flex-1 min-w-0">
              <div className="font-mono text-sm dark:text-white">{lightColor}</div>
              <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                Used for highlights, buttons, and accents in light mode
              </div>
            </div>
            <button
              onClick={() => setLightColor(DEFAULT_LIGHT_COLOR)}
              className="px-3 py-2 border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white font-bold text-xs uppercase hover:bg-neutral-100 dark:hover:bg-zinc-600 shadow-[2px_2px_0_0_#000] brutal-btn flex-shrink-0"
            >
              Reset
            </button>
          </div>
        </div>

        <div className="border-t-2 border-neutral-200 dark:border-zinc-700" />

        {/* Dark mode color */}
        <div>
          <label className="block text-xs font-bold uppercase text-neutral-600 dark:text-neutral-400 mb-3">
            Dark Mode Accent Color
          </label>
          <div className="flex items-center gap-4">
            <div
              className="w-12 h-12 border-3 border-brutal-black flex-shrink-0"
              style={{ backgroundColor: darkColor }}
            />
            <input
              type="color"
              value={darkColor}
              onChange={(e) => setDarkColor(e.target.value)}
              className="w-12 h-12 border-3 border-brutal-black cursor-pointer bg-transparent p-0.5"
            />
            <div className="flex-1 min-w-0">
              <div className="font-mono text-sm dark:text-white">{darkColor}</div>
              <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                Used for highlights, buttons, and accents in dark mode
              </div>
            </div>
            <button
              onClick={() => setDarkColor(DEFAULT_DARK_COLOR)}
              className="px-3 py-2 border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white font-bold text-xs uppercase hover:bg-neutral-100 dark:hover:bg-zinc-600 shadow-[2px_2px_0_0_#000] brutal-btn flex-shrink-0"
            >
              Reset
            </button>
          </div>
        </div>
      </div>

      {/* Live preview */}
      <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal p-6">
        <div className="text-xs font-bold uppercase text-neutral-600 dark:text-neutral-400 mb-4">
          Preview ({theme === 'dark' ? 'Dark Mode' : 'Light Mode'})
        </div>
        <div className="flex gap-3 flex-wrap items-center">
          <button
            className="px-4 py-2 border-3 border-brutal-black font-bold uppercase text-brutal-black shadow-[3px_3px_0_0_#000]"
            style={{ backgroundColor: theme === 'dark' ? darkColor : lightColor }}
          >
            Button
          </button>
          <div
            className="px-4 py-2 border-3 border-brutal-black font-bold text-brutal-black text-sm"
            style={{ backgroundColor: theme === 'dark' ? darkColor : lightColor }}
          >
            Active Tab
          </div>
          <div
            className="w-10 h-10 border-3 border-brutal-black shadow-[3px_3px_0_0_#000]"
            style={{ backgroundColor: theme === 'dark' ? darkColor : lightColor }}
          />
          <span
            className="text-xs font-bold uppercase px-2 py-1 border-2 border-brutal-black"
            style={{ backgroundColor: theme === 'dark' ? darkColor : lightColor }}
          >
            Badge
          </span>
        </div>
      </div>
    </div>
  );
}
