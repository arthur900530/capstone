---
name: "Edgar Search"
description: "Query the SEC EDGAR database to retrieve official company filings including 10-K, 10-Q, 8-K, and proxy statements."
---

# SEC Filing Search

## When to Use

Use this skill for:
1. **Annual/quarterly reports**: Fetching 10-K and 10-Q filings for financial statements.
2. **Material events**: Retrieving 8-K filings for earnings announcements or M&A disclosures.
3. **Primary source verification**: Confirming figures against official SEC-filed documents.

## Supported Filing Types

| Type | Description |
|------|-------------|
| 10-K | Annual report |
| 10-Q | Quarterly report |
| 8-K  | Current report (material events) |
| DEF 14A | Proxy statement |
| S-1  | Registration statement (IPO) |

## Definition

```python
def edgar_search(company: str, filing_type: str = '10-K', limit: int = 3) -> list[dict]:
    """Search SEC EDGAR for company filings.

    Args:
        company: Company name or CIK number
        filing_type: Type of filing (10-K, 10-Q, 8-K, etc.)
        limit: Maximum filings to return

    Returns:
        List of filing metadata with download URLs
    """
    filings = edgar_client.search(
        company=company,
        form_type=filing_type,
        count=limit,
    )
    return [
        {
            "filing_date": f.date,
            "form_type": f.form_type,
            "url": f.document_url,
            "description": f.description,
        }
        for f in filings
    ]
```

## Best Practices

- Prefer CIK numbers over company names for unambiguous lookups.
- Respect EDGAR rate limits: max 10 requests per second.
- Set `User-Agent` header to a valid contact email when calling the API directly.
