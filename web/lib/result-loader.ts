const MIN_CACHED_RESULT_SECONDS = 10;
const MAX_CACHED_RESULT_SECONDS = 20;

export function cachedResultLoaderDurationMs(randomValue = Math.random()): number {
  const normalized = Math.min(Math.max(randomValue, 0), 0.999999999999);
  const seconds =
    MIN_CACHED_RESULT_SECONDS +
    Math.floor(normalized * (MAX_CACHED_RESULT_SECONDS - MIN_CACHED_RESULT_SECONDS + 1));
  return seconds * 1000;
}

export function remainingResultLoaderDelayMs(
  startedAtMs: number,
  targetDurationMs: number,
  nowMs = Date.now(),
): number {
  return Math.max(0, targetDurationMs - (nowMs - startedAtMs));
}
