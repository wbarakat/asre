import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Sidebar } from "@/components/sidebar";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ASRE Documentation",
  description:
    "Admission Signal Reliability Engine - customer-facing documentation",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <Sidebar />
        <div className="lg:pl-64">
          <header className="sticky top-0 z-20 border-b border-zinc-800 bg-black/80 px-6 py-3 backdrop-blur-sm">
            <a
              href="/"
              className="text-sm text-zinc-500 transition-colors hover:text-[#60A5FA]"
            >
              &larr; Back to ASRE
            </a>
          </header>
          <main className="mx-auto max-w-3xl px-6 py-10">{children}</main>
        </div>
      </body>
    </html>
  );
}
