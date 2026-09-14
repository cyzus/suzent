interface DirectStreamCompletion {
  isSelected: () => boolean;
  ownsStream: () => boolean;
  loadHistory: () => Promise<void>;
  clearChatStreaming: () => void;
  clearTransient: () => void;
  clearSeed: () => void;
}

/** Completion must not navigate, or clear a newer chat's streaming UI. */
export async function completeDirectStream(completion: DirectStreamCompletion): Promise<void> {
  let completed = false;
  try {
    if (completion.isSelected()) await completion.loadHistory();
    completed = true;
  } finally {
    completion.clearChatStreaming();
    if (completed && completion.ownsStream()) completion.clearTransient();
    completion.clearSeed();
  }
}
