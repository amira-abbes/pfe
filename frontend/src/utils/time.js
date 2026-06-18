export function formatRemainingTime(seconds) {
  const safeSeconds = Math.max(0, Math.ceil(Number(seconds) || 0));

  if (safeSeconds <= 60) {
    return `${safeSeconds} s`;
  }

  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = safeSeconds % 60;
  return `${minutes} min ${String(remainingSeconds).padStart(2, "0")} s`;
}

export function parseRemainingTime(value) {
  if (!value || typeof value !== "string") return 0;

  const parts = value.split(":").map(Number);
  if (parts.length !== 2 || parts.some((part) => !Number.isFinite(part))) {
    return 0;
  }

  return Math.max(0, parts[0] * 60 + parts[1]);
}
