# Agent tools for SI-Trader

The development checkout can use Codex project skills and Claude Code plugins to inspect filings, discover skills, and review its automation setup. SI-Trader still runs with Python and Ollama. Document extraction is a development tool. The application accepts validated evidence through the [catalogue feed contract](CATALOGUE_FEEDS.md).

## Open the local workspace

On the Windows machine used for this setup, the source repositories and runtimes are in the sibling folder `SI-Trader-Agent-Tools`. From the SI-Trader development checkout, launch the isolated Claude Code profile in PowerShell.

```powershell
& '..\SI-Trader-Agent-Tools\Open-SI-Trader-Claude.ps1'
```

On first use, complete the Claude Code sign-in in that profile. Run the same launcher with `plugin list` to check enabled plugins.

- **Claude Code Setup** reviews the checkout and proposes relevant automations. Ask it to recommend automations for this project.
- **Claude-Mem** retains development-session context when its observer is running and authenticated. Keep credentials and account data out of recorded prompts and tool outputs. Use the isolated profile for SI-Trader work.
- **Anthropic document skills** support review of PDFs, spreadsheets, and other documents. **AnyDoc** can convert input to Markdown for an extraction pass on the local machine.
- **Find Skills** can find additional tools for a focused task. For example, `npx skills find "pdf filings" --owner anthropics`.

## Use the tools for catalogue research

1. Start with a public filing from the issuer, exchange, or regulator. Record the ISIN, source URL, publication timestamp, and reporting period.
2. Convert the document locally with AnyDoc or use a PDF skill to inspect the source table. Check the extracted value against the source, especially the units, consolidated versus standalone basis, and effective date.
3. Produce the typed observation from the [catalogue feed contract](CATALOGUE_FEEDS.md). Leave a value unknown if the source does not establish it. Keep the underlying filing link so another person can verify it.
4. Open **Weekly → 48-Parameter Run Report** and check coverage, source dates, and conflicts. Use original publication dates to assemble the separate chronological bundle for historical tests.

## Upstream projects

- [Claude-Mem](https://github.com/thedotmack/claude-mem)
- [Vercel Find Skills](https://github.com/vercel-labs/skills/tree/main/skills/find-skills)
- [Firecrawl AnyDoc](https://github.com/firecrawl/anydoc)
- [Claude Code Setup](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/claude-code-setup)
- [Anthropic Agent Skills](https://github.com/anthropics/skills)
