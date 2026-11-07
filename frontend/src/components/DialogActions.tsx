/** Shared dialog actions: dismissal first, primary action last. */
export const DIALOG_BUTTON_BASE = "min-h-10 rounded-md px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan disabled:cursor-not-allowed disabled:opacity-50";
export const DIALOG_NEUTRAL = `${DIALOG_BUTTON_BASE} border border-white/20 text-white/80 hover:bg-white/10`;
export const DIALOG_PRIMARY = `${DIALOG_BUTTON_BASE} border border-cyan bg-cyan font-medium text-navy hover:opacity-90`;
export const DIALOG_SECONDARY = `${DIALOG_BUTTON_BASE} border border-cyan text-cyan hover:bg-cyan/10`;
export const DIALOG_DANGER = `${DIALOG_BUTTON_BASE} border border-red-400 bg-red-400/80 font-medium text-navy hover:opacity-90`;
export const DIALOG_ICON = "flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-white/70 hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan disabled:cursor-not-allowed disabled:opacity-50";
export const DIALOG_FOOTER = "mt-4 flex flex-col gap-3 border-t border-white/15 pt-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end";
