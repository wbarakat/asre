import React from "react";
import { HERO, CALENDLY_URL } from "@/lib/constants";
import Button from "@/components/ui/Button";

function renderHeadline(headline: string, phrase: string): React.ReactNode {
  const index = headline.indexOf(phrase);
  if (index === -1) return headline;

  const before = headline.slice(0, index);
  const after = headline.slice(index + phrase.length);

  return (
    <>
      {before}
      <span className="text-primary">{phrase}</span>
      {after}
    </>
  );
}

export default function Hero() {
  return (
    <section className="section-blue min-h-screen flex items-center justify-center relative overflow-hidden">
      {/* Soft decorative blobs */}
      <div className="absolute top-20 right-[10%] w-[500px] h-[500px] bg-primary-200/40 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-20 left-[15%] w-[400px] h-[400px] bg-indigo-200/30 rounded-full blur-[100px] pointer-events-none" />

      <div className="max-w-4xl mx-auto text-center px-6 relative z-10 pt-24">
        <p className="text-primary font-medium text-sm uppercase tracking-widest mb-6 animate-slide-up">
          Admission Signal Reliability Engine
        </p>

        <h1 className="text-5xl md:text-7xl lg:text-8xl font-bold tracking-tight text-navy animate-slide-up animate-delay-100">
          {renderHeadline(HERO.headline, HERO.highlightedPhrase)}
        </h1>

        <p className="text-lg md:text-xl text-navy-100 max-w-2xl mx-auto mt-6 leading-relaxed animate-slide-up animate-delay-200">
          {HERO.subheadline}
        </p>

        <div className="flex flex-wrap gap-4 justify-center mt-10 animate-slide-up animate-delay-300">
          <Button variant="primary" size="lg" href={CALENDLY_URL}>
            {HERO.ctaPrimary}
          </Button>
          <Button variant="secondary" size="lg" href={HERO.whitepaperUrl}>
            {HERO.ctaSecondary}
          </Button>
        </div>
      </div>
    </section>
  );
}
