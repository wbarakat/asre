"use client";

import React from "react";
import { COMPARISON_ROWS } from "@/lib/constants";
import ScrollReveal from "@/components/ui/ScrollReveal";

function CheckIcon() {
  return (
    <svg className="w-5 h-5 text-status-yes" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg className="w-5 h-5 text-white/20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

function PartialIcon() {
  return (
    <svg className="w-5 h-5 text-status-partial" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14" />
    </svg>
  );
}

function StatusIcon({ status }: { status: "yes" | "no" | "partial" }) {
  if (status === "yes") return <CheckIcon />;
  if (status === "partial") return <PartialIcon />;
  return <XIcon />;
}

export default function Comparison() {
  return (
    <section id="compare" className="section-dark-alt py-24 md:py-32">
      <div className="max-w-5xl mx-auto px-6">
        <ScrollReveal>
          <p className="text-accent font-medium text-sm uppercase tracking-widest text-center mb-4">
            Why ASRE
          </p>
          <h2 className="font-serif text-3xl md:text-5xl text-white text-center mb-4">
            Replace Encounter SQL with a Fixed Pipeline
          </h2>
          <p className="text-white/90 text-center text-lg md:text-xl mb-16 max-w-2xl mx-auto">
            Teams often maintain custom SQL for encounter stitching. ASRE provides one defined pipeline for stitching, deduplication, reconciliation, and scoring.
          </p>
        </ScrollReveal>

        {/* Desktop table */}
        <ScrollReveal variant="scale" className="hidden md:block">
          <div className="rounded-2xl border border-white/[0.06] overflow-hidden">
            {/* Header */}
            <div className="grid grid-cols-[1fr_180px_180px] bg-dark-300">
              <div className="px-6 py-4" />
              <div className="px-6 py-4 text-center">
                <span className="text-sm font-semibold text-white/80">DIY SQL Pipeline</span>
              </div>
              <div className="px-6 py-4 text-center bg-accent/[0.06]">
                <span className="text-sm font-bold text-accent">ASRE</span>
              </div>
            </div>

            {/* Rows */}
            {COMPARISON_ROWS.map((row, i) => (
              <div
                key={row.feature}
                className={`grid grid-cols-[1fr_180px_180px] ${
                  i % 2 === 0 ? "bg-dark-100" : "bg-dark-200"
                } ${i < COMPARISON_ROWS.length - 1 ? "border-b border-white/[0.04]" : ""}`}
              >
                <div className="px-6 py-4">
                  <span className="text-sm font-medium text-white">{row.feature}</span>
                  {row.detail && (
                    <span className="block text-xs text-white/70 mt-0.5">{row.detail}</span>
                  )}
                </div>
                <div className="px-6 py-4 flex items-center justify-center">
                  <StatusIcon status={row.diy} />
                </div>
                <div className="px-6 py-4 flex items-center justify-center bg-accent/[0.03]">
                  <StatusIcon status={row.asre} />
                </div>
              </div>
            ))}
          </div>
        </ScrollReveal>

        {/* Mobile cards */}
        <div className="md:hidden space-y-3">
          {COMPARISON_ROWS.map((row) => (
            <ScrollReveal key={row.feature}>
              <div className="card-dark p-4">
                <div className="text-sm font-medium text-white mb-2">{row.feature}</div>
                {row.detail && (
                  <div className="text-xs text-white/70 mb-3">{row.detail}</div>
                )}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <StatusIcon status={row.diy} />
                    <span className="text-xs text-white/90">DIY SQL</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusIcon status={row.asre} />
                    <span className="text-xs font-medium text-accent">ASRE</span>
                  </div>
                </div>
              </div>
            </ScrollReveal>
          ))}
        </div>

      </div>
    </section>
  );
}
