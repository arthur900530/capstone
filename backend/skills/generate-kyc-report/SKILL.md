---
name: Generate-KYC-Report
description: >
  This skill outlines the workflow for generating a Know Your Customer (KYC) report, encompassing company website research, GLEIF/LEI lookup, and adverse media/news screening to build a foundational client profile.
license: MIT
compatibility: Requires bash
metadata:
  author: your-name
  version: "1.0"
triggers:
  - KYC report
---

# Skill Content

This skill details the process of generating a Know Your Customer (KYC) report, which involves three main steps:

1.  **Company Website Research**: This step focuses on gathering foundational information about the client company.
    *   **Gather Information**: Review the company's official website to understand its business overview, products/services, leadership team, strategic priorities, geographic footprint, and regulatory disclosures. This helps establish a basic understanding of the client.
2.  **GLEIF / LEI Lookup**: This involves using the Global Legal Entity Identifier Foundation (GLEIF) database to extract crucial legal and organizational data.
    *   **Retrieve Company Information**: Pull the company's Legal Entity Identifier (LEI), registered address, entity status, and analyze the ownership/organizational hierarchy, including both direct and ultimate parent relationships, to understand the company's structure.
3.  **Adverse Media / News Screening**: The final step is to identify any potential risks associated with the company from public sources.
    *   **Surface Negative Information**: Conduct adverse media screening by searching sources like Google News and public court/regulatory filings to identify any negative news, sanctions, regulatory actions, or legal proceedings involving the company.

Together, these steps form a basic KYC profile, covering identity verification, corporate structure, and risk screening.
