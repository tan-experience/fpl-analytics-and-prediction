# Decisions Log

A running record of non-obvious choices made while building this project:
the problem, the options on the table, what was chosen, and why. Code shows
*what* the project does; this shows *why* it's shaped the way it is.

Add an entry whenever a genuine trade-off is made - not for routine code,
only for moments where a reasonable person could have gone a different way.

---

## 2026-09 — Heuristic baseline before machine learning (Phase 2)

**Problem:** Needed a way to project player points for the upcoming
gameweek.

**Options considered:**
1. Jump straight to a trained ML model (e.g. regression on historical data)
2. Build a simple weighted formula first (form + fixture difficulty +
   playing probability), then compare ML against it later

**Decision:** Option 2 — built the heuristic first.

**Why:** Without a baseline, there's no way to know if a more complex model
is actually *better*, just different. A heuristic is also fully explainable
("this player's projection dropped because their next fixture got harder"),
which matters for trusting the system's output before adding more
complexity on top.

**PM lesson:** This is a "walking skeleton" / MVP pattern — ship the
simplest thing that produces a real, end-to-end output, then improve it
incrementally with a way to measure whether each improvement actually
helped.

---

## 2026-09 — Projecting for "pending" squads is not possible via the public API

**Problem:** Wanted the tool to reflect transfers made *after* the last
locked gameweek but *before* the next deadline — i.e. your true current
squad, not your last-locked one.

**Options considered:**
1. Authenticate as the user (store real FPL login credentials) and use an
   undocumented private endpoint that exposes pending squad state
2. Accept the public API's limitation and build a "what-if" transfer
   simulator instead, letting the user test hypothetical swaps against
   their last-locked squad

**Decision:** Option 2.

**Why:** FPL deliberately doesn't expose pending transfers (any manager's)
through the public API — it's the same privacy boundary that stops rivals
seeing each other's moves before a deadline. Working around that would mean
storing a real password for marginal benefit, and probably runs against
what the public API is meant for. The simulator is arguably more useful
anyway: it lets you test a transfer idea *before* committing to it, not
just after.

**PM lesson:** A platform constraint that looks like a bug to work around
is sometimes a deliberate design choice by the platform owner. Worth asking
"why would they have built it this way?" before trying to route around it -
and sometimes the constraint points you toward a better product idea than
the one you started with.

---

## 2026-09 — "Current" vs "upcoming" gameweek (a data-modeling bug)

**Problem:** Squad projections initially labeled themselves as being for
Gameweek 5, when the intent was to project forward to Gameweek 6.

**What happened:** FPL's API has two relevant flags — `is_current` (the
gameweek whose matches are happening/just happened; always has real picks
data) and `is_next` (the upcoming one; often has *no* picks data yet, since
nothing's locked in until its deadline passes). The fix was attempted by
simply switching which flag the code checked first — which fixed the label
but broke the feature (404 errors, since GW6 had no picks data to fetch).

**Decision:** Fetch picks from `is_current` (the only gameweek with real
data), but treat the *fixture difficulty* features as forward-looking
regardless — they already looked at each team's next unplayed match
independently of which gameweek's picks were being used.

**Why:** The original bug wasn't really about which flag to check — it was
conflating two different questions: "whose squad is this" (always the last
locked-in one) and "which match are we projecting toward" (always the next
one). Once separated, both could be simultaneously true and correctly
labeled.

**PM lesson:** A bug that looks like "wrong priority order" is sometimes
actually "two concepts got merged into one variable." Untangling the
underlying question usually matters more than getting the flag order right.

---

## 2026-09 — Simplified transfer budget math

**Problem:** FPL's real "selling price" rules are nontrivial — you don't
always get full value back on a player whose price has risen since you
bought them.

**Decision:** The transfer simulator treats sell price as equal to a
player's current listed price, not the user's actual purchase-adjusted
sell value.

**Why:** Modeling FPL's exact profit-rounding rules adds real complexity
for a tool meant to sanity-check an idea, not be the system of record for
your budget. The simplification is flagged clearly in the code and in
conversation with the user, so it's a known, visible limitation rather than
a silent inaccuracy.

**PM lesson:** Not every edge case needs to be modeled precisely — the
right call often depends on how the output will actually be used (a
directional check vs. a financial ledger). The key responsibility is making
the simplification visible, not eliminating it.

---

## 2026-09 — Built Phase 4 (squad import, transfers) before Phase 3 (match predictions)

**Problem:** The original project plan sequenced match/goal predictions
before team analysis and transfers.

**Decision:** Reordered to build team import, projection, and transfer
suggestions first.

**Why:** The user's immediate interest (seeing projections for their own
real squad) was reachable sooner this way, and it kept momentum/motivation
high early in a project the user is building to *learn* from, not just to
ship on a fixed deadline.

