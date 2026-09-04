export interface PrependScrollSnapshot {
  scrollHeight: number;
  scrollTop: number;
  anchorMessageIndex: number | null;
  anchorViewportOffset: number;
}

export function capturePrependScrollSnapshot(el: HTMLDivElement): PrependScrollSnapshot {
  const containerTop = el.getBoundingClientRect().top;
  const rows = Array.from(el.querySelectorAll<HTMLElement>('[data-message-index]'));
  const anchorRow = rows.find((row) => row.getBoundingClientRect().bottom > containerTop);

  return {
    scrollHeight: el.scrollHeight,
    scrollTop: el.scrollTop,
    anchorMessageIndex: anchorRow ? Number(anchorRow.dataset.messageIndex) : null,
    anchorViewportOffset: anchorRow ? anchorRow.getBoundingClientRect().top - containerTop : 0,
  };
}

export function restorePrependScrollSnapshot(
  el: HTMLDivElement,
  snapshot: PrependScrollSnapshot
): void {
  if (snapshot.anchorMessageIndex !== null) {
    const anchorRow = el.querySelector<HTMLElement>(
      `[data-message-index="${snapshot.anchorMessageIndex}"]`
    );
    if (anchorRow) {
      const containerTop = el.getBoundingClientRect().top;
      const currentOffset = anchorRow.getBoundingClientRect().top - containerTop;
      el.scrollTop += currentOffset - snapshot.anchorViewportOffset;
      return;
    }
  }

  // The anchor can disappear if the conversation changes during the prepend.
  // Retain the old height-delta behavior as a safe fallback.
  el.scrollTop = el.scrollHeight - snapshot.scrollHeight + snapshot.scrollTop;
}
