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

---

## 2026-10 — Adding last season's results to judge team strength (Phase 3)

**Problem:** Phase 3 rates each team's attack and defence to predict goals
in each match. Five gameweeks in, the FPL API has only 50 finished
matches - five per team - and one freak result can dominate that.

**Options considered:**
1. This season only (FPL API) - simplest, no new data source, but very
   noisy until well into the season
2. Add last season's 380 results from football-data.co.uk (a free CSV, no
   account or key), with older matches counting less (half weight every
   120 days) and promoted teams starting at the relegated teams' average
3. Use FPL's built-in team strength ratings - no fitting, but opaque, and
   likely the same basis as the 1-5 difficulty rating that the player
   backtest showed adds little

**Decision:** Option 2.

**Why - and the evidence:** Predicting each team's goals in gameweeks 2-5
(only using matches before each gameweek):

| Approach | Rank correlation |
|---|---|
| Model, last season + this season | 0.205 |
| Model, this season only | 0.046 |
| FPL 1-5 difficulty | 0.021 |

FPL's difficulty rating is barely better than random at predicting goals -
which explains why it added so little to player projections. And the model
only works once last season is included. Small sample (80 team-matches),
so treat the exact numbers as a first read.

**Trade-off accepted:** a second data source (and a team-name mapping
between the two: "Man United"/"Man Utd", "Tottenham"/"Spurs" - checked
automatically, so a mismatch can't silently split one club into two).

**PM lesson:** When early data is thin, borrow context - but let it fade
as your own data accumulates. And test the decision, not just the model:
running the "this season only" option alongside turned a judgement call
into evidence.

---

## 2026-10 — Estimating defensive contributions from season totals, not match history (Phase 3)

**Problem:** FPL awards +2 when a player's defensive actions in a match
reach a threshold (10 for defenders, 12 for midfielders/forwards). To
project these points we need each player's chance of reaching it next match.

**Options considered:**
1. **Match-by-match history** - how often they've actually hit the
   threshold. The most direct measure, but it needs every player's history:
   ~700 extra API calls, making the web app slow to load
2. **Season rate** - their actions per 90 minutes (already in FPL's main
   data file), converted into a chance of reaching the threshold with the
   same Poisson maths used for goals

**Decision:** Option 2.

**Why - the evidence:** a leakage-free backtest over GW3-7 (908
player-matches of 60+ minutes, 169 threshold hits), Brier score (lower is
better):

| Method | Brier | Predicted hits |
|---|---|---|
| Season rate | 0.130 | 163 |
| Match history | 0.133 | 159 |
| Position average | 0.143 | 153 |

The cheaper option was also the more accurate one, for defenders and
midfielders separately too - so there was no real trade-off to make.

**Also checked rather than assumed:** the API gives the points value but
not the thresholds, so they were verified against FPL's own GW6 points
breakdown (a clean split at 10 for defenders and 12 for midfielders).

**PM lesson:** "More data" and "more direct" feel more accurate, but test
before paying for them - here the expensive option would have cost load
time for a slightly worse answer. Framing it as speed *vs* accuracy assumed
a trade-off that the evidence showed didn't exist.

---

## 2026-10 — Adjusting attacking returns for the opponent only (Phase 3)

**Problem:** Expected goals/assists start from each player's xG and xA
per 90 this season. The question was how to adjust those for next
match's fixture.

**Options considered (backtested, GW3-7, 2,098 player-matches):**

| Approach | Rank correlation | Predicted total (actual 1,018) |
|---|---|---|
| No fixture adjustment | 0.272 | 1,046 |
| **Opponent-only**: scale by the opponent's defensive weakness + home/away | 0.271 | 1,048 |
| Full team model: scale by the team's predicted goals vs its usual xG | 0.262 | 984 |
| (Baseline: recent actual goals/assists per match) | 0.224 | 1,099 |

**Decision:** Opponent-only.

**Why:** The first version (full team model) slightly *hurt*. The reason
was traceable: a player's xG already reflects how good their own team's
attack is this season, but the team model's prediction also re-rates that
attack - leaning partly on last season - so it dragged this season's
strong attacks back towards last year. Adjusting only for the opponent
removes that double-counting. On five gameweeks it's level with no
adjustment (0.271 vs 0.272 - too close to call), and it's chosen because
it's the principled version and matches a strong prior from the wider
game (fixtures do matter). The backtest keeps reporting the no-adjustment
version, so if more data shows the adjustment adds nothing, it'll show.

**Also learned:** xG/xA rates beat actual recent goals/assists clearly
(0.27 vs 0.22) - chance quality predicts better than finishing luck.

**PM lesson:** When a reasonable-sounding feature makes results worse,
find out *why* before dropping it - here the cause (double-counting) led
to a better design rather than abandoning the idea. And when two options
tie, choose on principle and keep measuring, rather than over-reading a
0.001 difference.

---

## 2026-10 — Switching the product to expected points, goalkeepers included (Phase 3)

**Problem:** Phase 3 built expected points from FPL's scoring parts
(playing time, clean sheets, defensive contributions, goals and assists,
bonus, saves). Should it replace the original formula (recent form +
fixture difficulty) in the CLI, transfer suggestions and web app?

**The evidence:** on exactly the same 1,469 player-matches (GW3-7,
leakage-free), rank correlation 0.366 vs 0.318, and a smaller average
miss (2.19 vs 2.30 points). Better for defenders (0.30 vs 0.24),
midfielders (0.39 vs 0.35) and forwards (0.58 vs 0.52) - but worse for
goalkeepers (0.05 vs 0.11).

**Options considered:**
1. Switch everyone to expected points
2. Switch outfield players, keep the old formula for goalkeepers

**Decision:** Option 1.

**Why:** The goalkeeper result rests on 99 matches - too few to trust a
difference that size - and two models side by side would make every
projection harder to explain and compare across positions. The backtest
keeps reporting goalkeepers separately, so a lasting gap will show up.

**What changed for users:** projections now target the next deadline's
gameweek (double and blank gameweeks handled), rather than each team's next
unplayed match - which mid-gameweek could be a match already past the
deadline. The web app shows each player's breakdown by scoring part, so a
projection can be questioned, not just trusted.

**Also caught along the way:** the combined model's leakage test first
passed even with a deliberate leak, because it only varied actual goals -
which the model doesn't read. It now varies every input the model uses.

**PM lesson:** Ship the switch when the evidence clears a pre-set bar
(beat 0.321-ish on the same matches), not when the new thing feels more
sophisticated. And make the output explainable: a breakdown turns "trust
me" into "here's why", which matters more for a decision tool than a
slightly better number.

---

## 2026-10 — Judging transfers by your best XI, not by a like-for-like slot swap

**Problem:** The what-if simulator put an incoming player into the exact
slot of the outgoing one - same starting/bench status, same captaincy. The
user's request (choose a transfer *and* see which formation to play
afterwards) exposed a flaw: sell a benched defender for a strong midfielder
and the tool kept the new midfielder on the bench, valuing the transfer at
almost nothing. In reality you'd start him, drop your weakest starter, and
often change formation.

