# Product Research Workflow

## Overview
Automate product research and opportunity scanning across ecommerce platforms, competitor sites, and marketplaces. This workflow discovers products, analyzes trends, and generates opportunity scores.

## Source Scan
- Scan ecommerce platforms, competitor sites, and marketplaces for product listings
- Extract product data including price, features, and availability
- Apply category and niche filtering

## Product Extraction
- Extract key product attributes: name, price, ratings, specifications
- Normalize product data into consistent schema
- Deduplicate identical or similar products

## Trend Detection
- Identify trending products based on velocity, seasonality, and market signals
- Compare products across competitors
- Detect price history and trend patterns

## Price Normalization
- Convert prices to common currency
- Adjust for regional pricing differences
- Calculate true cost including shipping and fees

## Competitor Comparison
- Build competitor product matrices
- Identify gaps and opportunities
- Score competitive positioning

## Opportunity Scoring
- Price competitiveness (weight: configurable)
- Margin potential (weight: configurable)
- Trend momentum (weight: configurable)
- Competition density (weight: configurable, penalized)
- Seasonality fit (weight: configurable)
- Rights and availability status

## Report Generation
- Structured report with top opportunities
- Visual charts and tables
- Export to CSV or SQLite

## Human Gates
- Report review before publication
- Score threshold validation
- Export permission checks

## Compliance
- No circumvention of platform restrictions
- Price comparison within legal boundaries
- No copyright-unapproved content
- Transparent scoring with configurable weights

## Cost
- $0 hard cap - all processing local
- Free tools: Python, BeautifulSoup, lxml, SQLite
- Optional free-tier AI APIs for classification only
- No paid scraping services or proxies

## State Persistence
- SQLite database for products, competitors, opportunities
- Trend history and price tracking
- Audit log for all scanning steps
- Deduplication hash tracking

## Testing
- Unit tests: parsers, scorers, state transitions, deduplication
- Integration tests: DB operations, report generation
- Failure tests: network interruptions, missing data, competitor site changes