import React from "react";
import Link from "next/link";
import { FOOTER } from "@/lib/constants";

export default function Footer() {
  return (
    <footer className="section-navy">
      <div className="max-w-7xl mx-auto px-6 py-12">
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-sm text-slate-400">{FOOTER.copyright}</p>

          <nav aria-label="Footer links" className="flex gap-6">
            {FOOTER.links.map((link) => (
              <Link
                key={link.label}
                href={link.href}
                className="text-sm text-slate-400 hover:text-white transition-colors duration-200"
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </footer>
  );
}
