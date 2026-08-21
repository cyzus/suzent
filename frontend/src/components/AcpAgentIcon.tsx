import React from 'react';

interface IconProps {
  className: string;
}

// ---------------------------------------------------------------------------
// Agent brand icons — official SVG paths from Simple Icons and vendor repos.
//
// Sources:
//   Claude:  cdn.simpleicons.org/claude  (CC0 — viewBox 0 0 24 24)
//   OpenAI:  cdn.jsdelivr.net/npm/simple-icons@latest/icons/openai.svg (CC0)
//   OpenClaw: github.com/openclaw/openclaw  ui/public/favicon.svg (MIT)
//   Hermes:  caduceus ☤ — Nous Research's text-mark; mascot is too detailed
//            for a 20px icon.
// ---------------------------------------------------------------------------

/** Anthropic Claude — official mark from Simple Icons. */
function ClaudeIcon({ api, className }: IconProps & { api?: boolean }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z" />
      {api && (
        <g>
          <circle cx="19" cy="19" r="4.5" fill="var(--color-brutal-amber, #f59e0b)" />
          <text x="19" y="21" textAnchor="middle" fontSize="6" fontWeight="bold" fill="var(--color-brutal-black, #1a1a1a)">A</text>
        </g>
      )}
    </svg>
  );
}

/** OpenAI / Codex — official hexagonal-knot mark from Simple Icons. */
function OpenAIIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z" />
    </svg>
  );
}

/**
 * Nous Research / Hermes Agent — caduceus (☤).
 * The mascot is an anime-style character too detailed for 20px; the caduceus
 * is their text-brand symbol (used in their GitHub README title).
 * Simplified: a vertical staff with two mirrored S-curves and small wings.
 */
function HermesIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      {/* Staff */}
      <line x1="12" y1="2" x2="12" y2="22" />
      {/* Left snake */}
      <path d="M12 16c-3-1.5-3-4 0-5.5-3-1.5-3-4 0-5.5" fill="none" />
      {/* Right snake */}
      <path d="M12 16c3-1.5 3-4 0-5.5 3-1.5 3-4 0-5.5" fill="none" />
      {/* Left wing */}
      <path d="M8 5.5Q5 4 3 5" />
      {/* Right wing */}
      <path d="M16 5.5Q19 4 21 5" />
      {/* Staff knob */}
      <circle cx="12" cy="2" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

/**
 * OpenClaw — simplified monochrome lobster derived from their official
 * favicon at github.com/openclaw/openclaw (ui/public/favicon.svg).
 * The original is a red gradient animated lobster; this extracts the body
 * silhouette, claws, and eye dots for a currentColor icon.
 */
function OpenClawIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 120 120" fill="currentColor">
      {/* Body */}
      <path d="M60 10C30 10 15 35 15 55C15 75 30 95 45 100L45 110L55 110L55 100C55 100 60 102 65 100L65 110L75 110L75 100C90 95 105 75 105 55C105 35 90 10 60 10Z" />
      {/* Left claw */}
      <path d="M20 45C5 40 0 50 5 60C10 70 20 65 25 55C28 48 25 45 20 45Z" />
      {/* Right claw */}
      <path d="M100 45C115 40 120 50 115 60C110 70 100 65 95 55C92 48 95 45 100 45Z" />
      {/* Antennae */}
      <path d="M45 15Q35 5 30 8" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path d="M75 15Q85 5 90 8" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      {/* Eyes — inverted (background color) for contrast */}
      <circle cx="45" cy="35" r="6" className="fill-white dark:fill-neutral-900" />
      <circle cx="75" cy="35" r="6" className="fill-white dark:fill-neutral-900" />
      <circle cx="46" cy="34" r="2.5" />
      <circle cx="76" cy="34" r="2.5" />
    </svg>
  );
}

/** Fallback — generic agent icon for unknown custom agents. */
function DefaultIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="2" width="16" height="13" rx="3" />
      <line x1="9" y1="15" x2="9" y2="21" />
      <line x1="15" y1="15" x2="15" y2="21" />
      <line x1="6" y1="21" x2="18" y2="21" />
      <circle cx="9" cy="8" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="15" cy="8" r="1.2" fill="currentColor" stroke="none" />
    </svg>
  );
}

/**
 * Brand mark for a local ACP agent, by registry id.
 *
 * Shared by the settings tab and the chat transcript so a turn produced by an
 * external agent is marked with that agent rather than with Suzent's robot.
 */
export function AcpAgentIcon({ id, className = 'w-5 h-5 shrink-0' }: { id?: string; className?: string }) {
  if (id === 'claude-code') return <ClaudeIcon className={className} />;
  if (id === 'claude-code-api') return <ClaudeIcon className={className} api />;
  if (id === 'codex') return <OpenAIIcon className={className} />;
  if (id === 'hermes') return <HermesIcon className={className} />;
  if (id === 'openclaw') return <OpenClawIcon className={className} />;
  return <DefaultIcon className={className} />;
}

