import React from "react";
import Link from "next/link";
import { BRAND, FOOTER } from "@/lib/constants";

export default function Footer() {
  return (
    <footer className="bg-black">
      <div className="divider" />
      <div className="max-w-7xl mx-auto px-6 py-12">
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="font-serif text-white/80">{BRAND.name}</div>

          <nav aria-label="Footer links" className="flex gap-6">
            {FOOTER.links.map((link) => (
              <Link
                key={link.label}
                href={link.href}
                className="text-sm text-white/60 hover:text-white transition-colors duration-200"
              >
                {link.label}
              </Link>
            ))}
          </nav>

          <p className="text-sm text-white/50">{FOOTER.copyright}</p>
        </div>
      </div>
    </footer>
  );
}
