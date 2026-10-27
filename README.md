# NFL EDGE Context Lab — v2

## What this actually is
A complete replacement starter with real team analytics, ESPN injury ingestion, source-aware scenario adjustments and temporal player-interval evaluation. It is not a completed all-input automated scouting service. No 80% accuracy promise. No bundled mock statistics.

## Publish
1. Back up the existing repository.
2. Replace/upload index.html, build.py, context.py, players.py, requirements.txt, README.md and the inputs/ and tests/ directories.
3. Replace .github/workflows/live.yml with this package's workflow. GitHub upload may skip dotfolders; create that exact file path manually if needed.
4. Settings > Pages > Source > GitHub Actions.
5. Actions > Publish NFL EDGE Context Lab > Run workflow.
6. Check tests/build/deployment logs, page data timestamp, all 32 teams and ESPN feed status. A green deploy does not mean every optional feed is available. Optional sources fail visibly; current-season play-by-play and complete teams are required.

## Working pipeline vs required configuration
Automatic: nflverse schedules/play-by-play, team modeling, ESPN injury parsing, ESPN upcoming events, live browser scoreboard polling, chronological player yardage models, split-conformal interval calibration and untouched later-season coverage evaluation.
Configured: GSIS-to-ESPN player ID mapping; expected snap shares and replacement drops; offensive-line changes; individual blocking/coverage/alignment matchup estimates; verified venue coordinates and event roof state. Empty inputs are shipped deliberately. These factors can change the scenario forecast once supplied, but are NOT automatically discovered or verified by this package. See inputs/README.md for schemas.

ESPN injury comments can mention workload restrictions. Parser only flags explicit reported caps and ambiguity. A vague limited-practice designation never becomes a snap restriction. Numerically parsed caps require human review and a reliable expected-team-snap denominator before applying a share. No unsupported probabilities for Questionable/Doubtful.

## Weather
Requires exact ESPN venue ID/name record with source_url and verified_at; no usual-home-stadium fallback. Unknown/retractable roof means no penalty. Open-Meteo hourly forecast within one hour of scheduled kickoff, up to 16 days ahead. Units are mph wind, mm precipitation and Celsius temperature. Wind/rain/cold coefficients are transparent heuristics, not trained/validated causal effects. The forecast is source-backed, NOT an observation or guarantee of future weather. Source URL and retrieval time display in dashboard. Venue/roof freshness requires human review.

## Team prediction / context effects
Base logistic winner and ridge home-margin models use last-16-game exponentially weighted profiles with four-game shrinkage. Includes offense/defense EPA, pass/run EPA, success, explosives, turnovers, pass share and home/neutral indicator. Season-forward holdout only, ties excluded; corrected historical data make this retrospective reconstruction rather than immutable live picks. No betting odds and no artificial underdog quota.

Context scenario overlays apply only to upcoming games matched by home/away and date to an ESPN event. Supplied expected workload and mapped ESPN Out/IR status affect player contribution. Availability is not health. Replacement point loss, routes-vs-coverage, pass-protection and rusher alignment estimates feed expected point deltas. Weather changes passing scenarios and team scenarios. These overlays are unvalidated; source URLs are provenance, not proof of truth. Do not double count baseline injuries already reflected in team efficiency or overlapping matchup rows. Workload redistribution to teammates is NOT implemented. Baseline and adjusted probabilities display separately. Player scenario point estimates can change; baseline intervals do not become adjusted intervals.

## Player-stat interval validation
Passing/rushing/receiving yards separately. Features: prior-four role-game mean yards, opportunities, last yards, yardage standard deviation and history length. Minimum two prior role-opportunity games. Train seasons before prior season; calibrate absolute residual quantile on prior season; untouched current-season test reports empirical coverage, MAE, mean interval width and sample size. Nominal 80% coverage is NOT 80% winner accuracy. Finite-sample conformal quantile uses ceil((n+1)*(1-alpha)). No test tuning. Temporal dependence/distribution drift means no guaranteed coverage. Test state marked small below 100 rows.

Population is conditional on a recorded role opportunity. DNP, inactive and zero-opportunity outcomes are excluded; these are NOT unconditional game-day intervals. New players without sufficient history do not receive a forecast. Injured/retired players may remain in historical candidates; last-played dates are shown, and player inclusion is NOT a verified active roster. Point model deliberately stays fixed for honest evaluation; not refit on test data. Context-adjusted player intervals have not been validated and are not shown as such.

## Data and rights
ESPN injuries: https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries
ESPN injury page: https://www.espn.com/nfl/injuries
nflverse: https://github.com/nflverse/nflverse-data/releases
Update schedule: https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html
Weather: https://open-meteo.com/en/docs
ESPN endpoints are unofficial and can change. Free in-season participation data do not supply complete current individual assignments. Proprietary tracking requires a licensed provider with a supported adapter; no such license or feed is included. Review terms, attribution and commercial rights for all providers and team logos. Open-Meteo free endpoint is for eligible non-commercial use; commercial deployment needs the appropriate plan.

## Refreshes
Workflow scheduled hourly (not guaranteed start time). Advanced metrics reflect upstream publication, not the browser polling interval. ESPN injuries fetched on build; browser polls packaged JSON every 5 minutes, scores every 30 seconds while open. Hourly injury refresh is NOT an instant live update. Failed optional sources remain labeled unknown, no cached health assumptions. Build timestamp is not source publication timestamp. Historical context never uses current injuries/weather.

## Verification status
Python modules syntax-checked and synthetic unit tests run in the assistant sandbox. No network downloads, actual model fitting, empirical coverage results, browser render, live ESPN schema/CORS or deployed workflow verified there. First deployment is an integration test, not a forecast-quality certification. ESPN fetch through the research tool failed during preparation; parser needs real endpoint verification. No fabricated live injury data supplied. The included fixture-free tests check logic, not actual feed schemas.
