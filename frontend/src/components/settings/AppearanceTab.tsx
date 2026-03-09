import React from 'react';
import { useTheme } from '../../hooks/useTheme';

type PresetKey = 'warm' | 'cold';

const PRESETS: Record<PresetKey, { label: string; lightColor: string; darkColor: string }> = {
  warm: {
    label: 'Warm',
    lightColor: '#FFE666',
    darkColor: '#FF6600',
  },
  cold: {
    label: 'Cold',
    lightColor: '#7DD3FC',
    darkColor: '#38BDF8',
  },
};

function getActivePreset(lightColor: string, darkColor: string): PresetKey | null {
  for (const [key, preset] of Object.entries(PRESETS)) {
    if (
      preset.lightColor.toLowerCase() === lightColor.toLowerCase() &&
      preset.darkColor.toLowerCase() === darkColor.toLowerCase()
    ) {
      return key as PresetKey;
    }
  }
  return null;
}

/** Mini UI mockup drawn inside each preset card */
function CardPreview({ lightColor, darkColor }: { lightColor: string; darkColor: string }) {
  return (
    <div className="flex h-full">
      {/* Light half */}
      <div className="flex-1 bg-white flex flex-col gap-1.5 p-2.5">
        {/* fake header bar */}
        <div className="h-2.5 w-full rounded-sm" style={{ backgroundColor: lightColor }} />
        {/* fake text lines */}
        <div className="h-1.5 w-4/5 bg-neutral-200 rounded-sm" />
        <div className="h-1.5 w-3/5 bg-neutral-200 rounded-sm" />
        {/* fake button */}
        <div className="mt-auto h-4 w-3/4 rounded-sm border border-neutral-300" style={{ backgroundColor: lightColor }} />
      </div>

      {/* Divider */}
      <div className="w-px bg-neutral-300" />

      {/* Dark half */}
      <div className="flex-1 bg-zinc-800 flex flex-col gap-1.5 p-2.5">
        {/* fake header bar */}
        <div className="h-2.5 w-full rounded-sm" style={{ backgroundColor: darkColor }} />
        {/* fake text lines */}
        <div className="h-1.5 w-4/5 bg-zinc-600 rounded-sm" />
        <div className="h-1.5 w-3/5 bg-zinc-600 rounded-sm" />
        {/* fake button */}
        <div className="mt-auto h-4 w-3/4 rounded-sm border border-zinc-600" style={{ backgroundColor: darkColor }} />
      </div>
    </div>
  );
}

export function AppearanceTab(): React.ReactElement {
  const { lightColor, darkColor, setLightColor, setDarkColor } = useTheme();
  const activePreset = getActivePreset(lightColor, darkColor);

  function applyPreset(key: PresetKey) {
    setLightColor(PRESETS[key].lightColor);
    setDarkColor(PRESETS[key].darkColor);
  }

  return (
    <div className="space-y-6">
      <div className="bg-brutal-black text-white p-3 border-3 border-brutal-black">
        <h3 className="font-brutal text-xl uppercase tracking-tight">Appearance</h3>
        <p className="text-xs text-neutral-300 font-mono">Choose an accent color theme</p>
      </div>

      <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal p-6">
        <div className="text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400 mb-5">
          Accent Color
        </div>

        <div className="flex gap-5 flex-wrap">
          {(Object.keys(PRESETS) as PresetKey[]).map((key) => {
            const preset = PRESETS[key];
            const isActive = activePreset === key;

            return (
              <button
                key={key}
                onClick={() => applyPreset(key)}
                className="flex flex-col items-center gap-2 focus:outline-none"
              >
                {/* Card */}
                <div
                  className={[
                    'w-40 h-28 border-3 border-brutal-black overflow-hidden transition-all',
                    isActive
                      ? 'shadow-[0_0_0_3px_#000,4px_4px_0_3px_#000]'
                      : 'shadow-[3px_3px_0_0_#000] hover:shadow-[5px_5px_0_0_#000] hover:-translate-x-px hover:-translate-y-px',
                  ].join(' ')}
                >
                  <CardPreview lightColor={preset.lightColor} darkColor={preset.darkColor} />
                </div>

                {/* Label */}
                <div className="flex items-center gap-1.5">
                  {isActive && (
                    <svg className="w-3 h-3 text-brutal-black dark:text-white" fill="currentColor" viewBox="0 0 12 12">
                      <path d="M10 3L5 8.5 2 5.5 1 6.5l4 4 6-7z" />
                    </svg>
                  )}
                  <span
                    className={`text-xs font-bold uppercase ${
                      isActive
                        ? 'text-brutal-black dark:text-white'
                        : 'text-neutral-400 dark:text-neutral-500'
                    }`}
                  >
                    {preset.label}
                  </span>
                </div>

                {/* Color swatches */}
                <div className="flex gap-1">
                  <div
                    className="w-4 h-4 border-2 border-brutal-black"
                    title="Light mode"
                    style={{ backgroundColor: preset.lightColor }}
                  />
                  <div
                    className="w-4 h-4 border-2 border-brutal-black"
                    title="Dark mode"
                    style={{ backgroundColor: preset.darkColor }}
                  />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
