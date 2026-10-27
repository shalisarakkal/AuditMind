"use client";

import { useId, useState, type InputHTMLAttributes } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: string;
  /** A new handover must not inherit visibility from the previous secret. */
  resetOn?: object;
  containerClassName?: string;
};

/** Visibility is local to this field; never stored or sent to the server. */
export default function PasswordInput({ label, resetOn, containerClassName = "", id, className = "", disabled, ...props }: Props) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const [visibility, setVisibility] = useState({ shown: false, resetOn });
  const shown = visibility.shown && visibility.resetOn === resetOn;
  return <div className={`relative min-w-0 ${containerClassName}`}>
    <input {...props} id={inputId} type={shown ? "text" : "password"} disabled={disabled}
      spellCheck={false} autoCapitalize="none" autoCorrect="off"
      className={`${className} pr-16`} />
    <button type="button" disabled={disabled} aria-controls={inputId}
      aria-label={`${shown ? "Hide" : "Show"} ${label.toLowerCase()}`}
      onClick={() => setVisibility({ shown: !shown, resetOn })}
      className="absolute inset-y-0 right-0 min-h-11 w-16 rounded-r-md text-sm font-medium text-cyan hover:bg-cyan/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan disabled:opacity-50">
      {shown ? "Hide" : "Show"}
    </button>
  </div>;
}
