"use client";

import React from "react";
import { PAIN_POINTS } from "@/lib/constants";
import Card from "@/components/ui/Card";
import ScrollReveal from "@/components/ui/ScrollReveal";

export default function PainPoints() {
  return (
    <section id="features" className="section-dark py-24 md:py-32">
      <div className="max-w-7xl mx-auto px-6">
        <ScrollReveal>
          <p className="text-accent font-medium text-sm uppercase tracking-widest text-center mb-4">
            The Problem
          </p>
          <h2 className="font-serif text-3xl md:text-5xl text-white text-center mb-4">
            The Reliability Challenge
          </h2>
          <p className="text-white/90 text-center text-lg md:text-xl mb-16 max-w-2xl mx-auto">
            Why healthcare operations can&apos;t rely on raw admission signals
          </p>
        </ScrollReveal>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {PAIN_POINTS.map((point, i) => (
            <ScrollReveal key={point.title} delay={i as 0 | 1 | 2 | 3}>
              <Card>
                <div className="font-mono text-3xl md:text-4xl text-accent font-bold">
                  {point.stat}
                </div>
                <div className="text-xs text-white/70 uppercase tracking-wider mt-1">
                  {point.statLabel}
                </div>
                <h3 className="text-lg font-semibold text-white mt-4">
                  {point.title}
                </h3>
                <p className="text-white/90 text-sm mt-2 leading-relaxed">
                  {point.description}
                </p>
              </Card>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  );
}
