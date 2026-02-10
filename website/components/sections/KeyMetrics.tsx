import { MARKET_STATS, PRODUCT_STATS } from "@/lib/constants";

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
      {items.map((stat) => (
        <div key={stat.label} className="text-center">
          <div className="font-mono text-5xl md:text-6xl font-bold text-navy">
            {formatStat(stat)}
          </div>
          <p className="text-navy-100 mt-2">{stat.label}</p>
        </div>
      ))}
    </div>
  );
}

export default function KeyMetrics() {
  return (
    <section id="metrics" className="section-light py-24 md:py-32">
      <div className="max-w-6xl mx-auto px-6">
        <p className="text-primary font-medium text-sm uppercase tracking-widest text-center mb-4">
          By the Numbers
        </p>
        <h2 className="text-3xl md:text-5xl font-bold text-center text-navy mb-16">
          Market Context
        </h2>
        <StatGrid items={MARKET_STATS} />

        <div className="my-20 border-t border-surface-200" />

        <h2 className="text-3xl md:text-5xl font-bold text-center text-navy mb-16">
          ASRE Performance
        </h2>
        <StatGrid items={PRODUCT_STATS} />
      </div>
    </section>
  );
}
