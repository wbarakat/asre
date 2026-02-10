import React from "react";
import { PAIN_POINTS } from "@/lib/constants";
import Card from "@/components/ui/Card";

export default function PainPoints() {
  return (
    <section id="features" className="section-white py-24 md:py-32">
      <div className="max-w-7xl mx-auto px-6">
        <p className="text-primary font-medium text-sm uppercase tracking-widest text-center mb-4">
          The Problem
        </p>
        <h2 className="text-3xl md:text-5xl font-bold text-center text-navy mb-4">
          The Reliability Challenge
        </h2>
        <p className="text-navy-100 text-center text-lg mb-16 max-w-2xl mx-auto">
          Why healthcare operations can&apos;t rely on raw admission signals
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {PAIN_POINTS.map((point) => (
            <Card key={point.title}>
              <div className="font-mono text-3xl md:text-4xl text-primary font-bold">
                {point.stat}
              </div>
              <div className="text-xs text-navy-100/60 uppercase tracking-wider mt-1">
                {point.statLabel}
              </div>
              <h3 className="text-lg font-semibold text-navy mt-4">
                {point.title}
              </h3>
              <p className="text-navy-100 text-sm mt-2 leading-relaxed">
                {point.description}
              </p>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}
