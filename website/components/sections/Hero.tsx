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
      <span className="text-accent">{phrase}</span>
      {after}
    </>
  );
}

export default function Hero() {
  return (
    <section className="section-black min-h-screen flex items-center justify-center relative overflow-hidden">
      {/* Subtle accent glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-accent/[0.07] rounded-full blur-[150px] pointer-events-none" />

      <div className="max-w-4xl mx-auto text-center px-6 relative z-10 pt-24">
        <p className="font-serif italic text-white/70 text-base md:text-lg mb-6 animate-fade-up">
          Admission Signal Reliability Engine
        </p>

        <h1 className="font-serif text-5xl md:text-7xl lg:text-[5.5rem] text-white leading-[1.1] tracking-tight animate-fade-up animate-delay-100">
          {renderHeadline(HERO.headline, HERO.highlightedPhrase)}
        </h1>

        <p className="text-xl md:text-2xl text-white/90 max-w-2xl mx-auto mt-8 leading-relaxed animate-fade-up animate-delay-200">
          {HERO.subheadline}
        </p>

        <div className="flex flex-wrap gap-4 justify-center mt-10 animate-fade-up animate-delay-300">
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
