"use client";

import { useEffect, useRef } from "react";

import { useImports } from "@/context/ImportsContext";

/** Call `reload` whenever an import finishes (not on mount). */
export function useReloadOnImport(reload: () => void) {
  const { finishedCount } = useImports();
  const seen = useRef(finishedCount);
  useEffect(() => {
    if (finishedCount === seen.current) return;
    seen.current = finishedCount;
    reload();
  }, [finishedCount, reload]);
}
