---
name: retrieve-info
description: "Analyze and synthesize information from previously collected documents to extract specific financial data points and insights."
---

# Retrieve Information

## When to Use

Use this skill for:
1. **Data extraction**: Pulling specific figures (revenue, EPS, margins) from collected documents.
2. **Synthesis**: Combining information from multiple sources into a coherent answer.
3. **Confidence scoring**: Getting a reliability estimate alongside the extracted data.

## Definition

```python
def retrieve_info(query: str, documents: list[str] | None = None) -> dict:
    """Retrieve and synthesize information from collected documents.

    Args:
        query: What information to extract
        documents: Optional list of document IDs to search within

    Returns:
        Dict with extracted info, sources, and confidence
    """
    context = document_store.search(query, doc_ids=documents)
    synthesis = llm.synthesize(
        query=query,
        context=context,
        instruction='Extract precise financial data with sources',
    )
    return {
        'answer': synthesis.text,
        'sources': [s.id for s in synthesis.sources],
        'confidence': synthesis.confidence,
    }
```

## Best Practices

- Ask specific, targeted questions rather than broad queries.
- Check `confidence` score: values below 0.5 should be flagged for review.
- Specify `documents` IDs when you know which sources to search — improves speed and precision.
- Use after `parse-html` or `edgar-search` have collected source material.
