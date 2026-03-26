---
name: parse-html
description: "Extract and clean readable text content from HTML pages, including financial tables, earnings reports, and news articles."
---

# Parse HTML

## When to Use

Use this skill for:
1. **Article extraction**: Pulling clean text from financial news pages.
2. **Table parsing**: Extracting structured financial tables from earnings releases or SEC filings.
3. **Content processing**: Cleaning raw HTML before passing to analysis tools.

## Definition

```python
def parse_html(url: str, extract_tables: bool = True) -> dict:
    """Fetch and parse an HTML page into structured content.

    Args:
        url: The URL to fetch and parse
        extract_tables: Whether to extract HTML tables as structured data

    Returns:
        Dict with text content and optionally extracted tables
    """
    response = http_client.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    text = soup.get_text(separator='\n', strip=True)
    result = {'text': text[:5000]}
    if extract_tables:
        result['tables'] = extract_html_tables(soup)
    return result
```

## Best Practices

- Always pair with `web-search` or `edgar-search` to get URLs first.
- Use `extract_tables=True` when the target page has financial statements.
- Check `result['text']` length — truncation occurs at 5000 characters.
