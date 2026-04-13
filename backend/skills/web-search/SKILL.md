---
name: "Web Search"
description: "Search the web for real-time financial data, news articles, and market information using targeted queries."
---

# Web Search

## When to Use

Use this skill for:
1. **Real-time data**: Fetching current stock prices, earnings releases, or market news.
2. **News retrieval**: Finding recent articles about a company or sector.
3. **Cross-referencing**: Verifying figures from SEC filings against analyst commentary.

## Definition

```python
def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web for financial information.

    Args:
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        List of search results with title, url, and snippet
    """
    results = search_engine.query(query, limit=max_results)
    return [
        {
            "title": r.title,
            "url": r.url,
            "snippet": r.snippet,
        }
        for r in results
    ]
```

## Best Practices

- Use specific financial terms and ticker symbols in queries.
- Combine with `parse-html` to extract full content from result URLs.
- Include year/quarter in queries for time-sensitive data (e.g. "Apple Q4 2024 earnings").