**PM lesson:** Roadmaps are a starting hypothesis, not a contract. Reordering
based on what will deliver visible value soonest — especially early, when
proving the concept works matters more than following the original
sequence — is a normal and healthy part of planning, as long as the reason
for the reorder is recorded somewhere (like here).

---

## 2026-10 — Rank correlation, not average error, as the headline accuracy metric

**Problem:** Built a backtest to measure how good the points projections
are. The obvious metric, mean absolute error (MAE: "how many points off
were we, on average"), declared the winner to be "predict 2 points for
everyone" - beating the actual model (2.03 vs 2.34).

**What happened:** FPL scores are heavily skewed - most players who play
score 1-2 points, with occasional big hauls. MAE rewards always guessing
the median (2), so a "model" with zero insight looks best. But it's useless
for the real job: deciding *which* player to pick over another.

**Options considered:**
1. Keep MAE as the headline and try to beat the naive baseline on it
2. Switch the headline to rank correlation (did we put players in the
   right *order*?), keeping MAE as a secondary number

**Decision:** Option 2. On 882 player-matches (GW3-5), the model's rank
correlation is 0.32, vs 0.32 for plain form and an undefined score for the
constant baseline. The fixture adjustment helps only marginally, and tuning
its weight changed results within noise (0.316-0.324), so the weight stays
at 0.15 until there's more data.

**Why:** A metric should match the decision the product supports. FPL
managers choose between players; they don't need exact point totals.

**Also noted:** the API has no history of injury chances, so the backtest
only scores matches the player actually played. It measures "how good is
the projection, given they play", not "did we predict who'd play".

**PM lesson:** Pick the success metric before celebrating or panicking
about a number - the "obvious" metric can reward a useless answer. And
don't tune on noise: a tiny improvement on a small sample isn't a result.

---

## 2026-10 — Web app before better predictions (Phase 5 ahead of Phase 3)

**Problem:** With a working command-line tool, a measured baseline and
tests in place, the next step could be either a better model (Phase 3:
predicting goals per match) or a web app (Phase 5).

**Options considered:**
1. Phase 3 first - improve accuracy, then build the interface once the
   model settles
2. Web app first - make the existing tool usable by anyone, then improve
   the model inside a product people can already try

**Decision:** Option 2.

**Why:** The intended user changed. Until now the user was the builder,
comfortable in a terminal. As a public portfolio piece, the user is also a
recruiter or FPL player with about a minute and no Python installed - and
for them, a repo they'd have to clone and set up is effectively unusable,
however accurate the model. Two setup mistakes made during this project
(a missed virtual-environment step, and typing a `<TEAM_ID>` placeholder
literally) showed how easily a terminal tool loses people. The backtest
also showed the current model is only modestly better than form alone, so
a Phase 3 gain would be invisible to anyone who couldn't run it.

**De-risking first:** The plan depended on one untested assumption - that
the FPL API accepts requests from Streamlit Community Cloud's servers (some
sites block cloud hosts). Before merging, the app was deployed from its
feature branch as a test; a real squad loaded, confirming the simple
architecture works. Had it failed, the fallback was fetching data on a
schedule via GitHub Actions - a different design, better found out early.

**PM lesson:** "Who is the user?" is worth re-asking whenever the context
changes - a tool that's complete for its builder can be unusable for its
real audience. And when a plan rests on one risky assumption, test that
assumption cheaply before building on it.
