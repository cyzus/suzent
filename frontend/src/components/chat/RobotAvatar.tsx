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

    const ROBOT_SCALE = 0.75;

    // Wrapper for consistent scaling and centering
    const RobotBody = ({ children, style = {} }: { children: React.ReactNode; style?: React.CSSProperties }) => (
        <div className="w-full h-full flex items-center justify-center" style={style}>
            <svg className="w-full h-full" viewBox="0 0 24 24" style={{ transform: `scale(${ROBOT_SCALE})` }}>
                {children}
            </svg>
        </div>
    );

    // Standard robot face (black square with two eyes)
    const RobotFace = ({ eyesClass = '', eyeStyle = {} }: { eyesClass?: string; eyeStyle?: React.CSSProperties }) => (
        <>
            <rect x="0" y="0" width="24" height="24" rx="4" fill="#000000" />
            <rect className={`eye left ${eyesClass}`} style={eyeStyle} x="5" y="8" width="5" height="5" rx="1.5" fill="currentColor" />
            <rect className={`eye right ${eyesClass}`} style={eyeStyle} x="14" y="8" width="5" height="5" rx="1.5" fill="currentColor" />
        </>
    );

    // Combined BaseRobot for simple cases
    const BaseRobot = ({ eyesClass = '', eyeStyle = {}, style = {} }: { eyesClass?: string; eyeStyle?: React.CSSProperties; style?: React.CSSProperties }) => (
        <RobotBody style={style}>
            <RobotFace eyesClass={eyesClass} eyeStyle={eyeStyle} />
        </RobotBody>
    );

    // --- Variant Renderers ---

    // V14: Observer (Searching/Active)
    if (variant === 'observer') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <RobotBody>
                    <rect x="0" y="0" width="24" height="24" rx="4" fill="#000000" />
                    <g style={{ animation: 'robot-look-around 4s infinite step-end' }}>
                        <rect className="eye" x="5" y="8" width="5" height="5" rx="1.5" fill="currentColor" />
                        <rect className="eye" x="14" y="8" width="5" height="5" rx="1.5" fill="currentColor" />
                    </g>
                </RobotBody>
            </div>
        );
    }

    // V15: Jumper (Action)
    if (variant === 'jumper') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="w-full h-full flex items-center justify-center">
                    <svg className="w-full h-full" viewBox="0 0 24 24" overflow="visible" style={{ transform: `scale(${ROBOT_SCALE})` }}>

                        {/* Jumping Body */}
                        <g style={{ animation: 'robot-jump-body 1.2s infinite' }}>
                            <rect x="0" y="0" width="24" height="24" rx="4" fill="#000000" />
                            <rect className="eye left" x="5" y="8" width="5" height="5" rx="1.5" fill="currentColor" />
                            <rect className="eye right" x="14" y="8" width="5" height="5" rx="1.5" fill="currentColor" />
                        </g>
                    </svg>
                </div>
            </div>
        );
    }

    // V16: Snoozer (Idle/Sleep) -> More Zzzs
    if (variant === 'snoozer') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="w-full h-full flex items-center justify-center" style={{ animation: 'robot-breathe-body 4s infinite ease-in-out' }}>
                    <svg className="w-full h-full" viewBox="0 0 24 24" overflow="visible" style={{ transform: `scale(${ROBOT_SCALE})` }}>
                        <RobotFace eyeStyle={{ animation: 'robot-breathe-eyes 4s infinite ease-in-out', transformOrigin: 'center' }} />
                        {/* Floating Z's - SVG text elements */}
                        <text x="26" y="4" fontSize="5" fontWeight="bold" fill="#000000" opacity="0.6" style={{ animation: 'robot-float-z 3s infinite linear' }}>Z</text>
                        <text x="28" y="8" fontSize="4" fontWeight="bold" fill="#000000" opacity="0.6" style={{ animation: 'robot-float-z 3s infinite linear', animationDelay: '1s' }}>z</text>
                        <text x="27" y="12" fontSize="3" fontWeight="bold" fill="#000000" opacity="0.6" style={{ animation: 'robot-float-z 3s infinite linear', animationDelay: '2s' }}>.</text>
                    </svg>
                </div>
            </div>
        );
    }

    // V17: Peeker (Active/HideAndSeek)
    if (variant === 'peeker') {
        return (
            <div className={`relative w-full h-full overflow-hidden ${className}`}>
                <BaseRobot style={{ animation: 'robot-peek-up 3s infinite ease-in-out' }} />
            </div>
        );
    }

    // V18: Shaker (Error/Panic)
    if (variant === 'shaker') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="w-full h-full flex items-center justify-center" style={{ animation: 'robot-shake-hard 0.2s infinite' }}>
                    <svg className="w-full h-full" viewBox="0 0 24 24" overflow="visible" style={{ transform: `scale(${ROBOT_SCALE})` }}>
                        <RobotFace eyeStyle={{ animation: 'robot-dilate 2s infinite alternate', transformOrigin: 'center' }} />
                        {/* Sweat drops - SVG circles */}
                        <ellipse cx="-2" cy="2" rx="1.5" ry="2" fill="#000000" opacity="0" style={{ animation: 'robot-sweat-drop 0.8s infinite' }} />
                        <ellipse cx="-3" cy="5" rx="1" ry="1.5" fill="#000000" opacity="0" style={{ animation: 'robot-sweat-drop 0.7s infinite 0.2s' }} />
                        <ellipse cx="26" cy="2" rx="1.5" ry="2" fill="#000000" opacity="0" style={{ animation: 'robot-sweat-drop 0.8s infinite 0.4s' }} />
                        <ellipse cx="27" cy="5" rx="1" ry="1.5" fill="#000000" opacity="0" style={{ animation: 'robot-sweat-drop 0.7s infinite 0.1s' }} />
                    </svg>
                </div>
            </div>
        );
    }

    // V19: Skeptic (Thinking/Pondering)
    if (variant === 'skeptic') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="w-full h-full flex items-center justify-center" style={{ animation: 'robot-ponder-tilt 3s infinite ease-in-out', transformOrigin: 'bottom center' }}>
                    <svg className="w-full h-full" viewBox="0 0 24 24" overflow="visible" style={{ transform: `scale(${ROBOT_SCALE})` }}>
                        <rect x="0" y="0" width="24" height="24" rx="4" fill="#000000" />
                        <rect className="eye" x="5" y="8" width="5" height="5" rx="1.5" fill="currentColor" style={{ transformOrigin: 'center', animation: 'robot-squint 3s infinite ease-in-out' }} />
                        <rect className="eye" x="14" y="8" width="5" height="5" rx="1.5" fill="currentColor" style={{ animation: 'robot-raise-brow 3s infinite ease-in-out' }} />
                        {/* Floating ? - SVG text */}
                        <text x="22" y="3" fontSize="8" fontWeight="bold" fill="#000000" style={{ animation: 'robot-float-q 3s infinite ease-in-out' }}>?</text>
                    </svg>
                </div>
            </div>
        );
    }

    // V20: Love (Heart Eyes)
    if (variant === 'love') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="w-full h-full flex items-center justify-center" style={{ animation: 'robot-heartbeat 1s infinite' }}>
                    <svg className="w-full h-full" viewBox="0 0 24 24" overflow="visible" style={{ transform: `scale(${ROBOT_SCALE})` }}>
                        <rect x="0" y="0" width="24" height="24" rx="4" fill="#000000" />
                        <text x="5.5" y="12" fontSize="5" fill="currentColor" style={{ animation: 'robot-pulse-eye 1s infinite alternate', transformOrigin: 'center' }}>♥</text>
                        <text x="14.5" y="12" fontSize="5" fill="currentColor" style={{ animation: 'robot-pulse-eye 1s infinite alternate', transformOrigin: 'center' }}>♥</text>
                        {/* Floating hearts - SVG text */}
                        <text x="-4" y="4" fontSize="4" fill="#000000" style={{ animation: 'robot-float-up 2s infinite linear' }}>♥</text>
                        <text x="-2" y="0" fontSize="3" fill="#000000" style={{ animation: 'robot-float-up 2s infinite linear 0.5s' }}>♥</text>
                        <text x="26" y="6" fontSize="4" fill="#000000" style={{ animation: 'robot-float-up 2s infinite linear 1s' }}>♥</text>
                        <text x="24" y="-2" fontSize="3" fill="#000000" style={{ animation: 'robot-float-up 2s infinite linear 1.5s' }}>♥</text>
                    </svg>
                </div>
            </div>
        );
    }

    // V21: Rage (Angry/Error)
    if (variant === 'rage') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="w-full h-full flex items-center justify-center" style={{ animation: 'robot-vibrate 0.1s infinite' }}>
                    <svg className="w-full h-full" viewBox="0 0 24 24" overflow="visible" style={{ transform: `scale(${ROBOT_SCALE})` }}>
                        <rect x="0" y="0" width="24" height="24" rx="4" fill="#000000" />
                        <rect className="eye left" x="5" y="8" width="5" height="5" rx="1.5" fill="currentColor" />
                        <rect className="eye right" x="14" y="8" width="5" height="5" rx="1.5" fill="currentColor" />
                        <rect x="7" y="9" width="5" height="2" fill="#000000" transform="rotate(20, 7.5, 8)" />
                        <rect x="12" y="9" width="5" height="2" fill="#000000" transform="rotate(-20, 16.5, 8)" />
                        {/* Steam particles - SVG circles */}
                        <circle cx="-2" cy="8" r="1.5" fill="#666666" opacity="0" style={{ animation: 'robot-steam-rise 0.5s infinite linear' }} />
                        <circle cx="26" cy="4" r="1.5" fill="#666666" opacity="0" style={{ animation: 'robot-steam-rise 0.5s infinite linear 0.2s' }} />
                    </svg>
                </div>
            </div>
        );
    }

    // V22: Party/Cool (Visor look)
    if (variant === 'party') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <RobotBody>
                    <rect x="0" y="0" width="24" height="24" rx="4" fill="#000000" />
                    <g style={{ animation: 'robot-glasses-bounce 0.5s infinite ease-in-out' }}>
                        <rect x="4" y="8" width="16" height="6" rx="1" fill="currentColor" />
                        <rect x="5" y="9" width="14" height="1" fill="#FFFFFF" opacity="0.5" />
                    </g>
                </RobotBody>
            </div>
        );
    }

    // V23: Eater (Munching/Action)
    if (variant === 'eater') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="w-full h-full flex items-center justify-center">
                    <svg className="w-full h-full" viewBox="0 0 24 24" overflow="visible" style={{ transform: `scale(${ROBOT_SCALE})` }}>

                        {/* Top Head (Eyes + Top) */}
                        <g style={{ animation: 'robot-eat-top 1.5s infinite ease-in-out', transformOrigin: '4px 15px' }}>
                            {/* Path: Top rounded rect - extended to y=15 */}
                            <path d="M0,4 Q0,0 4,0 L20,0 Q24,0 24,4 L24,15 L0,15 Z" fill="#000000" />
                            {/* Eyes looking forward/right */}
                            <rect className="eye" x="7.5" y="8" width="5" height="5" rx="1.5" fill="currentColor" />
                            <rect className="eye" x="15.5" y="8" width="5" height="5" rx="1.5" fill="currentColor" />
                        </g>

                        {/* Bottom Jaw */}
                        <g style={{ animation: 'robot-eat-bottom 1.5s infinite ease-in-out', transformOrigin: '4px 15px' }}>
                            {/* Path: Bottom rounded rect - start from y=15 */}
                            <path d="M0,15 L24,15 L24,20 Q24,24 20,24 L4,24 Q0,24 0,20 Z" fill="#000000" />
                        </g>

                        {/* Data bits - Bites (Mixed chunks) */}
                        {/* 8 Bites. Loop 12s. */}
                        <g style={{ transform: 'translateY(15px)' }}>
                            {/* Bite 1: 000 (x offsets to center around 6) */}
                            <g style={{ animation: 'robot-feed-train 12s infinite linear', animationDelay: '0s' }}>
                                <text x="0" y="2" fontSize="6" fontWeight="bold" fill="#000000">0</text>
                                <text x="5" y="2" fontSize="6" fontWeight="bold" fill="#000000">0</text>
                                <text x="10" y="2" fontSize="6" fontWeight="bold" fill="#000000">0</text>
                            </g>
                            {/* Bite 2: 0 */}
                            <g style={{ animation: 'robot-feed-train 12s infinite linear', animationDelay: '1.5s' }}>
                                <text x="6" y="2" fontSize="6" fontWeight="bold" fill="#000000">0</text>
                            </g>
                            {/* Bite 3: 01 */}
                            <g style={{ animation: 'robot-feed-train 12s infinite linear', animationDelay: '3.0s' }}>
                                <text x="3" y="2" fontSize="6" fontWeight="bold" fill="#000000">0</text>
                                <text x="8" y="2" fontSize="6" fontWeight="bold" fill="#000000">1</text>
                            </g>
                            {/* Bite 4: 00 */}
                            <g style={{ animation: 'robot-feed-train 12s infinite linear', animationDelay: '4.5s' }}>
                                <text x="3" y="2" fontSize="6" fontWeight="bold" fill="#000000">0</text>
                                <text x="8" y="2" fontSize="6" fontWeight="bold" fill="#000000">0</text>
                            </g>
                            {/* Bite 5: 000 */}
                            <g style={{ animation: 'robot-feed-train 12s infinite linear', animationDelay: '6.0s' }}>
                                <text x="0" y="2" fontSize="6" fontWeight="bold" fill="#000000">0</text>
                                <text x="5" y="2" fontSize="6" fontWeight="bold" fill="#000000">0</text>
                                <text x="10" y="2" fontSize="6" fontWeight="bold" fill="#000000">0</text>
                            </g>
                            {/* Bite 6: 1 */}
                            <g style={{ animation: 'robot-feed-train 12s infinite linear', animationDelay: '7.5s' }}>
                                <text x="6" y="2" fontSize="6" fontWeight="bold" fill="#000000">1</text>
                            </g>
                            {/* Bite 7: 011 */}
                            <g style={{ animation: 'robot-feed-train 12s infinite linear', animationDelay: '9.0s' }}>
                                <text x="0" y="2" fontSize="6" fontWeight="bold" fill="#000000">0</text>
                                <text x="5" y="2" fontSize="6" fontWeight="bold" fill="#000000">1</text>
                                <text x="10" y="2" fontSize="6" fontWeight="bold" fill="#000000">1</text>
                            </g>
                            {/* Bite 8: 0 */}
                            <g style={{ animation: 'robot-feed-train 12s infinite linear', animationDelay: '10.5s' }}>
                                <text x="6" y="2" fontSize="6" fontWeight="bold" fill="#000000">0</text>
                            </g>
                        </g>
                    </svg>
                </div>
            </div>
        );
    }

    // V24: DJ (With Headphones)
    if (variant === 'dj') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="w-full h-full flex items-center justify-center" style={{ animation: 'robot-head-bop 0.5s infinite alternate ease-in-out' }}>
                    <svg className="w-full h-full" viewBox="0 0 24 24" overflow="visible" style={{ transform: `scale(${ROBOT_SCALE})` }}>
                        {/* Headphones Band */}
                        <path d="M-2,12 L-2,8 Q-2,-4 12,-4 Q26,-4 26,8 L26,12" fill="none" stroke="#262626" strokeWidth="3" strokeLinecap="round" />
                        {/* Earcups */}
                        <rect x="-5" y="8" width="5" height="10" rx="2" fill="#262626" />
                        <rect x="24" y="8" width="5" height="10" rx="2" fill="#262626" />

                        <RobotFace />
                    </svg>
                </div>
            </div>
        );
    }

    // V25: Ghost (404)
    if (variant === 'ghost') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="w-full h-full flex items-center justify-center" style={{ animation: 'robot-float-ghost 3s infinite ease-in-out' }}>
                    <svg className="w-full h-full" viewBox="0 0 24 24" overflow="visible" style={{ transform: `scale(${ROBOT_SCALE})` }}>
                        <path d="M2,25 L0,23 L0,13 A12,12 0 0,1 24,13 L24,23 L22,25 L18,21 L14,25 L12,23 L10,25 L6,21 L2,25 Z" fill="#000000" />
                        <rect className="eye" x="5" y="10" width="5" height="5" rx="1.5" fill="currentColor" />
                        <rect className="eye" x="14" y="10" width="5" height="5" rx="1.5" fill="currentColor" />
                        {/* 404 text - SVG */}
                        <text x="20" y="10" fontSize="4" fontWeight="bold" fill="#999999" style={{ animation: 'robot-boo-fade 2s infinite' }}>404</text>
                    </svg>
                </div>
            </div>
        );
    }

    // V26: Workout (Training)
    if (variant === 'workout') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="w-full h-full flex items-center justify-center" style={{ animation: 'robot-squat 1.8s infinite ease-in-out', transformOrigin: 'bottom center' }}>
                    <svg className="w-full h-full" viewBox="0 0 24 24" overflow="visible" style={{ transform: `scale(${ROBOT_SCALE})` }}>
                        {/* Barbell Group - everything moves up/down together */}
                        <g style={{ animation: 'robot-lift-svg 1.8s infinite ease-in-out' }}>
                            {/* Left Arm: Pivot at hand (x=-2, y=5) - leans out at bottom, straight at top */}
                            <g style={{ animation: 'robot-arm-left 1.8s infinite ease-in-out', transformOrigin: '-2px 5px' }}>
                                <rect x="-3" y="5" width="2" height="7" rx="0.5" fill="#666666" />
                            </g>

                            {/* Right Arm: Pivot at hand (x=26, y=5) - leans out at bottom, straight at top */}
                            <g style={{ animation: 'robot-arm-right 1.8s infinite ease-in-out', transformOrigin: '26px 5px' }}>
                                <rect x="25" y="5" width="2" height="7" rx="0.5" fill="#666666" />
                            </g>

                            {/* Bar */}
                            <rect x="-6" y="5" width="36" height="1.5" rx="0.75" fill="#000000" />
                            {/* Weights */}
                            <rect x="-8" y="0" width="3" height="10" fill="#000000" />
                            <rect x="29" y="0" width="3" height="10" fill="#000000" />
                        </g>

                        {/* Robot body */}
                        <rect x="0" y="0" width="24" height="24" rx="4" fill="#000000" />
                        {/* Squinting Eyes (White on Black) */}
                        <rect x="5.5" y="9" width="5" height="2" fill="#FFFFFF" />
                        <rect x="13.5" y="9" width="5" height="2" fill="#FFFFFF" />

                        {/* Sweat drop */}
                        <ellipse cx="23" cy="10" rx="0.8" ry="1.5" fill="#666666" opacity="0" style={{ animation: 'robot-sweat-fall 1.8s infinite' }} />
                    </svg>
                </div>
            </div>
        );
    }

    // V27: Portal (Teleport)
    if (variant === 'portal') {
        return (
            <div className={`relative w-full h-full ${className}`}>
                <div className="w-full h-full flex items-center justify-center">
                    <svg className="w-full h-full" viewBox="0 0 24 24" overflow="visible" style={{ transform: `scale(${ROBOT_SCALE})` }}>
                        {/* Top Portal Hole */}
                        <ellipse cx="12" cy="-4" rx="12" ry="3" fill="#000000" style={{ animation: 'robot-hole-top 2s infinite ease-in-out' }} />

                        {/* Teleporting Robot */}
                        <g style={{ animation: 'robot-teleport 2s infinite ease-in-out' }}>
                            <RobotFace />
                        </g>

                        {/* Bottom Portal Hole */}
                        <ellipse cx="12" cy="28" rx="12" ry="3" fill="#000000" style={{ animation: 'robot-hole-bottom 2s infinite ease-in-out' }} />
                    </svg>
                </div>
            </div>
        );
    }

    // V28: Scanner (OCR/Analyzer)
    if (variant === 'scanner') {
        return (
            <div className={`relative w-full h-full ${className}`} style={{ perspective: '150px' }}>
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/50 to-transparent z-20 pointer-events-none"
                    style={{ animation: 'robot-scan-pass 2s infinite linear' }} />
                <div className="absolute inset-0 flex items-center justify-center" style={{ transform: 'rotateX(45deg)', transformOrigin: 'center' }}>
                    <div className="w-[90%] h-[90%]">
                        <BaseRobot />
                    </div>
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
