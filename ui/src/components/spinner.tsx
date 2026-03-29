"use client";

type SpinnerProps = {
  size?: "sm" | "md" | "lg";
  className?: string;
};

const SIZE_MAP = {
  sm: "h-4 w-4 border-2",
  md: "h-5 w-5 border-2",
  lg: "h-7 w-7 border-[3px]"
};

export function Spinner({ size = "md", className = "" }: SpinnerProps) {
  return (
    <span
      aria-label="Loading"
      className={`inline-block animate-spin rounded-full border-slate-300 border-t-brand-500 ${SIZE_MAP[size]} ${className}`}
      role="status"
    />
  );
}
