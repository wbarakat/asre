import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — ASRE",
};

export default function PrivacyPolicy() {
  return (
    <main className="bg-black min-h-screen">
      <div className="max-w-3xl mx-auto px-6 py-24 md:py-32">
        <Link
          href="/"
          className="text-white/60 hover:text-white text-sm transition-colors mb-12 inline-block"
        >
          &larr; Back to home
        </Link>

        <h1 className="font-serif text-4xl md:text-5xl text-white mb-4">
          Privacy Policy
        </h1>
        <p className="text-white/50 text-sm mb-12">
          Last updated: February 12, 2026
        </p>

        <div className="space-y-10 text-white/90 leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Overview</h2>
            <p>
              ASRE (&quot;we&quot;, &quot;us&quot;, &quot;our&quot;) operates the asre.io website.
              This page informs you of our policies regarding the collection, use, and
              disclosure of information when you visit our website.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Information We Collect</h2>
            <p className="mb-3">
              Our website is informational. We do not require account creation or collect
              personal health information (PHI) through this site. We may collect:
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong className="text-white">Scheduling information:</strong> When you book a
                demo via Calendly, your name, email, and any information you provide is
                collected by Calendly under their{" "}
                <a
                  href="https://calendly.com/privacy"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:underline"
                >
                  privacy policy
                </a>.
              </li>
              <li>
                <strong className="text-white">Analytics data:</strong> We may use privacy-respecting
                analytics to understand aggregate traffic patterns (page views, referral sources).
                No personally identifiable information is stored.
              </li>
              <li>
                <strong className="text-white">Cookies:</strong> Our site uses minimal cookies
                required for functionality. Third-party services (Calendly) may set their own cookies.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">ASRE Product &amp; PHI</h2>
            <p>
              The ASRE product processes healthcare data entirely within the customer&apos;s own
              infrastructure (VPC). No patient data, protected health information, or clinical
              records are transmitted to, stored on, or accessible from this website or any
              ASRE-controlled servers. All data processing occurs within the customer&apos;s
              environment.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">How We Use Information</h2>
            <ul className="list-disc pl-6 space-y-2">
              <li>To respond to demo requests and inquiries</li>
              <li>To improve our website and services</li>
              <li>To send relevant product information if you opt in</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Data Sharing</h2>
            <p>
              We do not sell, trade, or transfer your personal information to third parties.
              Information may be shared with service providers (e.g., Calendly for scheduling)
              solely to deliver the services you request.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Your Rights</h2>
            <p>
              Depending on your jurisdiction, you may have the right to access, correct, delete,
              or port your personal data. California residents have additional rights under CCPA.
              To exercise these rights, contact us at the address below.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Security</h2>
            <p>
              We use commercially reasonable measures to protect information collected through
              our website. However, no method of transmission over the internet is 100% secure.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Changes</h2>
            <p>
              We may update this policy from time to time. Changes will be posted on this page
              with an updated revision date.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Contact</h2>
            <p>
              Questions about this policy? Reach us at{" "}
              <a href="mailto:privacy@asre.io" className="text-accent hover:underline">
                privacy@asre.io
              </a>.
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}