**Options considered:**
1. Keep slot swapping, and add a separate formation tool
2. Judge every transfer by the **best possible XI before vs after** -
   trying all 8 legal formations and picking the captain each time - and
   show every formation's total so the user can choose

**Decision:** Option 2.

**Why:** It measures what the user actually cares about (points from the
team they'd field), and it answers the formation question as a by-product
rather than as a separate feature. Checking all 8 formations is fast, so no
optimisation library was needed. The same best-XI picker is the foundation
for the next features: transfer suggestions ranked by best-XI gain, -4 hit
evaluation, and the free hit team.

**Also fixed:** the simulator didn't enforce FPL's 3-players-per-club limit.
It does now (read from FPL's own rules).

**PM lesson:** A user's feature request ("tell me the formation") can reveal
that the product is measuring the wrong thing. Fixing the measurement
first made the requested feature fall out naturally - and set up three
more on the same foundation.

---

## 2026-10 — Transfer plans and -4 hits: what to automate, what to ask

**Problem:** Suggest the best transfers and say whether a -4 point "hit"
(an extra transfer beyond your free ones) is worth it. Two sub-questions:
how to search, and how to know the user's free transfers.

**Decisions:**
1. **Rank every transfer by best-XI gain** (formation and captain re-picked
   each time), replacing the old rule that only flagged injured or
   "underperforming + tough run" starters using FPL's 1-5 difficulty -
   the weakest input the backtests found.
2. **Search pairs of transfers with a shared budget**, so the classic move
   - a cheaper downgrade funding an upgrade elsewhere - is found. About
   10,000 combinations per squad; a fast "total only" version of the
   best-XI picker (tested to agree with the full one) keeps it to ~1.5s.
3. **Ask the user for their free transfers (0-5)** rather than calculate
   them. The API doesn't expose the banked count directly; reconstructing
   it from transfer history and chip rules is fiddly and easy to get
   subtly wrong, and the user can read the exact number in the FPL app in
   a second. A wrong automatic number would silently corrupt every hit
   recommendation.
4. **Recommend the plan with the highest net gain** (none / single / pair,
   after hits), ties going to fewer transfers - and state the hit verdict
   in plain words ("a second transfer adds +1.42 pts, against the 4-point
   cost").

**Known limitation, shown on screen:** this uses next-gameweek projections
only. A new player keeps scoring for weeks, so a one-week view undervalues
transfers, hits especially. Multi-gameweek projections are next on the
roadmap.

**Also from testing:** several of my own hand-worked test expectations
were wrong - the search found legitimate options I'd missed (selling a
pricier player to fund a pair; selling one Arsenal player to buy two). The
tests now check rules that must always hold (budget, club limit) rather
than one assumed answer.

**PM lesson:** Automate what's reliable; ask for what the user knows
better. A one-tap input beats a clever inference that's occasionally
wrong in a way the user can't see. And be upfront about a recommendation's
horizon - "worth it this week" isn't "worth it".

---

## 2026-10 — Judging transfers over 3 gameweeks, lineup re-picked each week

**Problem:** The transfer planner judged every transfer on next
gameweek only - flagged on screen as undervaluing transfers, since a new
player keeps scoring for weeks while a -4 hit is paid once.

**Options considered:**
1. Keep one gameweek
2. Add up each player's points over 3 gameweeks, then pick one best XI
3. Pick the best XI **separately for each of the 3 gameweeks** and add up
   the weekly gains

**Decision:** Option 3, with 3 gameweeks as the default (1 still available).

**Why:** Option 2 is simpler but wrong in exactly the weeks that matter:
you change your lineup every week, and a blank or double gameweek changes
who should start. A test pins this: a keeper who blanks in week 2 is
benched for the backup that week. The fast best-XI total keeps the
3-week search under a second.

**What changed in practice** (the overall leader's squad, 1 free transfer):

| | Next gameweek | Next 3 gameweeks |
|---|---|---|
| Best single | Palmer -> Mbeumo (+1.6) | Palmer -> Tavernier (+5.6) |
| Two transfers, after the -4 hit | -0.9: not worth it | +6.9: **worth it** |

Both the recommended player and the hit verdict flip once the horizon
matches how long a transfer actually lasts.

**Limitations, stated in the app:** FPL's injury chance only covers the
next round but is applied to all 3 weeks; projections further ahead are
less certain (not yet backtested 2-3 weeks out); the fixture grid uses the
team model as it stands today.

**PM lesson:** A recommendation's time horizon is part of the product,
not a technical detail - the same data gave the opposite answer to "is
this hit worth it?" depending on it. Pick the horizon that matches the
decision's real consequences, and show it on screen.
