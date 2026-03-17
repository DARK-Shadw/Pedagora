const pendingFiles = new Map<string, File>();

export function setPendingFile(id: string, file: File) {
  pendingFiles.set(id, file);
}

export function getPendingFile(id: string) {
  return pendingFiles.get(id);
}

export function removePendingFile(id: string) {
  pendingFiles.delete(id);
}

export function getAllPendingFiles() {
  return pendingFiles;
}

export function clearPendingFiles() {
  pendingFiles.clear();
}
