import { describe, expect, it } from 'vitest';
import { applyAssistantFormPatch } from './formPatch';

describe('MiMo assistant form patches', () => {
  it.each(['mimo-v2.6-flash', 'mimo-v2.6-pro', 'mimo-v2.6-pro-ultraspeed'])(
    'accepts %s as a model selection', (model) => {
      expect(applyAssistantFormPatch({}, { mimo_model: model })).toEqual({ mimo_model: model });
    },
  );

  it('ignores retired and unknown models', () => {
    expect(applyAssistantFormPatch({}, { mimo_model: 'mimo-v2.5' })).toEqual({});
    expect(applyAssistantFormPatch({}, { mimo_model: 'unknown-model' })).toEqual({});
  });
});
