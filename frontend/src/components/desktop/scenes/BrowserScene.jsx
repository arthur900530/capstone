import { useState, useEffect } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

const SEARCH_RESULTS = [
  {
    title: "Apple Inc. (AAPL) Stock Price & News — finance.yahoo.com",
    url: "https://finance.yahoo.com/quote/AAPL",
    snippet:
      "Get the latest Apple Inc. (AAPL) stock price, news, buy/sell ratings, and financial data...",
  },
  {
    title: "AAPL | Apple Inc. Annual Report (10-K) — sec.gov/edgar",
    url: "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=AAPL",
    snippet:
      "Annual report filed pursuant to Section 13 and 15(d). Revenue: $383.3B...",
  },
  {
    title: "Apple Revenue & Earnings - Macrotrends — macrotrends.net",
    url: "https://www.macrotrends.net/stocks/charts/AAPL/apple/revenue",
    snippet:
      "Apple revenue for the twelve months ending September 2024 was $391.0B...",
  },
];

const EDGAR_FILINGS = [
  { type: "10-K", date: "2025-10-30", description: "Annual report" },
  { type: "10-Q", date: "2025-07-31", description: "Quarterly report" },
  { type: "8-K", date: "2025-06-15", description: "Current report" },
  { type: "DEF 14A", date: "2025-01-10", description: "Proxy statement" },
];

const READING_PARAGRAPHS = [
  "Apple Inc. reported total net revenue of $383.3 billion for the fiscal year ended September 2024, representing a 2% increase year over year.",
  "The company's gross margin improved to 46.2%, driven by higher services revenue and favorable product mix.",
  "Operating expenses totaled $57.4 billion, including $30.1 billion in research and development.",
  "Net income for the period was $97.0 billion, or $6.13 per diluted share, compared to $6.16 in the prior year.",
  "The company returned $94.4 billion to shareholders through dividends and share repurchases during the fiscal year.",
  "Management expects continued growth in services revenue, which reached $96.2 billion, up 12% year over year.",
];

function useTypingAnimation(targetText, charDelay = 30, startDelay = 0) {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!targetText) {
      setDisplayed("");
      setDone(false);
      return;
    }
    setDisplayed("");
    setDone(false);
    let index = 0;
    const startTimer = setTimeout(() => {
      const interval = setInterval(() => {
        index++;
        setDisplayed(targetText.slice(0, index));
        if (index >= targetText.length) {
          clearInterval(interval);
          setDone(true);
        }
      }, charDelay);
      return () => clearInterval(interval);
    }, startDelay);
    return () => clearTimeout(startTimer);
  }, [targetText, charDelay, startDelay]);

  return { displayed, done };
}

function UrlBar({ url }) {
  const { displayed } = useTypingAnimation(url, 30);
  return (
    <div className="h-9 bg-[#2a2a2a] border-b border-border/20 flex items-center px-3 gap-2 shrink-0">
      <ChevronLeft size={14} className="text-text-muted opacity-40" />
      <ChevronRight size={14} className="text-text-muted opacity-40" />
      <div className="flex-1 bg-[#1a1a1a] rounded-md px-3 py-1 text-xs text-text-secondary truncate">
        {displayed || <span className="text-text-muted">about:blank</span>}
      </div>
    </div>
  );
}

function IdleContent() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4">
      <div className="text-3xl font-light text-text-muted tracking-tight select-none">
        <span className="text-blue-400">G</span>
        <span className="text-red-400">o</span>
        <span className="text-yellow-400">o</span>
        <span className="text-blue-400">g</span>
        <span className="text-emerald-400">l</span>
        <span className="text-red-400">e</span>
      </div>
      <div className="w-64 h-8 bg-[#2a2a2a] rounded-full border border-border/30 flex items-center px-3 gap-2">
        <svg
          className="w-3 h-3 text-text-muted"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
        <span className="text-text-muted text-xs">Search</span>
      </div>
    </div>
  );
}

