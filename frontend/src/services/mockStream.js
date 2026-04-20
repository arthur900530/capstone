/**
 * Mock SSE stream that simulates a realistic agent workflow.
 * Falls back to this when the real backend is unavailable.
 */

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

const TOOL_SEQUENCES = [
  // Research-heavy flow
  [
    { tool: "web_search", detail: "Apple Inc AAPL 2024 annual revenue" },
    { tool: "edgar_search", detail: "Apple Inc 10-K filing 2024" },
    { tool: "parse_html", detail: "Parsing SEC filing document..." },
    { tool: "retrieve_info", detail: "Extracting financial metrics" },
    { tool: "submit_result", detail: "Compiling final report" },
  ],
  // Terminal-heavy flow
  [
    { tool: "web_search", detail: "Python data pipeline best practices" },
    { tool: "terminal", detail: "python pipeline.py --input data/filings.csv" },
    { tool: "file_editor", detail: "Editing pipeline.py to add validation" },
    { tool: "terminal", detail: "python -m pytest tests/ -v" },
    { tool: "retrieve_info", detail: "Collecting pipeline output metrics" },
    { tool: "submit_result", detail: "Pipeline execution complete" },
  ],
];

export async function mockStreamChat(_params, onEvent) {
  const sequence = TOOL_SEQUENCES[Math.floor(Math.random() * TOOL_SEQUENCES.length)];

  // Session start
  onEvent("session", { session_id: `mock-${Date.now()}` });
  await delay(200);

  // Agent assignment
  onEvent("agent", { name: "Research Analyst", model: "mock/demo-agent" });
  await delay(300);

  // Status
  onEvent("status", { message: "Starting analysis..." });
  await delay(500);

  // Trial start
  onEvent("trial_start", { trial: 1, max_trials: 3 });
  await delay(400);

  // Reasoning
  onEvent("reasoning", { text: "Let me analyze this request and determine the best approach. I'll need to gather financial data and cross-reference multiple sources." });
  await delay(2000);

  // Tool calls with results
  for (let i = 0; i < sequence.length; i++) {
    const step = sequence[i];

    onEvent("tool_call", { turn: i + 1, tool: step.tool, detail: step.detail });
    await delay(1200 + Math.random() * 800);

    onEvent("tool_result", { text: `Completed: ${step.detail}` });
    await delay(600 + Math.random() * 400);

    // Mid-flow reasoning after second tool
    if (i === 1) {
      onEvent("reasoning", { text: "Good progress. Let me dig deeper into the primary source documents to verify these figures." });
      await delay(1500);
    }
  }

  // Self evaluation
  onEvent("self_eval", {
    critique: "The analysis covers revenue, margins, and cash flow from verified SEC filings.",
    confidence_score: 0.85,
    is_confident: true,
  });
  await delay(2000);

  // Final answer
  onEvent("answer", {
    text: "Based on my analysis of Apple's SEC filings and financial data:\n\n**Key Findings:**\n- Total Revenue: $383.3B (FY2024), up 2% YoY\n- Net Income: $97.0B, with EPS of $6.13\n- Gross Margin: 46.2%, improved from prior year\n- Services Revenue: $96.2B, up 12% YoY\n- Free Cash Flow: $111.4B\n- Shareholder Returns: $94.4B via dividends and buybacks\n\nThe company shows strong profitability with services driving growth momentum.",
  });
}
