import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service — ASRE",
};

export default function TermsOfService() {
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
          Terms of Service
        </h1>
        <p className="text-white/50 text-sm mb-12">
          Last updated: February 12, 2026
        </p>

        <div className="space-y-10 text-white/90 leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Acceptance of Terms</h2>
            <p>
              By accessing the ASRE website at asre.io, you agree to be bound by these Terms
              of Service. If you do not agree to these terms, please do not use the site.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Description of Service</h2>
            <p>
              This website provides information about ASRE (Admission Signal Reliability Engine),
              a healthcare data reliability product. The website is informational and does not
              constitute a software service, medical advice, or clinical tool.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Use of the Site</h2>
            <p className="mb-3">You agree to use this site only for lawful purposes. You may not:</p>
            <ul className="list-disc pl-6 space-y-2">
              <li>Attempt to gain unauthorized access to any part of the site or its systems</li>
              <li>Use the site to transmit harmful code or interfere with its operation</li>
              <li>Reproduce, distribute, or create derivative works from site content without permission</li>
              <li>Use automated tools to scrape or extract data from the site</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Intellectual Property</h2>
            <p>
              All content on this site, including text, graphics, logos, and software, is the
              property of ASRE or its licensors and is protected by applicable intellectual
              property laws. The ASRE name, logo, and product names are trademarks of ASRE.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Product Information</h2>
            <p>
              Information about ASRE&apos;s product capabilities, performance metrics, and features
              is provided for informational purposes. Actual results may vary based on data
              quality, configuration, and deployment environment. Product specifications are
              subject to change.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Third-Party Services</h2>
            <p>
              This site integrates with third-party services such as Calendly for scheduling.
              Your use of these services is governed by their respective terms and privacy
              policies. We are not responsible for the practices of third-party services.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Disclaimer of Warranties</h2>
            <p>
              This site is provided &quot;as is&quot; and &quot;as available&quot; without warranties
              of any kind, either express or implied, including but not limited to implied
              warranties of merchantability, fitness for a particular purpose, or non-infringement.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Limitation of Liability</h2>
            <p>
              To the fullest extent permitted by law, ASRE shall not be liable for any indirect,
              incidental, special, consequential, or punitive damages arising from your use of
              or inability to use this site.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Governing Law</h2>
            <p>
              These terms are governed by and construed in accordance with the laws of the
              State of Delaware, without regard to its conflict of law provisions.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Changes to Terms</h2>
            <p>
              We reserve the right to modify these terms at any time. Changes will be posted
              on this page with an updated revision date. Continued use of the site after
              changes constitutes acceptance of the new terms.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold text-white mb-3">Contact</h2>
            <p>
              Questions about these terms? Reach us at{" "}
              <a href="mailto:legal@asre.io" className="text-accent hover:underline">
                legal@asre.io
              </a>.
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}
