import type {
  ProductCatalogItem,
  RecommendFormPatch,
  RecommendationRequest,
  RecommendationResponse,
  TryOnHandoffPayload,
} from '../types/api';
import { applyAssistantFormPatch } from '../utils/formPatch';
import { getStorageItem, setStorageItem, STORAGE_KEYS } from '../utils/storage';

export interface UserPhotoState {
  localPath: string;
  previewUrl: string;
  sampleModelId: string | null;
  remoteUrl: string;
}

export interface LastTryOnResultState {
  relativePath: string;
  displayUrl: string;
  width?: number;
  height?: number;
}

export interface AppStoreState {
  profileForm: RecommendationRequest;
  userPhoto: UserPhotoState;
  lastRecommendResult: RecommendationResponse | null;
  pendingAutoRecommend: boolean;
  activeStyleLabProduct: ProductCatalogItem | null;
  pendingTryOnHandoff: TryOnHandoffPayload | null;
  lastTryOnResult: LastTryOnResultState | null;
}

const DEFAULT_PROFILE: RecommendationRequest = {
  color_preference: '',
  gender: '',
};

const savedDraft = getStorageItem<Partial<RecommendationRequest>>(STORAGE_KEYS.profileDraft);

const state: AppStoreState = {
  profileForm: {
    ...DEFAULT_PROFILE,
    ...(savedDraft && typeof savedDraft === 'object' ? savedDraft : {}),
  },
  userPhoto: {
    localPath: '',
    previewUrl: '',
    sampleModelId: null,
    remoteUrl: '',
  },
  lastRecommendResult: null,
  pendingAutoRecommend: false,
  activeStyleLabProduct: null,
  pendingTryOnHandoff: null,
  lastTryOnResult: null,
};

type StoreListener = (snapshot: AppStoreState) => void;
const listeners = new Set<StoreListener>();

function emit(): void {
  const snap = getState();
  listeners.forEach((fn) => {
    try {
      fn(snap);
    } catch {
      // Ignore subscriber failure
    }
  });
}

export function getState(): AppStoreState {
  return {
    ...state,
    profileForm: { ...state.profileForm },
    userPhoto: { ...state.userPhoto },
  };
}

export function subscribeStore(fn: StoreListener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function updateProfileForm(partial: Partial<RecommendationRequest>): RecommendationRequest {
  state.profileForm = {
    ...state.profileForm,
    ...partial,
  };
  setStorageItem(STORAGE_KEYS.profileDraft, state.profileForm);
  emit();
  return { ...state.profileForm };
}

export function applyFormPatchToStore(patch: RecommendFormPatch, autoSubmit = false): RecommendationRequest {
  const merged = applyAssistantFormPatch(
    state.profileForm as unknown as Record<string, unknown>,
    patch,
  ) as unknown as RecommendationRequest;
  state.profileForm = {
    ...merged,
    color_preference: merged.color_preference || '',
  };
  setStorageItem(STORAGE_KEYS.profileDraft, state.profileForm);
  if (autoSubmit) {
    state.pendingAutoRecommend = true;
  }
  emit();
  return { ...state.profileForm };
}

export function consumePendingAutoRecommend(): boolean {
  const pending = state.pendingAutoRecommend;
  state.pendingAutoRecommend = false;
  return pending;
}

export function setUserPhoto(photo: Partial<UserPhotoState>): UserPhotoState {
  state.userPhoto = {
    ...state.userPhoto,
    ...photo,
  };
  emit();
  return { ...state.userPhoto };
}

export function clearUserPhoto(): void {
  state.userPhoto = {
    localPath: '',
    previewUrl: '',
    sampleModelId: null,
    remoteUrl: '',
  };
  emit();
}

export function setLastRecommendResult(res: RecommendationResponse | null): void {
  state.lastRecommendResult = res;
  emit();
}

export function setActiveStyleLabProduct(product: ProductCatalogItem | null): void {
  state.activeStyleLabProduct = product;
  emit();
}

export function setPendingTryOnHandoff(payload: TryOnHandoffPayload | null): void {
  state.pendingTryOnHandoff = payload;
  emit();
}

export function consumePendingTryOnHandoff(): TryOnHandoffPayload | null {
  const payload = state.pendingTryOnHandoff;
  state.pendingTryOnHandoff = null;
  return payload;
}

export function setLastTryOnResult(res: LastTryOnResultState | null): void {
  state.lastTryOnResult = res;
  emit();
}
