import { describe, expect, it } from 'vitest';
import { formatQuestionAnswer, isAnsweredQuestion } from './questionAnswer';
import type { A2UISurface } from '../types/a2ui';

describe('formatQuestionAnswer', () => {
  it('reads as question and answer, one per line', () => {
    expect(
      formatQuestionAnswer({
        '用哪个配色？': '暖色',
        'Which days?': ['Mon', 'Wed'],
        surface_id: 'question_x',
      })
    ).toBe('用哪个配色？: 暖色\nWhich days?: Mon, Wed');
  });

  it('uses a clicked button label as the answer', () => {
    expect(formatQuestionAnswer({ button_label: 'Approve', note: 'x' })).toBe('Approve');
  });
});

describe('isAnsweredQuestion', () => {
  const surface = (action: string): A2UISurface => ({
    id: 'question_palette',
    component: { type: 'form', action, fields: [] } as unknown as A2UISurface['component'],
  });

  it('treats a question form as answered once the user has replied', () => {
    expect(isAnsweredQuestion(surface('submit_question'), true)).toBe(true);
    expect(isAnsweredQuestion(surface('submit_question'), false)).toBe(false);
  });

  it('leaves other forms alone', () => {
    expect(isAnsweredQuestion(surface('save_settings'), true)).toBe(false);
  });
});
