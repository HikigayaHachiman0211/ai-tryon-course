export interface AssistantPublicConfig {
  enabled: boolean;
  welcome_message: string;
  features: {
    text_chat: boolean;
    auto_fill: boolean;
    auto_submit: boolean;
    style_lab_guide: boolean;
    tryon_guide: boolean;
  };
  defaults: {
    ai_provider: string;
    mimo_model: string;
  };
}

export interface RecommendFormPatch {
  color_preference?: string;
  brand_preference?: string;
  gender?: string;
  price_min?: number | null;
  price_max?: number | null;
  mbti?: string;
  size?: string;
  style_preference?: string;
  ai_provider?: string;
  vision_provider?: string;
  mimo_model?: string;
  gemini_model?: string;
  deepseek_model?: string;
}

export interface AssistantAction {
  type: string;
  form_patch?: RecommendFormPatch;
  confidence?: number;
  requires_confirmation?: boolean;
}

export interface AssistantDebugInfo {
  provider: string;
  fallback_used: boolean;
  latency_ms: number;
}

export interface AssistantChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  action?: AssistantAction;
  intent?: string;
  debug?: AssistantDebugInfo;
  timestamp: number;
}

export interface AssistantChatResponse {
  reply: string;
  intent: string;
  action: AssistantAction;
  sources: string[];
  debug: AssistantDebugInfo;
}
