# Launch v0.2.0

Repository: `scopereceipt`

Description: **Document coverage receipts for AI agents. Track missing lines/pages with a local CLI and MCP server.**

Suggested topics: `mcp`, `ai-agents`, `python`, `document-analysis`, `verification`,
`provenance`, `cli`, `pdf`.

Before tagging a release, check hosted CI and try a real MCP client. The automated
wire tests are not a substitute for client interoperability testing. Publish only
source, synthetic examples and documentation; never a real receipt directory.

Record `python scripts/demo.py` for a short screencast. Show the actual strict exit
codes. The README graphic is generated from real CLI results with synthetic inputs.

Draft announcement (not posted):

> I built ScopeReceipt after repeatedly asking an AI assistant: “Did you actually
> read all the files?” It tracks which text lines and PDF pages were emitted through
> a local CLI or MCP server, then reports missing ranges. It catches partial reads,
> changed sources and newly added files. It cannot prove understanding or observe
> reads that bypass it. Try the no-install demo; I would value feedback from people
> doing whole-folder reviews with agents.

First feedback questions: Was setup simple? Did the report catch a real omission?
Which reading tool needs an adapter? Avoid unsupported competitor claims, fabricated
benchmarks, testimonials and star counts. The first goal is useful repeat usage.
