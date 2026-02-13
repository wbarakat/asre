/**
 * Stub components that map Mintlify-specific MDX components to plain HTML.
 * These are passed into the MDX components map so that <Note>, <Warning>, etc.
 * render correctly without the Mintlify runtime.
 */
import React from "react";

/* ------------------------------------------------------------------ */
/* Callout boxes: Note, Warning, Info, Tip, Check                     */
/* ------------------------------------------------------------------ */

function Callout({
  children,
  variant,
}: {
  children: React.ReactNode;
  variant: "note" | "warning" | "info" | "tip" | "check";
}) {
  const styles: Record<string, { border: string; bg: string; label: string }> =
    {
      note: {
        border: "border-blue-500/40",
        bg: "bg-blue-500/10",
        label: "Note",
      },
      info: {
        border: "border-blue-500/40",
        bg: "bg-blue-500/10",
        label: "Info",
      },
      tip: {
        border: "border-green-500/40",
        bg: "bg-green-500/10",
        label: "Tip",
      },
      check: {
        border: "border-green-500/40",
        bg: "bg-green-500/10",
        label: "Check",
      },
      warning: {
        border: "border-yellow-500/40",
        bg: "bg-yellow-500/10",
        label: "Warning",
      },
    };

  const s = styles[variant] ?? styles.note;

  return (
    <div
      className={`my-4 rounded-md border-l-4 ${s.border} ${s.bg} px-4 py-3`}
    >
      <p className="mb-1 text-sm font-semibold text-zinc-300">{s.label}</p>
      <div className="text-sm text-zinc-300">{children}</div>
    </div>
  );
}

export function Note({ children }: { children: React.ReactNode }) {
  return <Callout variant="note">{children}</Callout>;
}
export function Info({ children }: { children: React.ReactNode }) {
  return <Callout variant="info">{children}</Callout>;
}
export function Tip({ children }: { children: React.ReactNode }) {
  return <Callout variant="tip">{children}</Callout>;
}
export function Check({ children }: { children: React.ReactNode }) {
  return <Callout variant="check">{children}</Callout>;
}
export function Warning({ children }: { children: React.ReactNode }) {
  return <Callout variant="warning">{children}</Callout>;
}

/* ------------------------------------------------------------------ */
/* Cards                                                               */
/* ------------------------------------------------------------------ */

export function Card({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
  [key: string]: unknown;
}) {
  return (
    <div className="my-2 rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
      {title && (
        <p className="mb-1 text-sm font-semibold text-white">{title}</p>
      )}
      <div className="text-sm text-zinc-300">{children}</div>
    </div>
  );
}

export function CardGroup({
  children,
}: {
  children: React.ReactNode;
  [key: string]: unknown;
}) {
  return (
    <div className="my-4 grid gap-4 sm:grid-cols-2">{children}</div>
  );
}

/* ------------------------------------------------------------------ */
/* Code groups / Tabs                                                  */
/* ------------------------------------------------------------------ */

export function CodeGroup({ children }: { children: React.ReactNode }) {
  return <div className="my-4 space-y-2">{children}</div>;
}

export function Tabs({ children }: { children: React.ReactNode }) {
  return <div className="my-4 space-y-2">{children}</div>;
}

export function Tab({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4">
      {title && (
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
          {title}
        </p>
      )}
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Steps                                                               */
/* ------------------------------------------------------------------ */

export function Steps({ children }: { children: React.ReactNode }) {
  return (
    <div className="my-4 space-y-4 border-l-2 border-zinc-700 pl-6">
      {children}
    </div>
  );
}

export function Step({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      {title && (
        <p className="mb-1 text-sm font-semibold text-white">{title}</p>
      )}
      <div className="text-sm text-zinc-300">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Accordion                                                           */
/* ------------------------------------------------------------------ */

export function AccordionGroup({ children }: { children: React.ReactNode }) {
  return <div className="my-4 space-y-2">{children}</div>;
}

export function Accordion({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <details className="group rounded-lg border border-zinc-700 bg-zinc-800/50">
      <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-white">
        {title ?? "Details"}
      </summary>
      <div className="px-4 pb-3 text-sm text-zinc-300">{children}</div>
    </details>
  );
}

/* ------------------------------------------------------------------ */
/* Collected export map for MDX                                        */
/* ------------------------------------------------------------------ */

export const mintlifyComponents = {
  Note,
  Info,
  Tip,
  Check,
  Warning,
  Card,
  CardGroup,
  CodeGroup,
  Tabs,
  Tab,
  Steps,
  Step,
  AccordionGroup,
  Accordion,
};
