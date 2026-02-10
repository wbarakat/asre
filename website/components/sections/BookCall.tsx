"use client";

import { useEffect, useState } from "react";
import { BOOK_CALL, CALENDLY_URL } from "@/lib/constants";

export default function BookCall() {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "https://assets.calendly.com/assets/external/widget.css";
    document.head.appendChild(link);

    const script = document.createElement("script");
    script.src = "https://assets.calendly.com/assets/external/widget.js";
    script.async = true;
    script.onload = () => setLoaded(true);
    document.head.appendChild(script);

    return () => {
      if (link.parentNode) link.parentNode.removeChild(link);
      if (script.parentNode) script.parentNode.removeChild(script);
    };
  }, []);

  return (
    <section id="about" className="section-light py-24 md:py-32">
      <div className="max-w-4xl mx-auto px-6">
        <p className="text-primary font-medium text-sm uppercase tracking-widest text-center mb-4">
          Get Started
        </p>
        <h2 className="text-3xl md:text-5xl font-bold text-center text-navy mb-4">
          {BOOK_CALL.heading}
        </h2>
        <p className="text-navy-100 text-center text-lg mb-12 max-w-2xl mx-auto">
          {BOOK_CALL.description}
        </p>

        <div
          className="calendly-inline-widget"
          data-url={`${CALENDLY_URL}?hide_gdpr_banner=1`}
          style={{ minWidth: 320, height: 1000, width: "100%" }}
        />
      </div>
    </section>
  );
}
