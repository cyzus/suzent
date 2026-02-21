import React from 'react';
import { RobotAvatar, RobotVariant } from './RobotAvatar';
import { useI18n } from '../../i18n';

const variants: RobotVariant[] = [
    'idle', 'observer', 'jumper', 'snoozer',
    'peeker', 'shaker', 'skeptic', 'love',
    'rage', 'party', 'eater', 'dj',
    'ghost', 'workout', 'portal', 'scanner'
];

export const RobotShowcase: React.FC = () => {
    const { t } = useI18n();
    return (
        <div className="flex-1 overflow-y-auto bg-neutral-100 p-8">
            <div className="max-w-6xl mx-auto">
                <h2 className="text-4xl font-brutal font-bold mb-8 uppercase tracking-tighter">
                    {t('views.robotGallery')}
                </h2>

                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-8">
                    {variants.map((variant) => (
                        <div key={variant} className="bg-white border-3 border-brutal-black shadow-brutal-lg p-6 flex flex-col items-center gap-4 transition-transform hover:translate-y-[-4px] hover:shadow-brutal-xl">
                            <div className="w-full aspect-square bg-white border-2 border-neutral-200 rounded-lg flex items-center justify-center p-4 overflow-hidden relative group">
                                {/* Checkerboard background for transparency checks */}
                                <div className="absolute inset-0 opacity-10"
                                    style={{ backgroundImage: 'radial-gradient(#000 1px, transparent 1px)', backgroundSize: '10px 10px' }}>
                                </div>

                                <div className="w-32 h-32 relative z-10 text-white">
                                    <RobotAvatar variant={variant} className="w-full h-full" />
                                </div>
                            </div>

                            <div className="text-center w-full">
                                <h3 className="font-bold text-xl uppercase tracking-wide">{variant}</h3>
                                <div className="text-xs font-mono text-neutral-500 mt-1 uppercase">
                                    V{13 + variants.indexOf(variant)}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};
