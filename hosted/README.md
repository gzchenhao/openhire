---
title: OpenHire
emoji: 🛰️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Employers' own job postings as an MCP endpoint
---

# OpenHire hosted endpoint

The MCP endpoint is at `/mcp` on this Space. It serves the same public job index as the
`openhire` package on PyPI (employers in AI infra, autonomous driving and embodied AI, read
from the employers' own applicant-tracking systems, with the employer's own posting date).

It exists for assistants that can only reach a URL, such as ChatGPT connectors. Everything a
request carries is what the tools take: search filters, a company name or domain, a board
URL, an anonymous client-generated fingerprint. No résumé, name, email or phone, ever, by
protocol. The local install (`uvx openhire serve`) remains the recommended path: there,
nothing of a search leaves your machine.

Source, privacy terms and the weekly numbers: https://github.com/gzchenhao/openhire
