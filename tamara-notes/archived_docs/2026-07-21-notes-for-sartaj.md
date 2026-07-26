# Notes for Sartaj — data pipeline + thoughts on the AI layer

Written after a long session fixing the scrape→format→extract-text pipeline
and thinking through how it should hand off to your semantic/tagging layer.
This is Tamara's read on where things stand and a few opinions on the
handoff — meant as a starting point for discussion, not a spec you're bound
to.

## The mission, as I understand it

The point of all this is getting people involved in legislation before it
passes, not after. Advocacy orgs (the kind of groups that already have an
audience who trusts them — civil rights orgs, LGBTQ+ orgs, etc.) need to know
specifically what's in a bill early enough to tell their people, so those
people can act while it still matters. A single bill can bury a provision
that matters enormously to one specific community inside a much larger,
otherwise-unrelated bill. Missing that buried provision is the exact failure
mode this whole project exists to prevent — so "how granular and how fast"
matters more here than in a typical data pipeline.

## What the extraction side now reliably gives you

As of tonight, three things that were broken are fixed
(`actions/extract/utils/pdf_extractor.py`, `text_extraction.py`):

1. **The real PDF bytes are actually stored now.** They weren't before — the
   saved "PDF" file was secretly the already-extracted text, re-saved under a
   `.pdf`-looking name. If your pipeline (or anything) was ever pointed at
   `*_Bill_Text.pdf` expecting a real PDF, it was getting garbage. Fixed —
   genuine binary PDF, alongside a clean plain-text extraction.
2. **One clean text read per document**, no artificial section-splitting.
   The old code wrote the same content twice (a broken "Section N:"
   breakdown, then the same thing again as "Raw Text"). Gone — just one
   clean read now.
3. **A `has_visual_markup` flag**, not an attempt to reconstruct
   strikethrough text ourselves. Checks for actual drawn lines/rectangles
   over text (pdfplumber `page.lines`/`page.rects`) rather than guessing off
   font names — catches both strikethrough (deleted language) and underline
   (added language), since both matter for knowing the plain-text extraction
   might not faithfully represent what the bill actually changes.

## Why the flag, not a fix

Amendment bills are usually "redline" documents — the PDF contains both the
old language being deleted and the new language being added, distinguished
only by strikethrough/underline. Plain text extraction glues both together
with no indication of which is which. That's not a formatting nuisance, it's
a correctness problem: a plain-text reader (human or model) can't tell what
the bill actually changes from that text alone.

I tried a Python heuristic for this (font/spacing/color-based strikethrough
detection) — it didn't work, and even when it "detected" something, the
reconstructed text was unreadable garbage (character-by-character, no
spaces). What *did* work, with zero custom code: reading the actual bill PDF
with a vision-capable model. It correctly read the redline and summarized
what the bill does. My take: `has_visual_markup: true` should route a
document to you (or whatever handles the semantic layer) with the **raw
PDF**, not our plain-text extraction — let a model that can actually see the
document's layout resolve what's being added vs. removed, rather than us
trying to encode that ourselves and handing you an approximation.

For documents where `has_visual_markup` is false, plain text extraction is
probably trustworthy on its own and cheaper to just use directly.

## How common this actually is, state by state

Ran an audit across the 28 states whose bills are PDF-only (no HTML/XML
alternative — full list and methodology in
`actions/extract/docs/2026-07-21-pdf-visual-markup-audit.md`). Sampled ~10
bills per state, checked earliest and latest available version of each.

- **Consistently marked up (~85-100%), even on bills that haven't been
  amended yet**: AL, CT, FL, GU, ID, MD, ND, NE, NC, OK, OR, RI, VT, KY.
  Possibly house style for these states (e.g. always underlining new
  statutory language on introduction), not just amendment-tracking. I'd
  treat these as needing full-fidelity handling by default.
- **Consistently clean**: GA, IN, LA, ME (zero markup across 8-20 samples
  each). Plain text is probably fine for these without extra cost.
- **Mixed**: everything else — worth checking per-document (the flag already
  does this), not assuming one way or the other for the whole state.

This was the "cheap first-pass filter" idea — turns out it doesn't cleanly
reduce to "some states never need it," since several PDF-only states are
*consistently* redline even pre-amendment. But it does mean you can budget
for it: roughly half the PDF-only states are near-100% likely to need
full-fidelity treatment, a handful are near-0%, and the rest genuinely need
the per-document check.

(28 states are PDF-only; the other ~25 states already have HTML or XML
alternatives and our pipeline already prefers those over PDF, so this
question doesn't apply to them at all — full breakdown in
`actions/scrape/docs/bill-format-audit.md`.)

## On the decomposition + tagging problem itself

Tamara described what you're building: an LLM layer that breaks a bill down
into its component parts (self-learning), feeding a cheaper tagging system
for orgs. That's your design, not something I'm trying to spec for you — but
one thing worth flagging from the extraction side, since it affects what
"good input" looks like for that layer:

**Whole-document tag-matching will miss exactly the thing this project cares
about most.** If a provision relevant to one specific community is a couple
paragraphs buried in an otherwise-unrelated 40-page bill, embedding the whole
document as one vector and comparing it against a tag's description dilutes
that signal into irrelevance — the "needle in a haystack" problem. Whatever
decomposition step you build, I'd bet the tagging/matching needs to happen
per-provision, not per-bill, or the exact failure case this project exists
to prevent (missing the buried thing) is the first thing that slips through.

A couple of other things that came up as important, for whatever it's worth:

- **Every provision-level summary should carry its source excerpt** — the
  actual quoted text it's based on, not just a generated paraphrase. Orgs
  are about to tell real people "this will affect you"; they need to be able
  to verify or quote it themselves, not trust a summary blind.
- **Timeline/urgency matters more than the summary itself.** The whole point
  is alerting before a vote, not after. A feed item saying "this passed" is
  useless for this mission; "committee vote in 3 days" is the actual
  product.

## What I'd want your input on

- Whether the audit above changes how you'd want to route documents (e.g. a
  static per-state default vs. always checking the per-document flag).
- Whether you want the raw PDF handed to you always, or only when
  `has_visual_markup` is true (cost/latency tradeoff — happy to talk through
  what the pipeline can cheaply provide either way).
- What the actual handoff interface should look like — right now metadata
  (`metadata.json`) and extracted text (`*_extracted.txt`) are separate files
  a consumer has to fetch and join. If it's useful, I can combine them into
  one JSON object per bill (structured metadata + full text + the raw-PDF
  pointer + the markup flag) so your pipeline doesn't have to do that
  assembly itself.
