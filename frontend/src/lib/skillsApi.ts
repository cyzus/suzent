/**
 * Skills API client functions
 */

import { getApiBase } from './api';
import { Skill } from '../types/skills';



export async function fetchSkills(): Promise<Skill[]> {
    const res = await fetch(`${getApiBase()}/skills`);
    if (!res.ok) {
        throw new Error(`Failed to fetch skills: ${res.statusText}`);
    }
    return await res.json();
}

export async function reloadSkills(): Promise<{ loaded: string[], failed: string[] }> {
    const res = await fetch(`${getApiBase()}/skills/reload`, {
        method: 'POST'
    });
    if (!res.ok) {
        throw new Error(`Failed to reload skills: ${res.statusText}`);
    }
    return await res.json();
}

export async function toggleSkill(skillName: string, enabled: boolean): Promise<void> {
    const res = await fetch(`${getApiBase()}/skills/${skillName}/toggle`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ enabled })
    });
    if (!res.ok) {
        throw new Error(`Failed to toggle skill: ${res.statusText}`);
    }
    // No return value expected for void promise, but consume body if any
    await res.text();
}
