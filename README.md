# Data Quality — Shift-Left DDL Validation Test

This repo demonstrates the Data Quality Platform's Liquibase changelog validation.

Every time a changelog file changes, GitHub Actions:
1. Parses all CREATE TABLE statements
2. Validates them against 50 active data quality rules
3. Posts a findings report as a PR comment

## Setup

Add `DQ_URL` as a GitHub secret pointing to your Data Quality Platform backend.
