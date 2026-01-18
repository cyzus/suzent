import React from 'react';

export type RobotVariant =
    | 'idle'
    | 'observer' // V14: Searching
    | 'jumper'   // V15: Action
    | 'snoozer'  // V16: Sleep
    | 'peeker'   // V17: Hide/Seek
    | 'shaker'   // V18: Error/Panic
    | 'skeptic'  // V19: Thinking
    | 'love'     // V20: Heart Eyes
    | 'rage'     // V21: Angry
    | 'party'    // V22: Cool
    | 'eater'    // V23: Munching
    | 'dj'       // V24: Music
    | 'ghost'    // V25: 404
    | 'workout'  // V26: Training
    | 'portal'   // V27: Teleport
    | 'scanner'; // V28: OCR

interface RobotAvatarProps {
    variant?: RobotVariant;
    className?: string;
}

export const RobotAvatar: React.FC<RobotAvatarProps> = ({
    variant = 'idle',
    className = ''
}) => {

    // Base SVG structure reuse for many variants
    // Tightened margins: 1px padding instead of 2px
    const BaseRobot = ({ children, eyesClass = '', eyeStyle = {}, bodyStyle = {} }: any) => (
        <svg className="w-full h-full overflow-visible" viewBox="0 0 24 24" style={bodyStyle}>
            <rect x="0.5" y="0.5" width="23" height="23" rx="4" fill="currentColor" stroke="none" />
            <rect x="2.5" y="2.5" width="19" height="19" rx="3" fill="#000000" />
            {children}
            {/* Eyes positioned to match new scale */}
            <rect className={`eye left ${eyesClass}`} style={eyeStyle} x="5" y="7" width="5" height="5" rx="1.5" fill="currentColor" />
            <rect className={`eye right ${eyesClass}`} style={eyeStyle} x="14" y="7" width="5" height="5" rx="1.5" fill="currentColor" />
        </svg>
    );

    // --- Variant Renderers ---

    // V14: Observer (Searching/Active)
    if (variant === 'observer') {
        return (
            <div className={`relative w-full h-full flex items-center justify-center ${className}`}>
                <svg className="w-full h-full overflow-visible" viewBox="0 0 24 24">
                    <rect x="0.5" y="0.5" width="23" height="23" rx="4" fill="currentColor" />
                    <rect x="2.5" y="2.5" width="19" height="19" rx="3" fill="#000000" />
                    <g style={{ animation: 'robot-look-around 4s infinite step-end' }}>
                        <rect className="eye" x="5" y="7" width="5" height="5" rx="1.5" fill="currentColor" />
                        <rect className="eye" x="14" y="7" width="5" height="5" rx="1.5" fill="currentColor" />
                    </g>
                </svg>
            </div>
        );
    }

    // V15: Jumper (Action)
    if (variant === 'jumper') {
        return (
            <div className={`relative w-full h-full flex flex-col justify-end items-center ${className}`}>
                <div style={{ animation: 'robot-jump-body 1.2s infinite cubic-bezier(0.28, 0.84, 0.42, 1)', width: '100%', height: '100%' }}>
                    <BaseRobot />
                </div>
            </div>
        );
    }

    // V16: Snoozer (Idle/Sleep)
    if (variant === 'snoozer') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                {/* Zzz closer */}
                <div className="absolute top-0 right-1 flex flex-col text-[8px] font-bold text-brutal-black opacity-60">
                    <span style={{ animation: 'robot-float-z 3s infinite linear', animationDelay: '0s' }}>Z</span>
                    <span style={{ animation: 'robot-float-z 3s infinite linear', animationDelay: '1s' }}>z</span>
                </div>
                <div style={{ animation: 'robot-breathe-body 4s infinite ease-in-out', width: '100%', height: '100%' }}>
                    <BaseRobot eyeStyle={{ animation: 'robot-breathe-eyes 4s infinite ease-in-out', transformOrigin: 'center' }} />
                </div>
            </div>
        );
    }

    // V17: Peeker (Active/HideAndSeek)
    if (variant === 'peeker') {
        return (
            <div className={`relative w-full h-full overflow-hidden ${className}`}>
                <div style={{ animation: 'robot-peek-up 3s infinite ease-in-out', width: '100%', height: '100%' }}>
                    <BaseRobot />
                </div>
            </div>
        );
    }

    // V18: Shaker (Error/Panic)
    if (variant === 'shaker') {
        return (
            <div className={`relative w-full h-full flex flex-col items-center ${className}`}>
                {/* Sweat closer */}
                <div className="absolute top-1 left-0 w-1.5 h-2 bg-brutal-black rounded-full opacity-0" style={{ animation: 'robot-sweat-drop 0.8s infinite' }} />
                <div className="absolute top-1 right-0 w-1.5 h-2 bg-brutal-black rounded-full opacity-0" style={{ animation: 'robot-sweat-drop 0.8s infinite 0.4s' }} />
                <div style={{ animation: 'robot-shake-hard 0.2s infinite', width: '100%', height: '100%' }}>
                    <BaseRobot eyeStyle={{ animation: 'robot-dilate 2s infinite alternate', transformOrigin: 'center' }} />
                </div>
            </div>
        );
    }

    // V19: Skeptic (Thinking/Pondering)
    if (variant === 'skeptic') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                {/* Question mark closer */}
                <div className="absolute -top-3 right-0 text-lg font-bold text-brutal-black" style={{ animation: 'robot-float-q 3s infinite ease-in-out' }}>?</div>
                <div style={{ animation: 'robot-ponder-tilt 3s infinite ease-in-out', transformOrigin: 'bottom center', width: '100%', height: '100%' }}>
                    <svg className="w-full h-full" viewBox="0 0 24 24">
                        <rect x="0.5" y="0.5" width="23" height="23" rx="4" fill="currentColor" />
                        <rect x="2.5" y="2.5" width="19" height="19" rx="3" fill="#000000" />
                        <rect className="eye" x="5" y="7" width="5" height="5" rx="1.5" fill="currentColor" style={{ transformOrigin: 'center', animation: 'robot-squint 3s infinite ease-in-out' }} />
                        <rect className="eye" x="14" y="7" width="5" height="5" rx="1.5" fill="currentColor" style={{ animation: 'robot-raise-brow 3s infinite ease-in-out' }} />
                    </svg>
                </div>
            </div>
        );
    }

    // V20: Love (Heart Eyes)
    if (variant === 'love') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                {/* Hearts closer */}
                <div className="absolute -top-1 left-2 text-xs text-brutal-black" style={{ animation: 'robot-float-up 2s infinite linear' }}>♥</div>
                <div className="absolute -top-1 right-2 text-xs text-brutal-black" style={{ animation: 'robot-float-up 2s infinite linear 1s' }}>♥</div>
                <div style={{ animation: 'robot-heartbeat 1s infinite', width: '100%', height: '100%' }}>
                    <svg className="w-full h-full" viewBox="0 0 24 24">
                        <rect x="0.5" y="0.5" width="23" height="23" rx="4" fill="currentColor" />
                        <rect x="2.5" y="2.5" width="19" height="19" rx="3" fill="#000000" />
                        {/* Smaller Heart Eyes 6px instead of 8px */}
                        <text x="5" y="11.5" fontSize="6.5" fill="currentColor" style={{ animation: 'robot-pulse-eye 1s infinite alternate', transformOrigin: 'center' }}>♥</text>
                        <text x="14" y="11.5" fontSize="6.5" fill="currentColor" style={{ animation: 'robot-pulse-eye 1s infinite alternate', transformOrigin: 'center' }}>♥</text>
                    </svg>
                </div>
            </div>
        );
    }

    // V21: Rage (Angry/Error)
    if (variant === 'rage') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                {/* Steam closer */}
                <div className="absolute -top-1 left-2 w-1.5 h-1.5 bg-neutral-600 rounded-full opacity-0" style={{ animation: 'robot-steam-rise 0.5s infinite linear' }} />
                <div className="absolute -top-1 right-2 w-1.5 h-1.5 bg-neutral-600 rounded-full opacity-0" style={{ animation: 'robot-steam-rise 0.5s infinite linear 0.2s' }} />
                <div style={{ animation: 'robot-vibrate 0.1s infinite', width: '100%', height: '100%' }}>
                    {/* Eyebrows Overlay - Lower and tighter */}
                    <div className="absolute z-10 w-3 h-1 bg-neutral-800 top-[7px] left-[5px] rotate-[25deg]" />
                    <div className="absolute z-10 w-3 h-1 bg-neutral-800 top-[7px] right-[5px] -rotate-[25deg]" />
                    <BaseRobot />
                </div>
            </div>
        );
    }

    // V22: Party/Cool -> Now with Headphones/Visor or just better vibe
    // Note: User said "Party doesn't make sense". Let's try a "Visor" cool look.
    if (variant === 'party') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div style={{ animation: 'robot-bounce-beat 0.5s infinite', width: '100%', height: '100%' }}>
                    <svg className="w-full h-full overflow-visible" viewBox="0 0 24 24">
                        <rect x="0.5" y="0.5" width="23" height="23" rx="4" fill="currentColor" />
                        <rect x="2.5" y="2.5" width="19" height="19" rx="3" fill="#000000" />
                        {/* Cool Visor */}
                        <rect x="4" y="7" width="16" height="6" rx="1" fill="currentColor" />
                        {/* Visor Glint */}
                        <rect x="5" y="8" width="14" height="1" fill="#FFFFFF" opacity="0.5" />
                    </svg>
                </div>
            </div>
        );
    }

    // V23: Eater (Munching/Action)
    if (variant === 'eater') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="absolute top-1/2 right-0 -translate-y-1/2 text-[8px] font-bold text-brutal-black opacity-0" style={{ animation: 'robot-feed 1.5s infinite linear' }}>01</div>
                <div style={{ animation: 'robot-chomp 0.4s infinite alternate', width: '100%', height: '100%', transformOrigin: 'center' }}>
                    <svg className="w-full h-full" viewBox="0 0 24 24">
                        <rect x="0.5" y="0.5" width="23" height="23" rx="4" fill="currentColor" />
                        <rect x="2.5" y="2.5" width="19" height="19" rx="3" fill="#000000" />
                        <rect x="6" y="7" width="5" height="5" rx="1.5" fill="currentColor" />
                        <rect x="15" y="7" width="5" height="5" rx="1.5" fill="currentColor" />
                    </svg>
                </div>
            </div>
        );
    }

    // V24: DJ -> With Headphones
    if (variant === 'dj') {
        return (
            <div className="relative w-full h-full flex flex-col items-center justify-end">
                <div style={{ animation: 'robot-head-bop 0.5s infinite alternate ease-in-out', width: '100%', height: '100%' }}>
                    {/* Headphones container */}
                    <div className="absolute -top-1 inset-x-0 h-full pointer-events-none z-20">
                        {/* Band */}
                        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[26px] h-[10px] border-[3px] border-b-0 border-neutral-800 rounded-t-xl" />
                        {/* Ear muffs */}
                        <div className="absolute top-[8px] -left-1 w-[6px] h-[10px] bg-neutral-800 rounded-sm" />
                        <div className="absolute top-[8px] -right-1 w-[6px] h-[10px] bg-neutral-800 rounded-sm" />
                    </div>
                    <BaseRobot />
                </div>
            </div>
        );
    }

    // V25: Ghost -> Ghost Shape body
    if (variant === 'ghost') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="absolute -top-1 -right-1 text-[8px] font-bold text-neutral-400" style={{ animation: 'robot-boo-fade 2s infinite' }}>?</div>
                <div style={{ animation: 'robot-float-ghost 3s infinite ease-in-out', width: '100%', height: '100%' }}>
                    <svg className="w-full h-full overflow-visible" viewBox="0 0 24 24">
                        {/* Ghost Shape */}
                        <path d="M2,12 V6 A10,10 0 0,1 22,6 V12 L22,22 L18,18 L14,22 L10,18 L6,22 L2,18 Z"
                            fill="currentColor" stroke="none" />
                        <path d="M4,12 V6 A8,8 0 0,1 20,6 V12 L20,18 L18,16 L14,20 L10,16 L6,20 L4,16 Z"
                            fill="#000000" />
                        <rect className="eye" x="7" y="9" width="4" height="4" rx="1" fill="currentColor" />
                        <rect className="eye" x="13" y="9" width="4" height="4" rx="1" fill="currentColor" />
                    </svg>
                </div>
            </div>
        );
    }

    // V26: Workout (Training) -> Better aligned
    if (variant === 'workout') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="absolute -top-4 w-full h-1 bg-black z-20" style={{ animation: 'robot-lift 1.5s infinite' }}>
                    <div className="absolute -top-1 left-[2px] w-1 h-3 bg-black border border-black" />
                    <div className="absolute -top-1 right-[2px] w-1 h-3 bg-black border border-black" />
                </div>
                <div className="absolute top-2 -right-1 w-1 h-1 bg-black rounded-full opacity-0" style={{ animation: 'robot-sweat-fall 1.5s infinite 0.5s' }} />
                <div style={{ animation: 'robot-squat 1.5s infinite', width: '100%', height: '100%' }}>
                    <svg className="w-full h-full" viewBox="0 0 24 24">
                        <rect x="0.5" y="0.5" width="23" height="23" rx="4" fill="currentColor" />
                        <rect x="2.5" y="2.5" width="19" height="19" rx="3" fill="#000000" />
                        <rect x="5" y="9" width="5" height="2" fill="currentColor" /> {/* Squint eyes */}
                        <rect x="14" y="9" width="5" height="2" fill="currentColor" />
                    </svg>
                </div>
            </div>
        );
    }

    // V27: Portal (Teleport)
    if (variant === 'portal') {
        return (
            <div className={`relative w-full h-full flex flex-col items-center justify-center ${className}`}>
                <div className="absolute top-0 w-full h-1 bg-black rounded-full opacity-50" style={{ animation: 'robot-hole-pulse 2s infinite' }} />
                <div style={{ animation: 'robot-teleport 2s infinite ease-in-out', width: '100%', height: '100%', zIndex: 10 }}>
                    <BaseRobot />
                </div>
                <div className="absolute bottom-0 w-full h-1 bg-black rounded-full opacity-50" style={{ animation: 'robot-hole-pulse 2s infinite' }} />
            </div>
        );
    }

    // V28: Scanner (OCR/Analyzer) -> Flattened perspective
    if (variant === 'scanner') {
        return (
            <div className={`relative w-full h-full ${className}`} style={{ perspective: '100px' }}>
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/50 to-transparent z-20 pointer-events-none border-r border-black/50"
                    style={{ animation: 'robot-scan-pass 2s infinite linear' }} />
                <div style={{ transform: 'rotateX(30deg) scale(0.9)', transformOrigin: 'bottom center', width: '100%', height: '100%' }}>
                    <BaseRobot />
                </div>
            </div>
        );
    }

    // Base/Idle
    return (
        <div className={`relative w-full h-full ${className}`}>
            <BaseRobot eyesClass="robot-eye robot-eye-idle" />
        </div>
    );
};
