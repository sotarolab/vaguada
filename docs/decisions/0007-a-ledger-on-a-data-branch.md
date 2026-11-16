# 0007. A ledger on a data branch, in hapi's shape; the service stack dropped

Date: 2026-11-16
Status: accepted; supersedes the store, service and client parts of 0001 and 0004

## Context

The first build put six feeds into Postgres behind a FastAPI service and a React page, and
stopped before the scorer and the model. A sibling project, hapi, proves forecasts in
production with a fraction of the code: raw products archived to a `data` branch by a
scheduled workflow, a scorer, a digest, a static page on GitHub Pages, and model forecasts
arriving from a separate science package through one CSV contract. Two ledgers with one
pattern cost less to run and to read than two patterns.

## Decision

Vaguada is a ledger in hapi's shape. Four flat scripts: `archive.py` saves every live
product as it arrived, gzipped, under `data/<product>/<station>/<UTC fetch time>.gz`;
`settle.py` turns the archived climate reports into settlements, keeping the preliminary
and the final version; `score.py` scores every model forecast file and every baseline it
builds from the archive at the local issue slots, using only files fetched before the
slot; `site.py` writes the JSON the page draws. A workflow runs them every hour and commits
to the `data` branch; `main` is code only.

A model lives in its own package and writes
`data/forecasts/<model>/<station>/<issue>.csv` with `date,target,lead_h,q05,q25,q50,q75,q95`
in Fahrenheit. The ledger scores it like any other product and never knows how it was made.

Point in time holds through filenames: the fetch time is the record of when a product was
known. No database, no service, no request-time computation.

## Consequences

The package `vaguada/` keeps the parsers, the local-day module and the daily-extremes
functions from the first build; the store, the service, the migrations and the client are
deleted. Observations are archived raw and reparsed by the digest, so a parser fix changes
the page without a migration. The record is a git branch anyone can clone.

## Alternatives rejected

- Finish the service stack: the scorer and the model were still ahead, and the stack would
  have stayed heavier than hapi for the same claim.
- Merge temperature into hapi: every script would carry two domains under a river's name.
