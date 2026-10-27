import os

# Every setting the extract and the build share, in one place. facts.md text takes its dates and thresholds from here
# or from the data; check_literals.py fails if a digit is typed into the text instead.

# ---- periods (YYYYMM) ----
# The comparison period. "Usual" and "normal" in facts.md mean the average of the years from FIRST to the year before INAUG,
# and a group's "old high" is its highest year in that span. Change the year and run `python3 run.py` (or set it in
# run.ipynb, or FIRST=201801 python3 run.py): the extract reads any years it doesn't have yet, and every number, chart and
# title is recomputed. Chart titles that make a claim fall back to plain wording when the claim doesn't hold (listed in facts.md).
# Every rate is per 1,000 January staff, and OPM's January staff counts start in January 2012, so FIRST can go back to 2012.
# The rookie screen and ICE cohorts have their own start dates below and don't move with FIRST.
FIRST = os.environ.get("FIRST", "201501")
INAUG = "202501"          # the inauguration month: the "before" snapshot for every comparison from then on
assert FIRST[4:] == "01" and "201201" <= FIRST <= f"{int(INAUG[:4]) - 1}01", "FIRST: a January from 2012 to the year before INAUG"
MONTHLY_FROM = "202411"   # monthly headcount files read from here (January files are read from FIRST)
ICE_FROM = "202509"       # ICE's hiring surge: chart 1's cohorts start here
ROOKIE_FROM = "202309"    # rookie screen: autumn cohorts from this year on
USAJOBS_FROM = "2025-06-01"   # ICE job postings (chart 1's label check) opened on or after this date

# ---- appointments ----
PERM = "('10', '15', '30', '32', '35', '36', '38', '50', '67')"   # permanent appointments, political excluded

# ---- years of service ----
LOS_CUTS = (2, 5, 10, 20, 30)   # extract.py's bands (under 2, 2-5, 5-10, 10-20, 20-30, 30+)
SCD_TOL = 0.2              # OPM's years of service "agrees" with the leave service date when within this many years (scd_check)
BAND_CUTS = (5, 20)             # the charts' three bands: under 5, 5-20, 20+ (each a merge of extract bands)

# ---- cohorts ----
AUTUMN = ("09", "12")     # rookie screen: hires in these months (September-December), followed to the next PARTIAL_TO month
MAX_LOS = 100             # years of service at or above this are a placeholder start date (OPM's June 2024-April 2025 files carry
                          # ~7,000 departures with 124-125 years), so they count as not reported
NEW_HIRE_LOS = 0.25       # a new hire with under this many years (3 months) of service at hire had no prior federal service
SCREEN_RISES = (5, 10)    # rookie screen: count components whose share leaving rose by at least these many points

# ---- age (OPM reports five-year age brackets) ----
YOUNG = ("LESS THAN 20", "20-24", "25-29")   # "young": under 30
# Retirement eligibility from an age bracket and years of service. FERS and CSRS give an immediate unreduced annuity at
# 60 with 20 years, 62 with 5, or the minimum retirement age (55-57) with 30; a reduced one at the minimum age with 10.
# A five-year bracket can't place 62 or the minimum age, so eligibility comes as a range:
ELIGIBLE_SURE = (("60-64", 20), ("65 OR MORE", 5))           # (bracket, years of service): everyone here qualifies
ELIGIBLE_MAYBE = (("55-59", 10), ("60-64", 5))               # ... some here do (62+, or at the minimum age); upper bound = SURE + MAYBE

# ---- education of new hires ----
# Series OPM requires a degree for (attorney, physician, professional engineers, physicist, chemist). An agency that records
# EDU_BAD or more of its hires in them as below a bachelor's (2015 on, with MIN_DEGREE_HIRES or more such hires) has
# education at hire recorded unreliably; its hires are left out of the education figures in every year. EDU_CHECK: the
# other cutoffs shown, to see whether the answer depends on the choice (1 = no agency left out).
DEGREE_SERIES = ("0602", "0905", "0801", "0810", "0830", "0850", "0854", "0855", "0861", "1310", "1320")
EDU_BAD, EDU_CHECK, MIN_DEGREE_HIRES = 0.10, (1, 0.20), 200

# ---- reporting lag: records keep arriving in later monthly files ----
LAG_H = 6                 # a month counts as complete with the records that arrive within this many months
LAG_SAMPLE = 6            # the most recent this-many months with LAG_H months of follow-up give the expected arrival pattern
CUSHIONS = (1, 2, 3)      # check: also compare with the newest 1, 2, 3 months left out

# ---- thresholds ----
PER = 1000                # rates are per 1,000 staff
MIN_STAFF = 2000          # occupations compared on their own need this many permanent staff
MIN_QUITS = 30            # ... and this many quits in the partial year, for quit ratios
MIN_ATTORNEYS = 300       # agencies listed for attorney quits need this many attorneys
MIN_AGENCY_HIRES = 200    # where hiring is happening: agencies and occupations listed need this many average same-months hires
TOP = 10                  # ... and the lists show this many
MIN_SCREEN_HIRES = 100    # rookie screen: autumn new hires a component needs in every screened year
FLOW_GAP_PCT = 10         # occupations whose headcount and recorded flows differ by more than this % of staff are left out
LOW_INDEX, RECOVERY = 90, 5   # "dropped then recovered": fell to this index or below, then regained this many points
GLITCH_PCT = 5            # a monthly agency count this % off both neighbours that comes straight back is flagged
AT_WILL = {"44": "Schedule C", "55": "noncareer SES", "60": "limited-term SES", "67": "Schedule Policy/Career", "68": "Schedule Policy/Career (nonpermanent)"}
TERM_STARTS = ("201701", "202101", "202501")   # inauguration months: at-will appointments are compared at the same point in each term
NONPERM_ATTORNEY = ("40", "48")   # DOJ's nonpermanent attorney appointment codes (excepted service, nonpermanent)

USAJOBS = "https://pub-317c58882ec04f329b63842c1eb65b0c.r2.dev/data"   # the usajobs_historical archive
