---
name: KYC-Report-Generation
description: >
  Generates a Know Your Customer (KYC) report for a company by performing comprehensive research and screening.
  This involves gathering information from the company's official website, conducting GLEIF/LEI lookups to
  understand legal entity identifiers and ownership structures, and performing adverse media/news screening
  to identify any negative news, sanctions, regulatory actions, or legal proceedings.
license: MIT
compatibility: Requires access to web search tools and the GLEIF database.
metadata:
  author: your-name
  version: "1.0"
triggers:
  - KYC report
  - Know Your Customer
  - compliance
  - due diligence
---

# Skill Content

This skill automates the process of generating a basic Know Your Customer (KYC) report. It is designed to assist in due diligence by collecting and analyzing publicly available information about a target company.

## Workflow

The KYC report generation involves three main steps:

1.  **Company Website Research:**
    *   **Objective:** To gain a foundational understanding of the client's business.
    *   **Information Gathered:**
        *   Business overview
        *   Products/services
        *   Leadership team
        *   Strategic priorities
        *   Geographic footprint
        *   Regulatory disclosures
    *   **Tool Usage:** This step can be performed by directly accessing and analyzing the company's official website or through a web search tool like `web-search` to find relevant company information.

2.  **GLEIF / LEI Lookup:**
    *   **Objective:** To verify the legal identity and understand the ownership structure of the company.
    *   **Information Retrieved:**
        *   Legal Entity Identifier (LEI)
        *   Registered address
        *   Entity status
        *   Ownership/Organizational hierarchy (direct and ultimate parent relationships)
    *   **Tool Usage:** This step requires accessing the Global Legal Entity Identifier Foundation (GLEIF) database. A direct API call or a web search tool can be used to query `https://www.gleif.org/` for the relevant information.

3.  **Adverse Media / News Screening:**
    *   **Objective:** To identify any potential risks such as negative news, sanctions, or regulatory issues.
    *   **Information Surfaced:**
        *   Negative news
        *   Sanctions
        *   Regulatory actions
        *   Legal proceedings
    *   **Tool Usage:** This step involves searching major news outlets and public court/regulatory filings. A web search tool like `web-search` (e.g., using `https://news.google.com/` or a general Google search) can be employed for this purpose.

## Usage Example

To generate a KYC report for a specific company, you would execute these steps in sequence, passing the company name or identification details as parameters to the respective tools or functions.

```python
# Assuming a function for each step exists, or a wrapper that uses web-search

# Step 1: Company Website Research
company_info = company_website_research(company_name="Example Corp")
print(f"Company Info: {company_info}")

# Step 2: GLEIF/LEI Lookup
lei_data = gleif_lei_lookup(company_name="Example Corp")
print(f"LEI Data: {lei_data}")

# Step 3: Adverse Media/News Screening
adverse_media_results = adverse_media_screening(company_name="Example Corp")
print(f"Adverse Media: {adverse_media_results}")

# Combine results into a KYC report
kyc_report = {
    "company_details": company_info,
    "legal_entity_info": lei_data,
    "risk_screening": adverse_media_results
}
print("KYC Report Generated:")
print(kyc_report)
```
