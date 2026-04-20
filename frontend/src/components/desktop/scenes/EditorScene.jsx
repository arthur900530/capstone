import { useState, useEffect } from "react";

const CODE_LINES = [
  `import pandas as pd`,
  `from datetime import datetime`,
  ``,
  `def process_filings(data_path):`,
  `    """Clean and transform SEC filing data."""`,
  `    df = pd.read_csv(data_path)`,
  `    df['date'] = pd.to_datetime(df['filing_date'])`,
  `    df = df.dropna(subset=['revenue', 'net_income'])`,
  `    df['profit_margin'] = df['net_income'] / df['revenue']`,
  `    return df.sort_values('date', ascending=False)`,
];

const KEYWORDS = ["import", "from", "def", "return"];

function tokenizeLine(line) {
  if (line === "") return [{ text: "\u00a0", cls: "" }];

  const tokens = [];

  // Handle docstring lines
  if (line.trim().startsWith('"""')) {
    tokens.push({ text: line, cls: "text-text-muted italic" });
    return tokens;
  }

  // Tokenize by splitting on spaces while preserving them, then classify each word
  // Use a simple segment approach
  const segments = [];
  let remaining = line;

  while (remaining.length > 0) {
    // Leading indentation
    const indentMatch = remaining.match(/^(\s+)/);
    if (indentMatch) {
      segments.push({ text: indentMatch[1], cls: "" });
      remaining = remaining.slice(indentMatch[1].length);
      continue;
    }

    // String literals (single or double quoted)
    const strMatch = remaining.match(/^(['"][^'"]*['"])/);
    if (strMatch) {
      segments.push({ text: strMatch[1], cls: "text-emerald-400" });
      remaining = remaining.slice(strMatch[1].length);
      continue;
    }

    // Comment
    if (remaining.startsWith("#")) {
      segments.push({ text: remaining, cls: "text-text-muted italic" });
      remaining = "";
      continue;
    }

    // Word token — could be keyword, function call (word before '('), dot accessor, etc.
    const wordMatch = remaining.match(/^([a-zA-Z_]\w*)/);
    if (wordMatch) {
      const word = wordMatch[1];
      remaining = remaining.slice(word.length);

      if (KEYWORDS.includes(word)) {
        segments.push({ text: word, cls: "text-purple-400" });
      } else if (remaining.startsWith("(")) {
        // Function call
        segments.push({ text: word, cls: "text-yellow-300" });
      } else {
        segments.push({ text: word, cls: "text-text-primary" });
      }
      continue;
    }

    // Dot accessor — .something
    const dotMatch = remaining.match(/^(\.[a-zA-Z_]\w*)/);
    if (dotMatch) {
      segments.push({ text: dotMatch[1], cls: "text-yellow-300" });
      remaining = remaining.slice(dotMatch[1].length);
      continue;
    }

    // Everything else (operators, punctuation, etc.) — character by character
    segments.push({ text: remaining[0], cls: "text-text-primary" });
    remaining = remaining.slice(1);
  }

  return segments;
}

function CodeLine({ line, highlight }) {
  const segments = tokenizeLine(line);
  return (
    <div
      className={`leading-5 px-2 rounded transition-colors duration-700 ${
        highlight ? "bg-yellow-400/10" : "bg-transparent"
      }`}
    >
      {segments.map((seg, i) => (
        <span key={i} className={seg.cls}>
          {seg.text}
        </span>
      ))}
    </div>
  );
}

const TOTAL_LINES = 20;

export default function EditorScene({ scene = {} }) {
  const { phase = "idle" } = scene;

  const [visibleLines, setVisibleLines] = useState(0);
  const [highlightedLine, setHighlightedLine] = useState(null);

  useEffect(() => {
    if (phase !== "editing") {
      setVisibleLines(0);
      setHighlightedLine(null);
      return;
    }

    setVisibleLines(0);
    setHighlightedLine(null);

    let current = 0;
    const interval = setInterval(() => {
      current++;
      setVisibleLines(current);
      setHighlightedLine(current - 1);

      // Remove highlight after a short delay
      setTimeout(() => {
        setHighlightedLine((prev) => (prev === current - 1 ? null : prev));
      }, 600);

      if (current >= CODE_LINES.length) {
        clearInterval(interval);
      }
    }, 150);

    return () => clearInterval(interval);
  }, [phase]);

  const lineCount = phase === "editing" ? visibleLines : 0;

  return (
    <div className="h-full flex flex-col bg-[#1e1e1e]">
      {/* File tab */}
      <div className="h-7 bg-[#2a2a2a] border-b border-border/20 px-3 flex items-center text-xs text-text-muted shrink-0">
        <span className="border-b border-accent-teal text-text-secondary pb-0.5">
          pipeline.py
        </span>
      </div>

      {/* Editor body */}
      <div className="flex-1 overflow-hidden flex">
        {/* Line number gutter */}
        <div className="w-10 bg-[#1a1a1a] border-r border-border/20 pt-2 shrink-0">
          {Array.from({ length: phase === "idle" ? TOTAL_LINES : lineCount }, (_, i) => (
            <div
              key={i}
              className="text-text-muted text-[10px] text-right pr-2 leading-5"
            >
              {i + 1}
            </div>
          ))}
        </div>

        {/* Code area */}
        <div className="flex-1 overflow-hidden font-mono text-xs p-2">
          {phase === "idle" && (
            <div className="text-text-muted text-xs pt-2 pl-2">
              {/* Empty lines */}
            </div>
          )}
          {phase === "editing" &&
            CODE_LINES.slice(0, visibleLines).map((line, i) => (
              <CodeLine
                key={i}
                line={line}
                highlight={highlightedLine === i}
              />
            ))}
        </div>
      </div>
    </div>
  );
}
