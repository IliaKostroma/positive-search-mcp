<img src="banner.png" alt="Positive Search" width="100%">

# Positive Search MCP server

**Infrastructure for trading AI agents and their humans**

<!-- mcp-name: io.github.iliakostroma/positive-search-mcp -->

which allows saving tokens while getting the highest-quality information about the current
news background. Through the analysis of a large number of open sources, Polymarket, X
and Truth.

An advanced scoring formula, a system of narratives and a source-quality audit together
help not to let fakes through. And to easily make decisions based on information that is
already analyzed, selected and sorted. The process of collecting the information and the
process of analysis are laid out, described and easy to understand — and assembled from
open sources, so, just in case, all of it is very easy to verify.

For the human on the site — a convenient UX where you immediately see which narratives
pull the price and in which direction. It provides history in the blockchain, which gives
very high reliability. The only tool to see the movement — sentiment over the last day,
over the last few days, over the last week, which also helps to make better decisions in
trading.

**Want the details?** How the AI reads the news and builds the index —
[About](https://positivesearch.app/about-en), in eight languages:
[EN](https://positivesearch.app/about-en) ·
[RU](https://positivesearch.app/about) ·
[DE](https://positivesearch.app/about-de) ·
[FR](https://positivesearch.app/about-fr) ·
[ES](https://positivesearch.app/about-es) ·
[PT](https://positivesearch.app/about-pt) ·
[PL](https://positivesearch.app/about-pl) ·
[NL](https://positivesearch.app/about-nl)

---

## Install

Python 3.9+. **No dependencies** — standard library only, so there is no version conflict
to resolve and nothing to keep updated.

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "positive-search": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/IliaKostroma/positive-search-mcp",
        "positive-search-mcp"
      ]
    }
  }
}
```

### Claude Code

```bash
claude mcp add positive-search -- uvx --from git+https://github.com/IliaKostroma/positive-search-mcp positive-search-mcp
```

### Cursor

`~/.cursor/mcp.json` — same shape as the Claude Desktop block above.

Restart the client afterwards, then ask it
*"what's the news sentiment on bitcoin right now?"*

### Without uv

It is one file with no imports beyond the standard library, so a clone is enough:

```bash
git clone https://github.com/IliaKostroma/positive-search-mcp.git
python3 positive-search-mcp/ps_mcp.py --selftest
```

Then point `command` at `python3` and `args` at the absolute path to `ps_mcp.py`.

Or install it into your environment:

```bash
pip install git+https://github.com/IliaKostroma/positive-search-mcp
positive-search-mcp --selftest
```

`--selftest` runs the handshake and every tool against the live site and prints a pass/fail
line for each — worth running once before you trust it.

---

## Tools

| Tool | What it answers |
|---|---|
| `get_sentiment` | **Start here.** The current reading — number, state, measurement time and expiry, what it is made of (news + X + Polymarket), 1h/24h/7d change, a ready citation line — **and the three heaviest narratives**, so one call answers both what and why |
| `get_narratives` | The full set of stories, each with its sentiment, `mass` and cross-source `agreement`, plus example headlines with links |
| `get_history` | Seven days, **daily by default** (close/avg/min/max per day) — enough to tell a normal reading from an outlier; `granularity: "hourly"` for every run, about six times the payload |
| `get_sources` | The evidence — every headline that went into the reading, with its own score, age, publisher and a link to the original |
| `compare_assets` | All three readings at once, ranked most bullish first, each with its own measurement time |

The cheap path: `compare_assets` to pick an asset → `get_sentiment` for the reading and the
top narratives → `get_narratives` only if you want the whole picture → `get_sources` only to
verify a specific headline → `get_history` only to check whether today is unusual.

Assets: `BTC`, `GOLD`, `OIL`. Loose spellings work — `bitcoin`, `XAU`, `crude oil`. Anything
else returns an explicit error naming what is covered, never a substitute reading.

**On weights.** Narrative `mass` is published; per-article weight is not. A single article's
weight is one model judgement and moves between runs, while narrative mass aggregates many
articles and is stable — so weight is published where it holds still. Inputs are auditable,
the published reading is tamper-evident, and the per-article weighting is not reproducible
from here. We would rather say that than imply otherwise.

---

## What makes it worth citing

**Every reading carries its own measurement time.** The three assets are scored on their
own hourly runs, so their readings carry three different timestamps. Quote a number with
the time next to it — a sentiment value without its moment is wrong the hour after.

**The number is a stored fact, not a live recomputation.** It is computed once, when the
run happens, from the components captured in that same run. Re-read that run tomorrow and
you get the same number to the last digit.

**Every source is linked.** The index is only as good as what it read, so what it read is
public: `get_sources` returns each headline with its own score and a link to the original.

**Past readings cannot be silently rewritten.** Every run enters a sha256 hash chain whose
head is anchored daily in the Bitcoin blockchain via OpenTimestamps. The fingerprints and
their proofs are published at <https://positivesearch.app/proofs/> and verify independently
of this site and its owner (`ots verify`).

**Honest limits, stated up front.** It measures the tone of news coverage. It is not price,
not a price forecast, and not financial advice. We do not recommend using it as your only
input — use it alongside technical, fundamental and other analysis, as one instrument among
several.

---

## How to read the number

`+1` strongly bullish coverage, `−1` strongly bearish, `0` **balanced, not silent** — bull
and bear pressure are measured separately, so a reading near zero usually means two strong
narratives pulling against each other. `get_narratives` tells the two cases apart.

"Bullish" means *works in favour of the price*, not *good news*. Bad news for an industry is
often bullish for its price.

---

## Without MCP

Everything here is also plain HTTP, no key required:

* Machine entry point: <https://positivesearch.app/.well-known/agents-gate.json>
* Methodology and limits: <https://positivesearch.app/llms.txt>
* Human pages: [Bitcoin](https://positivesearch.app/bitcoin-sentiment) ·
  [Gold](https://positivesearch.app/gold-sentiment) ·
  [Oil](https://positivesearch.app/oil-sentiment)

---

## Contact

Need another instrument (ETH, SOL, an FX pair, an index)? The engine is not tied to any
asset — <hi@positivesearch.app>.

MIT licence for this client. The readings themselves are published under CC BY 4.0.
