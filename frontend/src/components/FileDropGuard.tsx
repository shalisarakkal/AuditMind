"use client";

import { useEffect } from "react";

import { isFileDrop } from "@/lib/fileDrop";

/** Prevent the browser's file-open default, including outside upload targets.
 * Capture does not stop propagation: the page's uploader still receives drops.
 */
export default function FileDropGuard() {
  useEffect(() => {
    const preventFileNavigation = (event: DragEvent) => {
      // Native file inputs safely consume files themselves (Documents/logos).
      if (event.target instanceof HTMLInputElement && event.target.type === "file") return;
      if (isFileDrop(event)) event.preventDefault();
    };
    document.addEventListener("dragover", preventFileNavigation, true);
    document.addEventListener("drop", preventFileNavigation, true);
    return () => {
      document.removeEventListener("dragover", preventFileNavigation, true);
      document.removeEventListener("drop", preventFileNavigation, true);
    };
  }, []);
  return null;
}