function SearchingContent({ query, resultsVisible, highlightFirst }) {
  return (
    <div className="flex-1 overflow-hidden p-4 space-y-4">
      {resultsVisible && (
        <div className="space-y-4">
          {SEARCH_RESULTS.map((result, i) => (
            <div
              key={i}
              className={`space-y-0.5 transition-colors duration-300 rounded px-2 py-1 ${
                highlightFirst && i === 0 ? "bg-accent-teal/10" : ""
              }`}
              style={{
                opacity: 0,
                animation: `fadeIn 0.4s ease-out ${i * 200}ms forwards`,
              }}
            >
              <div className="text-accent-teal text-sm font-medium">
                {result.title}
              </div>
              <div className="text-emerald-400 text-xs">{result.url}</div>
              <div className="text-text-secondary text-xs">{result.snippet}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EdgarContent({ resultsVisible, highlightFirst }) {
  return (
    <div className="flex-1 overflow-hidden p-4">
      <div className="text-text-primary font-semibold mb-3 text-sm">
        EDGAR Company Search
      </div>
      {resultsVisible && (
        <div
          className="rounded border border-border/20 overflow-hidden"
          style={{
            opacity: 0,
            animation: "fadeIn 0.4s ease-out 0ms forwards",
          }}
        >
          <div className="grid grid-cols-3 gap-0 bg-[#1a1a1a] px-3 py-1.5">
            <span className="text-text-muted uppercase text-[10px]">Form</span>
            <span className="text-text-muted uppercase text-[10px]">Filed</span>
            <span className="text-text-muted uppercase text-[10px]">
              Description
            </span>
          </div>
          {EDGAR_FILINGS.map((filing, i) => (
            <div
              key={i}
              className={`grid grid-cols-3 gap-0 px-3 py-1.5 text-xs transition-colors duration-300 ${
                i % 2 === 0 ? "bg-white/5" : ""
              } ${highlightFirst && i === 0 ? "bg-accent-teal/10" : ""}`}
            >
              <span className="text-accent-teal font-medium">{filing.type}</span>
              <span className="text-text-secondary">{filing.date}</span>
              <span className="text-text-secondary">{filing.description}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ReadingContent({ phase }) {
  return (
    <div className="flex-1 overflow-hidden relative">
      <div
        className={phase === "reading" ? "animate-scroll-page" : ""}
        style={{ padding: "16px", paddingBottom: "80px" }}
      >
        {READING_PARAGRAPHS.map((para, i) => (
          <p
            key={i}
            className={`text-text-secondary text-xs leading-5 mb-3 rounded px-1 ${
              i < 3 ? "animate-highlight" : ""
            }`}
            style={
              i < 3
                ? { animationDelay: `${i * 400 + 800}ms`, animationFillMode: "both" }
                : {}
            }
          >
            {para}
          </p>
        ))}
      </div>
    </div>
  );
}

export default function BrowserScene({ scene = {} }) {
  const { phase = "idle", query = "AAPL financial data", detail } = scene;

  const [resultsVisible, setResultsVisible] = useState(false);
  const [highlightFirst, setHighlightFirst] = useState(false);

  const searchUrl =
    phase === "searching" || phase === "results_shown"
      ? `https://www.google.com/search?q=${encodeURIComponent(query)}`
      : "";
  const edgarUrl =
    phase === "edgar" || (phase === "results_shown" && detail === "edgar")
      ? `https://www.sec.gov/cgi-bin/browse-edgar?company=${encodeURIComponent(
          query
        )}`
      : "";
  const readingUrl =
    phase === "reading" || (phase === "results_shown" && detail === "reading")
      ? `https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm`
      : "";

  const activeUrl = searchUrl || edgarUrl || readingUrl;
  const urlCharCount = activeUrl.length;
  const typingDuration = urlCharCount * 30 + 100;

  useEffect(() => {
    setResultsVisible(false);
    setHighlightFirst(false);

    if (
      phase === "searching" ||
      phase === "edgar" ||
      phase === "reading" ||
      phase === "results_shown"
    ) {
      const showTimer = setTimeout(() => {
        setResultsVisible(true);
      }, typingDuration + 300);

      return () => clearTimeout(showTimer);
    }
  }, [phase, query]);

  useEffect(() => {
    if (phase === "results_shown") {
      setHighlightFirst(true);
    } else {
      setHighlightFirst(false);
    }
  }, [phase]);

  const isEdgar =
    phase === "edgar" ||
    (phase === "results_shown" && detail === "edgar");
  const isReading =
    phase === "reading" ||
    (phase === "results_shown" && detail === "reading");

  return (
    <div className="h-full flex flex-col bg-[#1e1e1e]">
      <UrlBar url={activeUrl} />
      <div className="flex-1 overflow-hidden flex flex-col">
        {phase === "idle" && <IdleContent />}
        {(phase === "searching" || (phase === "results_shown" && !isEdgar && !isReading)) && (
          <SearchingContent
            query={query}
            resultsVisible={resultsVisible}
            highlightFirst={highlightFirst}
          />
        )}
        {isEdgar && (
          <EdgarContent
            resultsVisible={resultsVisible}
            highlightFirst={highlightFirst}
          />
        )}
        {isReading && <ReadingContent phase={phase} />}
      </div>
    </div>
  );
}
