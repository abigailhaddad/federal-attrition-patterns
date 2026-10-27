# Federal attrition: charts for the post

Start with `run.ipynb`: it runs everything from OPM's files and shows each chart and the tables behind every number in the post, in the post's order.

```bash
pip install duckdb pandas matplotlib numpy
python3 run.py          # extract, build and spot check, in order (python3 run.py --verify adds verify_opm.py); run.ipynb does the same
python3 extract.py      # OPM EHRI from HuggingFace plus ICE's USAJOBS postings; slow, resumable (caches each file in data/cache/)
python3 verify_opm.py   # hashes every file read against OPM's own copy (data.opm.gov); build.py stops if any differs
python3 build.py        # charts, their CSVs, charts/tables/*.csv, charts/facts.md (the check log) and charts/rookie_screen.csv
python3 spot_check.py   # recomputes the headline numbers from OPM's raw files with separate code -> checks/spot_check.md
python3 post.py DRAFT.md OUT.docx   # the post as a Word file, each {{chart N}} marker replaced by that chart
```

| File | Shows |
|---|---|
| `1_ice_new_hires_who_left` | ICE's new officers since September 2025 who have left, vs Border Patrol agents hired in the same months |
| `2_how_people_left` | How five example occupations lost people in 2025 |
| `3_who_left_by_service` | People who left each year, by years of service (2026: January-August) |
| `4_leaving_pace_by_service` | Departures, quits and retirements per month per 1,000 staff, by years of service, January-August of every year |
| `6_attorney_quits` | Quit rates: everyone, attorneys (all and by agency), air traffic controllers, mid-career staff with graduate degrees |
| `8_pathways_hires` | Pathways hires, January-August of every year |
| `9_at_will_appointments` | Political appointees (Schedule C, noncareer and limited-term SES) |
| `10_schedule_policy_career` | Staff in Schedule Policy/Career by agency |
| `facts.md` | Every number in sentence form, with the data checks; spot_check.py reads it |
| `tables/*.csv` | The tables `run.ipynb` shows next to each part of the post, saved by `build.py`; `charts.csv` has each chart's headline and notes |
| `rookie_screen.csv` | New hires who left within a year, by agency component, 2023-2025 |

The images carry no headline, description or notes (the post does); `facts.md` lists each chart's suggested headline and its notes for footnotes. Titles are written text, but `build.py` checks the data still supports each claim. If one doesn't hold (after a data refresh), the chart falls back to plain wording computed from the numbers, and `facts.md` lists
every claim and whether it held.

## Data (`data/`, git-ignored)

`extract.py` reads OPM EHRI's HuggingFace mirror (`impactproject/opm-ehri-data`), the newest version of each monthly file, and
writes small aggregates to `data/` (its header lists them). It also saves ICE's USAJOBS postings for series 1801 and 1811, which
`build.py` uses to check chart 1's job label. The cache in `data/cache/` is named by file version, so a month OPM republishes is
read again on the next run.

Years of service are computed from the leave service date (`service_computation_date_leave`) in every file, not read from
OPM's `length_of_service_years`. OPM's field switched definition, without a note: from the March 2026 files on it equals the time
since that date, military time included (OPM's [documented definition](https://www.opm.gov/data/datasets/Files/763/50647e85-a9ae-4123-8866-022059c5f340.pdf)); before, it often left military time out. Using the field as
reported would put 2026 departures on one definition and the January staff they're divided by on the other. `facts.md` reports
when the switch happened, and `tables/years_of_service_as_published.csv` shows what the field as published would do: 2026's 20+ years quit rate would
look like a record and prior service among non-veteran new hires like it doubled.

Chart 1 and the fall-class comparison match departures to hires without person IDs, which OPM's public files don't have: a
departure's hire month is its effective month minus its years of service.

Two other data problems are handled in code and reported in `facts.md`: years of service of `MAX_LOS` (100) or more is a placeholder
start date (about 7,000 departures in OPM's June 2024-April 2025 files) and counts as not reported; and records for recent months
keep arriving in later files, far more since late 2025, so the partial year is also shown with an estimate and range once late
records arrive (`LAG_H`, `LAG_SAMPLE` in `config.py`).

Settings shared by both scripts (periods, thresholds, service bands) are in `config.py`; definitions (permanent appointments, departure types) are at the top of `build.py`. Every number in `facts.md` and on the charts is computed from the data or taken from `config.py`: `check_literals.py`, which `build.py` runs at the end, fails if a digit is typed into the text.
