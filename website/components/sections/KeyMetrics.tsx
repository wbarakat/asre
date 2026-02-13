"use client";

import { VALUE_METRICS } from "@/lib/constants";
import ScrollReveal from "@/components/ui/ScrollReveal";
import Card from "@/components/ui/Card";

interface ValueMetric {
  readonly value: string;
  readonly label: string;
  readonly detail: string;
}

function ValueGrid({ items }: { items: readonly ValueMetric[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 items-stretch">
      {items.map((metric, i) => (
        <ScrollReveal key={metric.label} delay={i as 0 | 1 | 2 | 3} className="h-full">
          <Card className="h-full">
            <p className="font-mono text-3xl xl:text-4xl text-accent font-bold leading-[1.05] whitespace-nowrap">
              {metric.value}
            </p>
            <p className="text-white mt-3 text-lg font-semibold">{metric.label}</p>
            <p className="text-white/80 text-sm mt-2 leading-relaxed">{metric.detail}</p>
          </Card>
        </ScrollReveal>
      ))}
    </div>
  );
}

export default function KeyMetrics() {
  return (
    <section id="metrics" className="section-gradient-down py-24 md:py-32">
      <div className="max-w-6xl mx-auto px-6">
        <ScrollReveal>
          <p className="text-accent font-medium text-sm uppercase tracking-widest text-center mb-4">
            Value
          </p>
          <h2 className="font-serif text-3xl md:text-5xl text-white text-center mb-4">
            What Teams Usually Gain
          </h2>
          <p className="text-white/90 text-center text-lg md:text-xl mb-16 max-w-3xl mx-auto">
            Estimated impact ranges for time savings, data accuracy, and duplicate cleanup.
          </p>
        </ScrollReveal>
        <ValueGrid items={VALUE_METRICS} />
      </div>
    </section>
  );
}
