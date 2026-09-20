/**
 * Utility pure formatting functions
 */

export function formatBytes(value) {
  if (value === null || value === undefined) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

export function formatSpeed(bytesPerSec) {
  if (!bytesPerSec || bytesPerSec <= 0) return "";
  const mbps = (bytesPerSec / (1024 * 1024)).toFixed(2);
  return `${mbps} MB/s`;
}

export function formatTime(value) {
  if (!value) return "-";
  return new Date(value * 1000).toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeAgo(timestamp) {
  if (!timestamp) return "";
  const seconds = Math.floor(Date.now() / 1000 - timestamp);
  if (seconds < 60) return "Poco fa";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m fa`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h fa`;
  const days = Math.floor(hours / 24);
  return `${days}gg fa`;
}

export function formatProgress(value) {
  if (value === null || value === undefined) return "-";
  return `${value.toFixed(1)}%`;
}
