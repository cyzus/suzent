import { describe, expect, it } from 'vitest';
import {
  forgetRegentReturnUnless,
  getOpenedFromRegent,
  markOpenedFromRegent,
  unmarkOpenedFromRegent,
} from './regentReturn';

describe('way back to Regent', () => {
  it('stays while the chat opened from the board is current', () => {
    markOpenedFromRegent('chat-a');
    forgetRegentReturnUnless('chat-a');
    expect(getOpenedFromRegent()).toBe('chat-a');
  });

  it('is forgotten once another chat opens', () => {
    markOpenedFromRegent('chat-a');
    forgetRegentReturnUnless('chat-b');
    expect(getOpenedFromRegent()).toBeNull();
  });

  it('is taken back when the chat fails to open, leaving any other mark alone', () => {
    markOpenedFromRegent('chat-a');
    unmarkOpenedFromRegent('chat-b');
    expect(getOpenedFromRegent()).toBe('chat-a');
    unmarkOpenedFromRegent('chat-a');
    expect(getOpenedFromRegent()).toBeNull();
  });
});
