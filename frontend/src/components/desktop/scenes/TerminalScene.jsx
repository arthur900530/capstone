import { useState, useEffect } from "react";

const PYTHON_OUTPUT = [
  "Loading dataset... done (1,247 rows)",
  "Validating schema... OK",
  "Running transformations... complete",
  "Pipeline finished. 0 errors.",
];

const DEFAULT_OUTPUT = [
  "Connecting to data source...",
  "Fetching records... 2,341 rows",
  "Processing...",
  "Complete.",
];

function Prompt() {
  return <span className="text-emerald-400">agent@workspace:~$</span>;
}

function BlinkCursor() {
  return <span className="animate-blink text-text-primary ml-1">█</span>;
}

function ProgressBar() {
  return (
    <div className="mt-1 mb-2">
      <div className="h-3 w-48 bg-surface rounded-full overflow-hidden">
        <div className="h-full bg-emerald-400 animate-progress" />
      </div>
    </div>
  );
}

export default function TerminalScene({ scene = {} }) {
  const { phase = "idle", command = "python pipeline.py --env prod" } = scene;

  const [typedCommand, setTypedCommand] = useState("");
  const [commandDone, setCommandDone] = useState(false);
  const [visibleOutputCount, setVisibleOutputCount] = useState(0);
  const [showProgress, setShowProgress] = useState(false);
  const [showFinal, setShowFinal] = useState(false);

  const isPython =
    command.includes("python") || command.includes("pipeline");
  const outputLines = isPython ? PYTHON_OUTPUT : DEFAULT_OUTPUT;

  useEffect(() => {
    if (phase !== "typing_command" && phase !== "command_done") {
      setTypedCommand("");
      setCommandDone(false);
      setVisibleOutputCount(0);
      setShowProgress(false);
      setShowFinal(false);
      return;
    }

    // Type the command char by char
    let index = 0;
    setTypedCommand("");
    setCommandDone(false);
    setVisibleOutputCount(0);
    setShowProgress(false);
    setShowFinal(false);

    const typingInterval = setInterval(() => {
      index++;
      setTypedCommand(command.slice(0, index));
      if (index >= command.length) {
        clearInterval(typingInterval);
        setCommandDone(true);
      }
    }, 40);

    return () => clearInterval(typingInterval);
  }, [phase, command]);

  useEffect(() => {
    if (!commandDone) return;

    // Show progress bar shortly after command finishes
    const progressTimer = setTimeout(() => setShowProgress(true), 100);

    // Stagger output lines
    const outputTimers = outputLines.map((_, i) =>
      setTimeout(() => {
        setVisibleOutputCount((c) => Math.max(c, i + 1));
      }, 300 + i * 200)
    );

    // Show final prompt after all output
    const finalTimer = setTimeout(
      () => setShowFinal(true),
      300 + outputLines.length * 200 + 300
    );

    return () => {
      clearTimeout(progressTimer);
      outputTimers.forEach(clearTimeout);
      clearTimeout(finalTimer);
    };
  }, [commandDone]);

  return (
    <div className="h-full bg-[#0d0d0d] font-mono text-xs p-4 overflow-hidden flex flex-col">
      {/* Previous session line for context */}
      {(phase === "typing_command" || phase === "command_done") && (
        <div className="text-text-muted mb-2 text-[10px]">
          Last login: Mon Apr 20 09:41:12 2026
        </div>
      )}

      {phase === "idle" && (
        <div>
          <Prompt />
          <BlinkCursor />
        </div>
      )}

      {(phase === "typing_command" || phase === "command_done") && (
        <div className="space-y-1">
          {/* Command line */}
          <div>
            <Prompt />
            <span className="text-text-primary ml-1">{typedCommand}</span>
            {!commandDone && <BlinkCursor />}
          </div>

          {/* Progress bar */}
          {showProgress && commandDone && <ProgressBar />}

          {/* Output lines */}
          {outputLines.slice(0, visibleOutputCount).map((line, i) => (
            <div key={i} className="text-text-secondary">
              {line}
            </div>
          ))}

          {/* Final success line + prompt */}
          {showFinal && (
            <>
              <div className="text-emerald-400 mt-1">✓ Done</div>
              <div className="mt-1">
                <Prompt />
                <BlinkCursor />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
