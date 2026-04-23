import { Sparkles } from "lucide-react";

export default function WelcomeHeader() {
  return (
    <div className="flex flex-col items-center gap-3 pt-16 pb-24 md:pt-24 md:pb-32">
      <div className="flex items-center gap-3">
        <h1 className="font-welcome font-bold
               text-5xl md:text-5xl
               tracking-[0.1em] md:tracking-[0.15em]">
          Welcome, User
        </h1>
        <div className="sparkle-wrapper relative cursor-pointer">
          <Sparkles
            size={45}
            className="sparkle-icon text-transparent"
            style={{
              fill: "url(#bny-teal-gradient)",
              stroke: "url(#bny-teal-gradient)",
              strokeWidth: 0.5,
            }}
          />
          <div className="sparkle-glow absolute -inset-3 -z-10 rounded-full opacity-0 blur-xl" />
          <svg width="0" height="0" className="absolute">
            <defs>
              <linearGradient id="bny-teal-gradient" x1="0%" y1="0%" x2="200%" y2="0%">
                <stop offset="0%" stopColor="#05687F">
                  <animate attributeName="stop-color" values="#05687F;#ACE2E5;#2D9BAD;#05687F" dur="3s" repeatCount="indefinite" />
                </stop>
                <stop offset="50%" stopColor="#ACE2E5">
                  <animate attributeName="stop-color" values="#ACE2E5;#2D9BAD;#05687F;#ACE2E5" dur="3s" repeatCount="indefinite" />
                </stop>
                <stop offset="100%" stopColor="#2D9BAD">
                  <animate attributeName="stop-color" values="#2D9BAD;#05687F;#ACE2E5;#2D9BAD" dur="3s" repeatCount="indefinite" />
                </stop>
              </linearGradient>
            </defs>
          </svg>
        </div>
      </div>
      <p className="text-base text-text-muted">
        How can I help you today?
      </p>
    </div>
  );
}
