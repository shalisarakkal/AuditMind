"use client";

import { useEffect, useRef } from "react";

/** One attempt after visible, unhovered, unfocused time; failures require manual retry. */
export function useVisibleAutoDismiss(enabled: boolean, identity: string, onDismiss: () => void, delay = 10000) {
  const element = useRef<HTMLElement>(null);
  const latest = useRef(onDismiss);
  useEffect(() => { latest.current = onDismiss; }, [onDismiss]);
  useEffect(() => {
    const node = element.current;
    if (!enabled || !node || typeof IntersectionObserver === "undefined") return;
    let remaining = delay, started: number | null = null, timer: number | undefined;
    let visible = false, hovered = node.matches(":hover"), focused = node.contains(document.activeElement), attempted = false;
    function pause() {
      if (timer !== undefined) window.clearTimeout(timer);
      timer = undefined;
      if (started !== null) remaining = Math.max(0, remaining - (Date.now() - started));
      started = null;
    }
    function update() {
      pause();
      if (attempted || !visible || document.visibilityState !== "visible" || hovered || focused) return;
      started = Date.now();
      timer = window.setTimeout(() => { attempted = true; started = null; timer = undefined; latest.current(); }, remaining);
    }
    const observer = new IntersectionObserver(entries => { visible = entries.some(entry => entry.isIntersecting); update(); });
    const enter = () => { hovered = true; update(); };
    const leave = () => { hovered = false; update(); };
    const focusIn = () => { focused = true; update(); };
    const focusOut = (event: FocusEvent) => { focused = event.relatedTarget instanceof Node && node!.contains(event.relatedTarget); update(); };
    observer.observe(node);
    node.addEventListener("mouseenter", enter); node.addEventListener("mouseleave", leave);
    node.addEventListener("focusin", focusIn); node.addEventListener("focusout", focusOut);
    document.addEventListener("visibilitychange", update);
    return () => {
      pause(); observer.disconnect();
      node.removeEventListener("mouseenter", enter); node.removeEventListener("mouseleave", leave);
      node.removeEventListener("focusin", focusIn); node.removeEventListener("focusout", focusOut);
      document.removeEventListener("visibilitychange", update);
    };
  }, [enabled, identity, delay]);
  return element;
}
