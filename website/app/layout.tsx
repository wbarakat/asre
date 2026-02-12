import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Playfair_Display } from "next/font/google";
import "./globals.css";

const serif = Playfair_Display({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ASRE — Admission Signal Reliability Engine",
  description:
    "One trusted encounter layer. ASRE unifies fragmented ADT, claims, and authorization signals into confidence-scored, reconciled admission events.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable} ${serif.variable}`}>
      <body className="font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
