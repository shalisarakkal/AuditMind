/** OS file drags expose Files during dragover; files are readable on drop. */
export function isFileDrop(event: Pick<DragEvent, "dataTransfer">): boolean {
  return !!event.dataTransfer && (
    Array.from(event.dataTransfer.types ?? []).includes("Files") || (event.dataTransfer.files?.length ?? 0) > 0
  );
}
