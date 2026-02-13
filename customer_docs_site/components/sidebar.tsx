"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navigation } from "@/lib/navigation";
import { useState } from "react";

export function Sidebar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  // Derive current slug from pathname ("/" -> "", "/getting-started/overview" -> "getting-started/overview")
  const currentSlug = pathname === "/" ? "" : pathname.replace(/^\//, "");

  const navContent = (
    <nav className="space-y-6">
      {navigation.map((group) => (
        <div key={group.group}>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            {group.group}
          </p>
          <ul className="space-y-0.5">
            {group.pages.map((page) => {
              const href = page.slug === "" ? "/" : `/${page.slug}`;
              const isActive = currentSlug === page.slug;
              return (
                <li key={page.slug}>
                  <Link
                    href={href}
                    onClick={() => setMobileOpen(false)}
                    className={`block rounded-md px-3 py-1.5 text-sm transition-colors ${
                      isActive
                        ? "bg-[#60A5FA]/10 font-medium text-[#60A5FA]"
                        : "text-zinc-400 hover:bg-zinc-800 hover:text-white"
                    }`}
                  >
                    {page.title}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );

  return (
    <>
      {/* Mobile toggle button */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="fixed left-4 top-4 z-50 rounded-md border border-zinc-700 bg-zinc-900 p-2 text-zinc-400 hover:text-white lg:hidden"
        aria-label="Toggle navigation"
      >
        <svg
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          {mobileOpen ? (
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          ) : (
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 6h16M4 12h16M4 18h16"
            />
          )}
        </svg>
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 z-40 h-screen w-64 overflow-y-auto border-r border-zinc-800 bg-zinc-950 px-4 pb-8 pt-16 transition-transform lg:translate-x-0 lg:pt-8 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="mb-6">
          <Link href="/" className="text-lg font-bold text-white">
            ASRE Docs
          </Link>
        </div>
        {navContent}
      </aside>
    </>
  );
}
