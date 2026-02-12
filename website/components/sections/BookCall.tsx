"use client";

import { useEffect, useCallback } from "react";
import { BOOK_CALL, CALENDLY_URL } from "@/lib/constants";
import Button from "@/components/ui/Button";
import ScrollReveal from "@/components/ui/ScrollReveal";

declare global {
  interface Window {
    Calendly?: {
      initPopupWidget: (opts: { url: string }) => void;
    };
  }
}

export default function BookCall() {
  useEffect(() => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "https://assets.calendly.com/assets/external/widget.css";
    document.head.appendChild(link);

    const script = document.createElement("script");
    script.src = "https://assets.calendly.com/assets/external/widget.js";
    script.async = true;
    document.head.appendChild(script);

    return () => {
      if (link.parentNode) link.parentNode.removeChild(link);
      if (script.parentNode) script.parentNode.removeChild(script);
    };
  }, []);

  const openCalendly = useCallback(() => {
    if (window.Calendly) {
      window.Calendly.initPopupWidget({
        url: `${CALENDLY_URL}?hide_gdpr_banner=1`,
      });
    } else {
      window.open(CALENDLY_URL, "_blank");
    }
  }, []);

  return (
    <section id="demo" className="section-black py-24 md:py-32 relative overflow-hidden">
      {/* Subtle accent glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-accent/[0.05] rounded-full blur-[150px] pointer-events-none" />

      <div className="max-w-4xl mx-auto px-6 relative z-10 text-center">
        <ScrollReveal>
          <p className="text-accent font-medium text-sm uppercase tracking-widest mb-4">
            Get Started
          </p>
          <h2 className="font-serif text-3xl md:text-5xl text-white mb-4">
            {BOOK_CALL.heading}
          </h2>
          <p className="text-white/90 text-lg md:text-xl mb-12 max-w-2xl mx-auto">
            {BOOK_CALL.description}
          </p>
        </ScrollReveal>

        <ScrollReveal delay={1}>
          <Button variant="primary" size="lg" onClick={openCalendly}>
            Book a Call
          </Button>
          <p className="text-white/60 text-sm mt-4">
            30-minute walkthrough — no commitment
          </p>
        </ScrollReveal>
      </div>
    </section>
  );
}
