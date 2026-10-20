# Lead Generation Workflow

## Overview
Automate lead discovery, extraction, filtering, and enrichment for legitimate business opportunities. This workflow handles the full lead lifecycle from source discovery to CRM-exportable format.

## Source Discovery
- Search and filter for lead opportunities across supported platforms
- Apply legal/technical permitting checks before enrichment
- Normalize lead data into consistent format

## Data Extraction
- Extract contact information, company details, and relevant metadata from web sources
- Apply deduplication detection to avoid redundant leads
- Score leads based on predefined criteria

## Enrichment (if legally/technically permitted)
- Enrich lead data with additional fields when permitted
- Apply scoring and priority ranking
- Export in compatible formats

## Output Formats
- CSV export for spreadsheet integration
- SQLite database for local storage
- CRM-compatible JSON format

## Scoring Features
- Source fit: How well the lead source matches target criteria
- Niche fit: Alignment with target industry/niche
- Legal/technical compliance status
- Data quality and recency scores

## Human Gates
- Lead verification before export
- Enrichment permission checks
- Score threshold validation

## Compliance
- Only extract data permitted by target site rules
- No circumvention of platform restrictions
- Data privacy compliance (GDPR, CCPA considerations)
- No credential harvesting

## Cost
- $0 hard cap - all processing local
- Free tools: Python, regex, SQLite
- No paid APIs or hosting required
- Optional free-tier APIs as accelerators only

## State Persistence
- SQLite database for leads, scores, enrichment status
- Audit log for all extraction and enrichment steps
- Deduplication hash tracking

## Testing
- Unit tests: parsers, scorers, state transitions, deduplication
- Integration tests: DB operations, export formats
- Failure tests: missing source data, network interruptions, duplicate detection