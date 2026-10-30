import openaiIcon from '../assets/provider-icons/openai.svg';
import anthropicIcon from '../assets/provider-icons/anthropic.svg';
import geminiIcon from '../assets/provider-icons/gemini.svg';
import xaiIcon from '../assets/provider-icons/xai.svg';
import bailianIcon from '../assets/provider-icons/bailian.svg';
import deepseekIcon from '../assets/provider-icons/deepseek.svg';
import minimaxIcon from '../assets/provider-icons/minimax.svg';
import moonshotIcon from '../assets/provider-icons/moonshot.svg';
import kimiIcon from '../assets/provider-icons/kimi.svg';
import zhipuIcon from '../assets/provider-icons/zhipu.svg';
import openrouterIcon from '../assets/provider-icons/openrouter.svg';
import vllmIcon from '../assets/provider-icons/vllm.svg';
import ollamaIcon from '../assets/provider-icons/ollama.svg';
import xiaomimimoIcon from '../assets/provider-icons/xiaomimimo.svg';
import bedrockIcon from '../assets/provider-icons/bedrock.svg';
import tencentcloudIcon from '../assets/provider-icons/tencentcloud.svg';
import volcengineIcon from '../assets/provider-icons/volcengine.svg';

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
    logoUrl: openaiIcon,
  },
  chatgpt: {
    id: 'chatgpt',
    label: 'ChatGPT',
    color: '74AA9C',
    logoUrl: openaiIcon,
  },
  anthropic: {
    id: 'anthropic',
    label: 'Anthropic',
    color: 'D97757',
    logoUrl: anthropicIcon,
  },
  gemini: {
    id: 'gemini',
    label: 'Google Gemini',
    color: '4285F4',
    logoUrl: geminiIcon,
  },
  xai: {
    id: 'xai',
    label: 'xAI',
    color: '000000',
    logoUrl: xaiIcon,
  },
  dashscope: {
    id: 'dashscope',
    label: 'Dashscope',
    color: 'FF6A00',
    logoUrl: bailianIcon,
  },
  deepseek: {
    id: 'deepseek',
    label: 'DeepSeek',
    color: '4D6BFE',
    logoUrl: deepseekIcon,
  },
  minimax: {
    id: 'minimax',
    label: 'MiniMax',
    color: '1F1E33',
    logoUrl: minimaxIcon,
  },
  moonshot: {
    id: 'moonshot',
    label: 'Moonshot',
    color: '1C1C1E',
    logoUrl: moonshotIcon,
  },
  zhipuai: {
    id: 'zhipuai',
    label: 'Zhipu AI',
    color: '2B60D6',
    logoUrl: zhipuIcon,
  },
  kimi_code: {
    id: 'kimi_code',
    label: 'Kimi Code',
    color: '1C1C1E',
    logoUrl: kimiIcon,
  },
  bailian_token: {
    id: 'bailian_token',
    label: 'Bailian Token Plan',
    color: 'FF6A00',
    logoUrl: bailianIcon,
  },
  bailian_coding: {
    id: 'bailian_coding',
    label: 'Bailian Coding Plan',
    color: 'FF6A00',
    logoUrl: bailianIcon,
  },
  tencent_token: {
    id: 'tencent_token',
    label: 'Tencent Cloud Token Plan',
    color: '0052D9',
    logoUrl: tencentcloudIcon,
  },
  tencent_coding: {
    id: 'tencent_coding',
    label: 'Tencent Cloud Coding Plan',
    color: '0052D9',
    logoUrl: tencentcloudIcon,
  },
  glm_coding: {
    id: 'glm_coding',
    label: 'GLM Coding Plan',
    color: '2B60D6',
    logoUrl: zhipuIcon,
  },
  volcengine_agent: {
    id: 'volcengine_agent',
    label: 'Volcengine Agent Plan',
    color: '1664FF',
    logoUrl: volcengineIcon,
  },
  volcengine_coding: {
    id: 'volcengine_coding',
    label: 'Volcengine Coding Plan',
    color: '1664FF',
    logoUrl: volcengineIcon,
  },
  openrouter: {
    id: 'openrouter',
    label: 'OpenRouter',
    color: '6467F2',
    logoUrl: openrouterIcon,
  },
  vllm: {
    id: 'vllm',
    label: 'vLLM',
    color: '30A2FF',
    logoUrl: vllmIcon,
  },
  sglang: {
    id: 'sglang',
    label: 'SGLang',
    color: 'E05A2B',
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
    logoUrl: ollamaIcon,
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
    logoUrl: bedrockIcon,
  },
  xiaomi_mimo: {
    id: 'xiaomi_mimo',
    label: 'Xiaomi MiMo',
    color: 'FF6900',
    logoUrl: xiaomimimoIcon,
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
