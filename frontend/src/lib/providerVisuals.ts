export interface ProviderVisual {
  id: string;
  label: string;
  color: string;
  logoUrl?: string;
}

const PROVIDER_VISUALS: Record<string, ProviderVisual> = {
  openai: {
    id: 'openai',
    label: 'OpenAI',
    color: '000000',
    logoUrl: 'https://api.iconify.design/simple-icons:openai.svg?color=white',
  },
  chatgpt: {
    id: 'chatgpt',
    label: 'ChatGPT',
    color: '74AA9C',
    logoUrl: 'https://api.iconify.design/simple-icons:openai.svg?color=white',
  },
  anthropic: {
    id: 'anthropic',
    label: 'Anthropic',
    color: 'D97757',
    logoUrl: 'https://cdn.simpleicons.org/anthropic',
  },
  gemini: {
    id: 'gemini',
    label: 'Google Gemini',
    color: '4285F4',
    logoUrl: 'https://cdn.simpleicons.org/googlegemini',
  },
  xai: {
    id: 'xai',
    label: 'xAI',
    color: '000000',
    logoUrl: 'https://api.iconify.design/bxl:grok.svg?color=white',
  },
  dashscope: {
    id: 'dashscope',
    label: 'Dashscope',
    color: 'FF6A00',
    logoUrl: 'https://cdn.simpleicons.org/alibabacloud',
  },
  deepseek: {
    id: 'deepseek',
    label: 'DeepSeek',
    color: '4D6BFE',
    logoUrl: 'https://api.iconify.design/simple-icons:deepseek.svg?color=white',
  },
  minimax: {
    id: 'minimax',
    label: 'MiniMax',
    color: '1F1E33',
    logoUrl: 'https://cdn.simpleicons.org/minimax',
  },
  moonshot: {
    id: 'moonshot',
    label: 'Moonshot',
    color: '1C1C1E',
    logoUrl: 'https://cdn.simpleicons.org/moonshotai',
  },
  zhipuai: {
    id: 'zhipuai',
    label: 'Zhipu AI',
    color: '2B60D6',
  },
  openrouter: {
    id: 'openrouter',
    label: 'OpenRouter',
    color: '6467F2',
    logoUrl: 'https://cdn.simpleicons.org/openrouter',
  },
  litellm_proxy: {
    id: 'litellm_proxy',
    label: 'LiteLLM Proxy',
    color: '7C3AED',
  },
  ollama: {
    id: 'ollama',
    label: 'Ollama',
    color: '000000',
    logoUrl: 'https://cdn.simpleicons.org/ollama',
  },
  perplexity: {
    id: 'perplexity',
    label: 'Perplexity',
    color: '20808D',
  },
  together: {
    id: 'together',
    label: 'Together',
    color: 'FF5733',
  },
  fireworks: {
    id: 'fireworks',
    label: 'Fireworks',
    color: '9B59B6',
  },
  sambanova: {
    id: 'sambanova',
    label: 'SambaNova',
    color: 'E34A34',
  },
  bedrock: {
    id: 'bedrock',
    label: 'Amazon Bedrock',
    color: 'FF9900',
  },
  xiaomi_mimo: {
    id: 'xiaomi_mimo',
    label: 'Xiaomi MiMo',
    color: 'FF6900',
    logoUrl: 'https://cdn.simpleicons.org/xiaomi',
  },
};

const PROVIDER_ALIASES: Record<string, string> = {
  google: 'gemini',
  zai: 'zhipuai',
};

export function normalizeProviderLogoUrl(logoUrl?: string): string | undefined {
  if (!logoUrl) return undefined;
  return logoUrl.includes('simpleicons.org') ? `${logoUrl}/ffffff` : logoUrl;
}

export function getProviderInitials(label: string): string {
  return label.slice(0, 2).toUpperCase();
}

export function normalizeProviderId(providerId?: string): string {
  if (!providerId) return '';
  return PROVIDER_ALIASES[providerId] ?? providerId;
}

export function getProviderVisual(providerId?: string): ProviderVisual | undefined {
  const normalized = normalizeProviderId(providerId);
  return PROVIDER_VISUALS[normalized];
}

export function getProviderVisualForModel(modelId?: string): ProviderVisual | undefined {
  const providerId = modelId?.split('/')[0]?.trim();
  return getProviderVisual(providerId);
}

export function getProviderColor(providerId: string, userDefined?: boolean): string {
  return getProviderVisual(providerId)?.color ?? (userDefined ? '6B7280' : 'e5e5e5');
}
