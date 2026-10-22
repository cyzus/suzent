import type { A2UISurface } from '../types/a2ui';

/**
 * Turn a submitted question form into the message the user sends.
 *
 * Regent's question forms outlive the turn that asked them, so their answer
 * arrives as an ordinary message. The form's fields are named by their
 * question, which lets the message read as "question: answer".
 */
export function formatQuestionAnswer(context: Record<string, unknown>): string {
  if (typeof context.button_label === 'string' && context.button_label.trim()) {
    return context.button_label.trim();
  }
  return Object.entries(context)
    .filter(([key]) => key !== 'button_label' && key !== 'surface_id')
    .map(([question, value]) => {
      const answer = Array.isArray(value) ? value.join(', ') : String(value ?? '').trim();
      return `${question}: ${answer}`;
    })
    .join('\n');
}

/** A question form the user has since replied to, so it should not be offered again. */
export function isAnsweredQuestion(surface: A2UISurface, repliedTo: boolean): boolean {
  return (
    repliedTo && surface.component.type === 'form' && surface.component.action === 'submit_question'
  );
}
