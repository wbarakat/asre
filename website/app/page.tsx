import Navbar from "@/components/sections/Navbar";
import Hero from "@/components/sections/Hero";
import PainPoints from "@/components/sections/PainPoints";
import KeyMetrics from "@/components/sections/KeyMetrics";
import BookCall from "@/components/sections/BookCall";
import Footer from "@/components/sections/Footer";

export default function Home() {
  return (
    <main>
      <Navbar />
      <Hero />
      <PainPoints />
      <KeyMetrics />
      <BookCall />
      <Footer />
    </main>
  );
}
