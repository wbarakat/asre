"use client";

import { MARKET_STATS, PRODUCT_STATS } from "@/lib/constants";
import ScrollReveal from "@/components/ui/ScrollReveal";

interface StatItem {
  readonly value: number;
  readonly prefix?: string;
  readonly suffix: string;
  readonly label: string;
  readonly decimals?: number;
}

function formatStat(stat: StatItem): string {
  const prefix = "prefix" in stat && stat.prefix ? stat.prefix : "";
  const decimals = "decimals" in stat && stat.decimals ? stat.decimals : 0;
  return `${prefix}${stat.value.toFixed(decimals)}${stat.suffix}`;
}

function StatGrid({ items }: { items: readonly StatItem[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
      {items.map((stat, i) => (
        <ScrollReveal key={stat.label} delay={i as 0 | 1 | 2}>
          <div className="text-center">
            <div className="font-mono text-5xl md:text-7xl font-bold text-white">
              {formatStat(stat)}
            </div>
            <p className="text-white/70 mt-2 uppercase tracking-wider text-sm">{stat.label}</p>
          </div>
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
            By the Numbers
          </p>
          <h2 className="font-serif text-3xl md:text-5xl text-white text-center mb-16">
            Market Context
          </h2>
        </ScrollReveal>
        <StatGrid items={MARKET_STATS} />

        <div className="divider my-20" />

        <ScrollReveal>
          <h2 className="font-serif text-3xl md:text-5xl text-white text-center mb-16">
            ASRE Performance
          </h2>
        </ScrollReveal>
        <StatGrid items={PRODUCT_STATS} />
      </div>
    </section>
  );
}
