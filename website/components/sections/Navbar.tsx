"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { cn } from "@/lib/cn";
import { BRAND, NAV_LINKS, CALENDLY_URL } from "@/lib/constants";
import Button from "@/components/ui/Button";

const SCROLL_THRESHOLD = 50;

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const leftLinks = NAV_LINKS.slice(0, 2);
  const rightLinks = NAV_LINKS.slice(2);

  const handleScroll = useCallback(() => {
    setScrolled(window.scrollY > SCROLL_THRESHOLD);
  }, []);

  useEffect(() => {
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [handleScroll]);

  useEffect(() => {
    function handleResize() {
      if (window.innerWidth >= 768) setMobileOpen(false);
    }
    window.addEventListener("resize", handleResize, { passive: true });
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [mobileOpen]);

  return (
    <div className="fixed top-0 left-0 right-0 z-50 px-4 md:px-6 pt-4">
      <nav
        className={cn(
          "max-w-5xl mx-auto rounded-full transition-all duration-300 border",
          scrolled
            ? "bg-white/[0.07] backdrop-blur-xl border-white/[0.10] shadow-lg shadow-black/20"
            : "bg-white/[0.04] backdrop-blur-md border-white/[0.06]",
        )}
      >
        <div className="px-6 lg:px-8 py-3">
          {/* Desktop: links centered on each side of logo */}
          <div className="hidden md:grid grid-cols-3 items-center">
            {/* Left links — centered in their column */}
            <div className="flex items-center justify-center gap-8">
              {leftLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="text-base text-white/90 hover:text-white transition-colors duration-200"
                >
                  {link.label}
                </Link>
              ))}
            </div>

            {/* Center logo */}
            <Link
              href="#"
              onClick={(e) => {
                e.preventDefault();
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
              className="font-mono text-white text-2xl tracking-widest uppercase text-center"
            >
              {BRAND.name}
            </Link>

            {/* Right links + CTA — centered in their column */}
            <div className="flex items-center justify-center gap-8">
              {rightLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="text-base text-white/90 hover:text-white transition-colors duration-200"
                >
                  {link.label}
                </Link>
              ))}
              <Button variant="secondary" size="sm" href={CALENDLY_URL}>
                Book a Demo
              </Button>
            </div>
          </div>

          {/* Mobile: logo left, hamburger right */}
          <div className="flex md:hidden items-center justify-between">
            <Link
              href="#"
              onClick={(e) => {
                e.preventDefault();
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
              className="font-mono text-white text-2xl tracking-widest uppercase"
            >
              {BRAND.name}
            </Link>

            <button
              type="button"
              className="w-10 h-10 flex items-center justify-center text-white/90 hover:text-white transition-colors"
              onClick={() => setMobileOpen((prev) => !prev)}
              aria-expanded={mobileOpen}
              aria-label={mobileOpen ? "Close menu" : "Open menu"}
            >
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                {mobileOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
          </div>
        </div>

        {/* Mobile drawer */}
        <div
          className={cn(
            "md:hidden overflow-hidden transition-all duration-300 border-t",
            mobileOpen
              ? "max-h-80 opacity-100 border-white/[0.06]"
              : "max-h-0 opacity-0 border-transparent",
          )}
        >
          <div className="flex flex-col gap-4 px-6 py-5">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-base text-white/90 hover:text-white transition-colors"
                onClick={() => setMobileOpen(false)}
              >
                {link.label}
              </Link>
            ))}
            <Button variant="secondary" size="sm" href={CALENDLY_URL}>
              Book a Demo
            </Button>
          </div>
        </div>
      </nav>
    </div>
  );
}
