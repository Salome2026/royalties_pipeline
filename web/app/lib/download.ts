export function filenameFromDisposition(disposition: string | null, fallback: string) {
  if (!disposition) return fallback;
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return match?.[1] || fallback;
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
