"use client";

import React from "react";
import { useScrollReveal } from "@/lib/useScrollReveal";
import { cn } from "@/lib/cn";

interface ScrollRevealProps {
  children: React.ReactNode;
  className?: string;
  variant?: "fade-up" | "scale" | "fade";
  delay?: 0 | 1 | 2 | 3 | 4 | 5 | 6;
}

const variantClass = {
  "fade-up": "reveal",
  scale: "reveal-scale",
  fade: "reveal-fade",
} as const;

export default function ScrollReveal({
  children,
  className,
  variant = "fade-up",
  delay = 0,
}: ScrollRevealProps) {
  const ref = useScrollReveal<HTMLDivElement>();

  return (
    <div
      ref={ref}
      className={cn(variantClass[variant], `stagger-${delay}`, className)}
    >
      {children}
    </div>
  );
}
