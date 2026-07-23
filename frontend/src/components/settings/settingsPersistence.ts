export function closeImmediatelyAndPersist(
  onClose: () => void,
  persist: () => Promise<void>,
  onError: (error: unknown) => void,
): void {
  onClose();

  globalThis.setTimeout(() => {
    void persist().catch(onError);
  }, 0);
}
