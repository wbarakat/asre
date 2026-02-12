import Navbar from "@/components/sections/Navbar";
import Hero from "@/components/sections/Hero";
import PainPoints from "@/components/sections/PainPoints";
import Comparison from "@/components/sections/Comparison";
import KeyMetrics from "@/components/sections/KeyMetrics";
import BookCall from "@/components/sections/BookCall";
import Footer from "@/components/sections/Footer";

export default function Home() {
  return (
    <main className="bg-black">
      <Navbar />
      <Hero />
      <PainPoints />
      <Comparison />
      <KeyMetrics />
      <BookCall />
      <Footer />
    </main>
  );
}
