import Link from "next/link";
import { Button } from "@/components/ui/button";
import { MaterialIcon } from "@/components/shared/material-icon";

const agents = [
  {
    icon: "search",
    title: "Research",
    description:
      "Deep-dive synthesis of academic sources, cross-referencing thousands of whitepapers in seconds.",
  },
  {
    icon: "tactic",
    title: "Planning",
    description:
      "Structured curriculum design with adaptive learning paths that evolve as you progress.",
  },
  {
    icon: "auto_graph",
    title: "Visualization",
    description:
      "Dynamic generation of high-fidelity diagrams, charts, and interactive mental maps.",
  },
  {
    icon: "school",
    title: "Teaching",
    description:
      "Adaptive AI-led tutoring that mirrors the Socratic method for deeper conceptual retention.",
  },
];

const pricing = [
  {
    name: "Starter",
    description: "Explore the power of AI learning.",
    price: "$0",
    period: "/ month",
    features: [
      "Core Research Agent",
      "5 Learning Projects",
      "Basic Visualizations",
    ],
    cta: "Get Started",
    popular: false,
  },
  {
    name: "Pro",
    description: "For the lifelong continuous learner.",
    price: "$29",
    period: "/ month",
    features: [
      "Full Agent Access",
      "Unlimited Projects",
      "Priority Agent Compute",
      "Custom Visual Export",
    ],
    cta: "Try Pro Free",
    popular: true,
  },
  {
    name: "Enterprise",
    description: "Custom solutions for organizations.",
    price: "$99",
    period: "/ user",
    features: [
      "Single Sign-On (SSO)",
      "Custom Agent Training",
      "Dedicated Success Manager",
    ],
    cta: "Contact Sales",
    popular: false,
  },
];

export default function LandingPage() {
  return (
    <>
      {/* Hero Section */}
      <section className="hero-gradient relative pt-20 pb-32 px-6 lg:px-20">
        <div className="max-w-5xl mx-auto text-center flex flex-col items-center">
          <div className="mb-6 inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-bold uppercase tracking-widest">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
            </span>
            New: v2.0 Agent Core
          </div>

          <h1 className="text-charcoal dark:text-white text-5xl md:text-7xl font-black leading-[1.1] tracking-[-0.04em] mb-8">
            Learning, <br className="hidden md:block" />
            <span className="text-primary">architected</span> by AI.
          </h1>

          <p className="text-charcoal/60 dark:text-slate-400 text-lg md:text-xl font-normal leading-relaxed max-w-2xl mb-12">
            Pedagora leverages advanced multi-agent systems to research, plan,
            visualize, and teach complex subjects with surgical precision.
          </p>

          <div className="flex flex-col sm:flex-row items-center gap-4">
            <Button size="lg" className="w-full sm:w-auto" asChild>
              <Link href="/signup">Start Learning Now</Link>
            </Button>
            <Button
              variant="outline"
              size="lg"
              className="w-full sm:w-auto flex items-center gap-2"
            >
              <MaterialIcon name="play_circle" className="text-primary" />
              Watch Demo
            </Button>
          </div>

          <div className="mt-20 w-full max-w-5xl rounded-2xl overflow-hidden border border-primary/10 bg-white/50 dark:bg-slate-900/50 p-2 backdrop-blur-sm shadow-2xl">
            <div className="bg-slate-900 rounded-xl aspect-video relative overflow-hidden flex items-center justify-center">
              <div className="text-center space-y-4">
                <MaterialIcon
                  name="play_circle"
                  className="text-6xl text-white/30"
                />
                <p className="text-slate-500 text-sm">Product demo coming soon</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Agent Engine Section */}
      <section className="py-24 px-6 lg:px-20 bg-white dark:bg-[var(--background)]/50">
        <div className="max-w-6xl mx-auto">
          <div className="mb-16">
            <h2 className="text-primary text-sm font-bold uppercase tracking-widest mb-4">
              The Engine
            </h2>
            <h3 className="text-charcoal dark:text-white text-4xl font-black tracking-tight mb-6">
              Modular Intelligence
            </h3>
            <p className="text-charcoal/60 dark:text-slate-400 text-lg max-w-xl">
              Our four-pillar agent system handles the heavy lifting of
              educational design, automating the journey from source material to
              mastery.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {agents.map((agent) => (
              <div
                key={agent.title}
                className="group p-8 rounded-2xl bg-[var(--background)] dark:bg-slate-900 border border-primary/5 hover:border-primary/20 hover:shadow-xl transition-all"
              >
                <div className="size-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center mb-6 group-hover:bg-primary group-hover:text-white transition-colors">
                  <MaterialIcon name={agent.icon} />
                </div>
                <h4 className="text-charcoal dark:text-white text-xl font-bold mb-3">
                  {agent.title}
                </h4>
                <p className="text-charcoal/50 dark:text-slate-400 text-sm leading-relaxed">
                  {agent.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="py-24 px-6 lg:px-20 bg-[var(--background)]">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-charcoal dark:text-white text-4xl font-black tracking-tight mb-4">
              Invest in your intellect
            </h2>
            <p className="text-charcoal/60 dark:text-slate-400">
              Simple, transparent pricing for individuals and institutions.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {pricing.map((plan) => (
              <div
                key={plan.name}
                className={`flex flex-col p-10 rounded-3xl bg-white dark:bg-slate-900 soft-shadow relative ${
                  plan.popular
                    ? "border-2 border-primary"
                    : "border border-primary/5"
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-primary text-white text-[10px] font-black uppercase tracking-[0.2em] px-4 py-1.5 rounded-full">
                    Most Popular
                  </div>
                )}

                <h5 className="text-charcoal dark:text-white font-bold mb-1">
                  {plan.name}
                </h5>
                <p className="text-charcoal/50 dark:text-slate-400 text-sm mb-6">
                  {plan.description}
                </p>

                <div className="mb-8 flex items-baseline gap-1">
                  <span className="text-4xl font-black text-charcoal dark:text-white">
                    {plan.price}
                  </span>
                  <span className="text-charcoal/50 dark:text-slate-400 text-sm font-medium">
                    {plan.period}
                  </span>
                </div>

                <ul className="space-y-4 mb-10 flex-1">
                  {plan.features.map((feature) => (
                    <li
                      key={feature}
                      className={`flex items-center gap-3 text-sm text-charcoal/70 dark:text-slate-300 ${
                        plan.popular ? "font-semibold" : ""
                      }`}
                    >
                      <MaterialIcon
                        name="check_circle"
                        className="text-primary text-xl"
                      />
                      {feature}
                    </li>
                  ))}
                </ul>

                <Button
                  variant={plan.popular ? "default" : "outline"}
                  className="w-full py-3 rounded-xl"
                  asChild
                >
                  <Link href="/signup">{plan.cta}</Link>
                </Button>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
