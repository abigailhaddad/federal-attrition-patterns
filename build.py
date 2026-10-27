# The charts and facts for the federal attrition post, from the OPM EHRI aggregates extract.py writes to data/.
# python3 build.py  ->  charts/*.png with the CSV behind each, charts/facts.md, charts/rookie_screen.csv
import subprocess, sys
from pathlib import Path
import duckdb
from config import (MONTHLY_FROM, AT_WILL, TERM_STARTS, DEGREE_SERIES, EDU_BAD, EDU_CHECK, MIN_DEGREE_HIRES, SCD_TOL, FIRST, INAUG, ICE_FROM, USAJOBS_FROM, LOS_CUTS, BAND_CUTS, PER, MIN_STAFF, MIN_QUITS, MIN_ATTORNEYS,
                    MIN_SCREEN_HIRES, FLOW_GAP_PCT, LOW_INDEX, RECOVERY, GLITCH_PCT, NONPERM_ATTORNEY,
                    AUTUMN, NEW_HIRE_LOS, SCREEN_RISES, ROOKIE_FROM, YOUNG, ELIGIBLE_SURE, ELIGIBLE_MAYBE, MIN_AGENCY_HIRES, TOP, MAX_LOS, LAG_H, LAG_SAMPLE, CUSHIONS)
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

DATA, OUT = Path("data"), Path("charts")
OUT.mkdir(exist_ok=True)
for old in OUT.glob("*"):
    if old.is_file():
        old.unlink()

# ---- definitions ----------------------------------------------------------------------------------------
from config import PERM   # permanent appointment codes
TRANSFERS = "('SA', 'SB')"                                     # transfers to another agency aren't departures
# The newest OPM file sets the period: its year is the partial year, shown with an asterisk.
PARTIAL_TO = duckdb.sql(f"SELECT max(file) FROM '{DATA}/sep.parquet'").fetchone()[0]
assert PARTIAL_TO[4:] != "12", "newest file is December: the partial-year logic below assumes an incomplete year"
# The analysis starts at FIRST, the first January staff file read (every rate is per January staff).
START = duckdb.sql(f"SELECT min(snap) FROM '{DATA}/emp.parquet' WHERE snap LIKE '%01'").fetchone()[0]
assert START == FIRST, (START, FIRST, "run extract.py for this FIRST")
YEARS = list(range(int(START[:4]), int(PARTIAL_TO[:4]) + 1))
LAST_FULL = YEARS[-2]
SHOCK = int(INAUG[:4])                       # the year the changes began
BASE_YEARS = list(range(YEARS[0], SHOCK))    # the years before
BASE = f"{BASE_YEARS[0]}-{BASE_YEARS[-1]}"


def month(ym):
    return pd.Timestamp(f"{ym[:4]}-{ym[4:]}-01").strftime("%B %Y")


def months_between(a, b):
    return [str(p).replace("-", "") for p in pd.period_range(f"{a[:4]}-{a[4:]}", f"{b[:4]}-{b[4:]}", freq="M")]


NEWEST = month(PARTIAL_TO)
JAN = month(INAUG)                                     # the "before" snapshot, as text
AFTER = months_between(INAUG, PARTIAL_TO)[1]           # flows after that snapshot start the next month
RATE = f"per {PER:,}"
AUT = "-".join(pd.Timestamp(f"2000-{m_}-01").strftime("%B") for m_ in AUTUMN)   # "September-December"
MONTH_SPAN = f"January-{pd.Timestamp(f'2000-{PARTIAL_TO[4:]}-01'):%B}"
MONTHS = {y: 12 for y in YEARS if y <= LAST_FULL} | {YEARS[-1]: int(PARTIAL_TO[4:])}
YEAR_LABELS = [str(y) for y in YEARS[:-1]] + [f"{YEARS[-1]}*\nJan-{pd.Timestamp(f'2000-{PARTIAL_TO[4:]}-01'):%b}"]   # the partial year, labelled as such
BANDS = {"a": f"Under {BAND_CUTS[0]} years", "b": f"{BAND_CUTS[0]}-{BAND_CUTS[1]} years", "c": f"{BAND_CUTS[1]}+ years"}
U2, OVER30 = f"under {LOS_CUTS[0]} years", f"{LOS_CUTS[-1]}+ years"   # extract.py's lowest and highest bands
BAND_SQL = ("CASE WHEN los IN ('a<2', 'b2-5') THEN 'a' WHEN los IN ('c5-10', 'd10-20') THEN 'b' "
            "WHEN los IN ('e20-30', 'f30+') THEN 'c' END")
# Departure types, checked in order (buyout first: DRP exits are coded as quits or retirements).
# The two unusual exits come first, so they also stack first.
TYPES = {"Deferred resignation (DRP)": "{drp} = 'Y'", "Layoff (RIF)": "{cat} = 'SH'", "Retirement": "{cat} IN ('SD', 'SE', 'SG')",
         "Quit": "{cat} = 'SC'", "Other": "TRUE"}
DEFENSE = ("DD", "AR", "NV", "AF")   # agency codes of the Defense Department and the three military departments
EXAMPLES = {"TR 0592": "IRS tax examiners", "HE 0343": "HHS management analysts", "VA 0610": "VA nurses",
            "VA 0996": "VA claims examiners", "HS 1896": "Border Patrol agents"}

# ---- style: The Present of Coding brand; one meaning per color across all four charts --------------------
# Accents only where the point is (buyout amber, layoff red); ordinary exits are warm browns; years of service is
# a forest-green ramp; the heatmap shades in the brand's dark brown. Checked against the warm white surface.
TYPE_COLOR = dict(zip(TYPES, ["#D4A03C", "#C0392B", "#6F8F9E", "#634F40", "#DCC6A6"]))   # amber, red, slate, brown, tan
BAND_COLOR = dict(zip(BANDS.values(), ["#7DB596", "#4A9070", "#2D6A4F"]))
STAYED = "#B8A898"                                                                      # still on the job: outline only
INK, MUTED, GRID, SURFACE = "#3D2B1F", "#7A6E62", "#E8DDD0", "#FFF8F0"
INTENSITY = LinearSegmentedColormap.from_list("brown", ["#F5EDE0", "#3D2B1F"])          # heatmap: more = darker
DARK = {TYPE_COLOR["Layoff (RIF)"], TYPE_COLOR["Quit"], BAND_COLOR[BANDS["c"]]}        # fills that take light text
for f in Path("fonts").glob("*.ttf"):
    matplotlib.font_manager.fontManager.addfont(str(f))
SOURCE = "Source: OPM Enterprise Human Resources Integration (EHRI) data, files through {thru}. Permanent appointments."
WIDTH = 10
plt.rcParams.update({"font.family": "Source Sans 3", "font.size": 10.5, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.spines.left": False, "axes.edgecolor": GRID,
                     "xtick.color": MUTED, "ytick.color": INK, "xtick.major.size": 0, "ytick.major.size": 0,
                     "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE})


def frame(height, top_in=0.68, bottom_in=0.9, left=0.16, right=0.86):
    """A figure with the same title band and footnote band, in inches, whatever its height."""
    fig, ax = plt.subplots(figsize=(WIDTH, height))
    fig.subplots_adjust(top=1 - top_in / height, bottom=bottom_in / height, left=left, right=right)
    return fig, ax


def finish(fig, name, title, subtitle, notes, thru=None, perm=True):
    # No text above or below the plot: the post carries the headline, the description and the notes (all listed in facts.md).
    HEADLINES.append((name, title))
    src = SOURCE.format(thru=thru or NEWEST)
    NOTES.append((name, [subtitle.rstrip(".") + "."] + notes + [src if perm else src.replace("Permanent appointments.", "All appointment types.")]))   # not on the image: footnotes in the post, listed in facts.md
    fig.savefig(OUT / f"{name}.png", dpi=200, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


HEADLINES = []   # (chart file, suggested headline)
NOTES = []       # (chart file, notes for the post's footnotes)
CLAIMS = []   # (chart, claim, held, wording used): chart titles and notes that make a claim the data has to support
(OUT / "tables").mkdir(exist_ok=True)
for old in (OUT / "tables").glob("*.csv"):
    old.unlink()


def table(name, df):
    """Save a table the notebook shows next to the post's sections (charts/tables/NAME.csv); everything in it is from above."""
    df.to_csv(OUT / "tables" / f"{name}.csv")


def claim(chart, ok, said, instead):
    """The claim `said` if the data supports it (ok), else the plain wording `instead`. Every claim is listed in facts.md, so
    a run with other settings (a different FIRST, say) still finishes and says which claims no longer hold."""
    CLAIMS.append((chart, said, bool(ok), said if ok else instead))
    return said if ok else instead


def thousands(v):
    return f"{v / 1000:.0f}k" if v >= 10_000 else f"{v / 1000:.1f}k"


db = duckdb.connect()
for t in ("sep", "emp"):
    db.execute(f"CREATE VIEW {t} AS SELECT * FROM '{DATA}/{t}.parquet' WHERE appt IN {PERM}")


def type_case(drp, cat):
    return "CASE " + " ".join(f"WHEN {w.format(drp=drp, cat=cat)} THEN '{t}'" for t, w in TYPES.items()) + " END"


# ---- 1. ICE's new officers vs Border Patrol's ------------------------------------------------------------
# From extract.py (every file from September 2025 on; it carries pay plan and exact years of service, from the leave service
# date). Matched cohorts: new hires with under 3 months of creditable service (federal civilian or military), and departures
# whose hire month (departure month minus years of service) is September 2025 or later. A veteran whose military time is
# credited is in neither: not counted as a new hire, and dated before the window if they leave. Transfers to another agency are not departures here either.
ACC, SEP = f"{DATA}/acc_ice_cbp.parquet", f"{DATA}/sep_ice_cbp.parquet"
# This extract has appointment labels, not codes: the labels of the PERM codes above. Noncareer SES (55, political) is
# labeled "... SENIOR EXECUTIVE SERVICE PERMANENT", so matching on the word "permanent" would let it in.
PERM_LABELS = ("CAREER (COMPETITIVE SERVICE PERMANENT)", "CAREER-CONDITIONAL (COMPETITIVE SERVICE PERMANENT)",
               "SCHEDULE A (EXCEPTED SERVICE PERMANENT)", "SCHEDULE B (EXCEPTED SERVICE PERMANENT)",
               "SCHEDULE D (EXCEPTED SERVICE PERMANENT)", "EXECUTIVE (EXCEPTED SERVICE PERMANENT)",
               "OTHER (EXCEPTED SERVICE PERMANENT)", "CAREER (SENIOR EXECUTIVE SERVICE PERMANENT)",
               "SCHEDULE POLICY/CAREER (EXCEPTED SERVICE PERMANENT)")
NOT_PERM_LABELS = ("NONPERMANENT (COMPETITTIVE SERVICE NONPERMANENT)", "SCHEDULE A (EXCEPTED SERVICE NONPERMANENT)",
                   "SCHEDULE B (EXCEPTED SERVICE NONPERMANENT)", "SCHEDULE C (EXCEPTED SERVICE NONPERMANENT)",
                   "SCHEDULE D (EXCEPTED SERVICE NONPERMANENT)", "EXECUTIVE (EXCEPTED SERVICE NONPERMANENT)",
                   "OTHER (EXCEPTED SERVICE NONPERMANENT)", "NONCAREER (SENIOR EXECUTIVE SERVICE PERMANENT)",
                   "LIMITED TERM (SENIOR EXECUTIVE SERVICE NONPERMANENT)", "LIMITED EMERGENCY (SENIOR EXECUTIVE SERVICE NONPERMANENT)",
                   "SCHEDULE POLICY/CAREER (EXCEPTED SERVICE NONPERMANENT)")
for f in (ACC, SEP):
    seen = {r[0] for r in db.sql(f"SELECT DISTINCT appointment_type FROM '{f}'").fetchall()}
    assert seen <= set(PERM_LABELS) | set(NOT_PERM_LABELS), f"unclassified appointment labels in {f}: {seen - set(PERM_LABELS) - set(NOT_PERM_LABELS)}"
PERM_LBL = "appointment_type IN (" + ", ".join(f"'{x}'" for x in PERM_LABELS) + ")"
ICE_SERIES, BP_SERIES, LE_PLAN = ("1801", "1811"), ("1896",), "GL"   # deportation officer, criminal investigator; Border Patrol agent; law-enforcement pay plan
sql_in = lambda xs: "(" + ", ".join(f"'{x}'" for x in xs) + ")"
COHORTS = {"ICE deportation officers and criminal investigators":
               f"agy_code = 'HSBB' AND pay_plan_code = '{LE_PLAN}' AND occupational_series_code IN {sql_in(ICE_SERIES)}",
           "Border Patrol agents": f"agy_code = 'HSBD' AND pay_plan_code = '{LE_PLAN}' AND occupational_series_code IN {sql_in(BP_SERIES)}"}
LOS = "TRY_CAST(service_years AS DOUBLE)"
HIRE_YM = f"strftime(make_date(left(event_ym, 4)::INT, right(event_ym, 2)::INT, 15) - to_months(CAST(round({LOS} * 12) AS INT)), '%Y%m')"
ym = months_between(ICE_FROM, PARTIAL_TO)
fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 4.9), sharey=True)
fig.subplots_adjust(top=1 - 1.13 / 4.9, bottom=1.35 / 4.9, left=0.07, right=0.98, wspace=0.08)
rows = []
for ax, (name, fp) in zip(axes, COHORTS.items()):
    hired = db.sql(f"""SELECT event_ym, sum(count) n FROM '{ACC}' WHERE {fp} AND {PERM_LBL} AND accession_category LIKE 'NEW HIRE%'
        AND event_ym >= '{ym[0]}' AND {LOS} < {NEW_HIRE_LOS} GROUP BY 1""").df().set_index("event_ym").n.reindex(ym, fill_value=0).cumsum()
    left = db.sql(f"""SELECT event_ym, {type_case('drp_indicator', 'separation_category_code')} typ, sum(count) n FROM '{SEP}'
        WHERE {fp} AND {PERM_LBL} AND separation_category_code NOT IN {TRANSFERS} AND event_ym >= '{ym[0]}' AND {HIRE_YM} >= '{ym[0]}'
        GROUP BY ALL""").df().pivot(index="event_ym", columns="typ", values="n").reindex(index=ym, columns=list(TYPES)).fillna(0).cumsum()
    assert (left.sum(axis=1) <= hired).all()
    rows.append(left.assign(group=name, hired_so_far=hired))
    x, bottom = np.arange(len(ym)), np.zeros(len(ym))
    for t in TYPES:
        if left[t].iloc[-1] > 0:
            ax.bar(x, left[t], bottom=bottom, color=TYPE_COLOR[t], width=0.74, edgecolor=SURFACE, linewidth=1)
            bottom += left[t].values
    ax.bar(x, hired - bottom, bottom=bottom, facecolor="none", width=0.74, edgecolor=STAYED, linewidth=1.1)
    gone = left.iloc[-1].sum()
    ax.text(x[-1], hired.iloc[-1] + 150, f"{gone:,.0f} of {hired.iloc[-1]:,.0f}\nhave left ({gone / hired.iloc[-1]:.0%})",
            ha="center", va="bottom", fontsize=10, color=INK, fontweight=600)
    ax.set_title(name, loc="left", fontsize=11.5, color=INK, pad=8, family="DM Sans", fontweight=600)
    ax.set_xticks(x, [pd.Timestamp(f"{m[:4]}-{m[4:]}-01").strftime("%b\n%Y" if m[4:] in ("09", "01") else "%b") for m in ym])
    ax.grid(axis="y", color=GRID); ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.tick_params(axis="y", colors=MUTED)
axes[0].set_ylim(0, 7000)
shown = [t for t in TYPES if any(r[t].iloc[-1] > 0 for r in rows)]
OPM_LABEL = {"Quit": "quit", "Other": "termination (expired appt/other) or other separation"}   # OPM's own category names
fig.legend([plt.Rectangle((0, 0), 1, 1, facecolor="none", edgecolor=STAYED, linewidth=1.1)]
           + [plt.Rectangle((0, 0), 1, 1, color=TYPE_COLOR[t]) for t in shown],
           ["Still on the job"] + [f"Left: {OPM_LABEL.get(t, t.lower())}" for t in shown], ncol=1 + len(shown), frameon=False,
           loc="upper left", bbox_to_anchor=(0.006, 1 - 0.46 / 4.9), fontsize=10, handlelength=1)
pd.concat(rows).to_csv(OUT / "1_ice_new_hires_who_left.csv")
ice_last = rows[0].iloc[-1]
ice_share = ice_last[list(TYPES)].sum() / ice_last.hired_so_far
bp_share = rows[1].iloc[-1][list(TYPES)].sum() / rows[1].iloc[-1].hired_so_far
FAR = 3   # "far faster": ICE's share who left at least this many times Border Patrol's
claim("ICE heading", 0.27 <= ice_share <= 0.33, "Three in ten of ICE's new officers have already left", f"{ice_share:.0%} of ICE's new officers have already left")
finish(fig, "1_ice_new_hires_who_left", claim("Chart 1 title", ice_share >= FAR * bp_share, "ICE's new officers are leaving far faster than Border Patrol's",
                                             f"{ice_share:.0%} of ICE's new officers have left, against {bp_share:.0%} of Border Patrol's"),
       f"People hired since {month(ym[0])} with no prior federal civilian or military service: running total each month, by whether they are still there",
       [f"New to federal service: under {NEW_HIRE_LOS * 12:.0f} months of creditable federal civilian or military service at hire. ICE officers: series "
        f"{' and '.join(ICE_SERIES)}; Border Patrol agents: series {' and '.join(BP_SERIES)}; both on the {LE_PLAN} law-enforcement pay plan.",
        "OPM's public files don't follow individual people, so a departure's hire month is its effective month minus its years of service; "
        "in every month the running count who have left is at most the running count hired (checked).",
        "Transfers to other agencies are not counted. Recent months fill in as late records arrive.",
        "OPM's \"other separation\" category includes removals for discipline or performance, and deaths."],
       thru=f"{NEWEST} (entry law-enforcement pay plan)")

# ---- 2. How each example lost people in SHOCK (the whole year) ----------------------------------------------
EX_TO = f"{SHOCK}12"
d2 = db.sql(f"""SELECT agency_code || ' ' || occupational_series_code k, {type_case('drp', 'cat')} typ, sum(n) n FROM sep
    WHERE cat NOT IN {TRANSFERS} AND eff BETWEEN '{INAUG}' AND '{EX_TO}' GROUP BY ALL""").df()
d2 = d2[d2.k.isin(EXAMPLES)].pivot(index="k", columns="typ", values="n").reindex(index=list(EXAMPLES), columns=list(TYPES)).fillna(0)
staff25 = db.sql(f"SELECT agency_code || ' ' || occupational_series_code k, sum(n) n FROM emp WHERE snap = '{INAUG}' GROUP BY 1").df().set_index("k").n.reindex(list(EXAMPLES))
share = d2.div(staff25, axis=0) * 100
d2.assign(january_2025_staff=staff25).astype(int).to_csv(OUT / "2_how_people_left.csv")
fig, ax = frame(5.0, top_in=0.73, bottom_in=1.4, left=0.24, right=0.97)
y, bottom = np.arange(len(EXAMPLES))[::-1], np.zeros(len(EXAMPLES))
for t in TYPES:
    ax.barh(y, share[t], left=bottom, color=TYPE_COLOR[t], height=0.64, edgecolor=SURFACE, linewidth=1.5)
    for yi, b, w in zip(y, bottom, share[t]):
        if w >= 4:
            ax.text(b + w / 2, yi, f"{w:.0f}%", ha="center", va="center", fontsize=9.5, color=SURFACE if TYPE_COLOR[t] in DARK else INK)
    bottom += share[t].values
for yi, k, tot in zip(y, EXAMPLES, bottom):
    ax.text(tot + 0.6, yi, f"{tot:.0f}%  ({d2.loc[k].sum():,.0f} people)", va="center", fontsize=9.5, color=INK)
ax.set_yticks(y, [f"{EXAMPLES[k]}\n{staff25[k]:,.0f} staff" for k in EXAMPLES], fontsize=10)
ax.set_xticks([]); ax.spines["bottom"].set_visible(False); ax.set_xlim(0, bottom.max() * 1.3)
fig.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in TYPE_COLOR.values()], list(TYPES), ncol=5, frameon=False,
           loc="lower left", bbox_to_anchor=(0.24, 0.8 / 5.0), fontsize=9.5, handlelength=1)
finish(fig, "2_how_people_left", f"How five occupations lost staff in {SHOCK}",
       f"Permanent staff who left in {SHOCK}, as a share of {JAN} staff, by how they left",
       ["Layoff (RIF): separations agencies coded as a reduction in force. Other: terminations (expired appointments and other) and OPM's \"other separation\",",
        "which includes removals for discipline or performance, and deaths.",
        "Retirement includes disability retirement. Transfers to other agencies are not counted."])

KIND = {"quit": "cat = 'SC' AND drp <> 'Y'", "retire": "cat IN ('SD', 'SE', 'SG') AND drp <> 'Y'", "total": f"cat NOT IN {TRANSFERS}"}

# ---- Reporting lag: records for a month keep arriving in later files, and since late 2025 far more of them do ----
# A month counts as complete with the records that arrive within LAG_H months (lag = file month - effective month).
# The LAG_SAMPLE most recent months with that much follow-up give the share of a month's records that has arrived after
# 0, 1, 2 ... months; each partial-year month is scaled up by the share expected at its age. The middle estimate uses the
# median share across the sample months, the range the most and least complete of them. Earlier years are counted the
# same way (records within LAG_H months), so they're complete too.
mi = lambda ym: int(ym[:4]) * 12 + int(ym[4:]) - 1
ym_of = lambda i: f"{i // 12}{i % 12 + 1:02d}"
LAG_SQL = "((substr(file, 1, 4)::INT * 12 + substr(file, 5, 2)::INT) - (substr(eff, 1, 4)::INT * 12 + substr(eff, 5, 2)::INT))"
LAG_MONTHS = [ym_of(mi(PARTIAL_TO) - LAG_H - k) for k in range(LAG_SAMPLE)][::-1]
LAG_TABLES = {"total": ("sep", KIND["total"]), "quit": ("sep", KIND["quit"]), "retire": ("sep", KIND["retire"]),
              "hires": (f"'{DATA}/acc.parquet'", f"appt IN {PERM} AND cat IN ('AC', 'AD', 'AE')")}
LAG_TXT = {"total": "departures", "quit": "quits", "retire": "retirements", "hires": "new hires"}


def arrived(kind):
    """Share of each sample month's records (within LAG_H months) that had arrived by each lag; index lag, columns month."""
    t, w = LAG_TABLES[kind]
    d = db.sql(f"""SELECT eff, greatest({LAG_SQL}, 0) lag, sum(n) n FROM {t} WHERE ({w}) AND {LAG_SQL} <= {LAG_H}
        AND eff IN ({', '.join(f"'{m}'" for m in LAG_MONTHS)}) GROUP BY ALL""").df()
    c = d.pivot_table(index="lag", columns="eff", values="n", aggfunc="sum").reindex(range(LAG_H + 1)).fillna(0).cumsum()
    return c / c.iloc[-1]


ARRIVED = {k: arrived(k) for k in LAG_TABLES}


def lag_estimate(kind):
    """Partial year, January to the newest month: (observed, estimate, low, high) once every month is complete."""
    t, w = LAG_TABLES[kind]
    obs = db.sql(f"SELECT eff, sum(n) n FROM {t} WHERE ({w}) AND eff BETWEEN '{YEARS[-1]}01' AND '{PARTIAL_TO}' GROUP BY 1").df().set_index("eff").n
    share = lambda e, how: ARRIVED[kind].loc[mi(PARTIAL_TO) - mi(e)].agg(how) if mi(PARTIAL_TO) - mi(e) < LAG_H else 1.0
    return obs.sum(), *(sum(obs[e] / share(e, how) for e in obs.index) for how in ("median", "max", "min"))


LAG = {k: lag_estimate(k) for k in LAG_TABLES}
LAG_FACTOR = {k: tuple(v / LAG[k][0] for v in LAG[k][1:]) for k in LAG}   # (estimate, low, high) / observed

# ---- 3 and 4 share one query: departures by years of service, whole years plus the partial year ------------
# Complete years count every record, late arrivals included. Departures are banded by service at departure,
# staff by service in January.
full = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, {BAND_SQL} los, sum(n) n FROM sep
    WHERE cat NOT IN {TRANSFERS} AND los <> 'NA'
      AND (substr(eff, 1, 4)::INT BETWEEN {YEARS[0]} AND {LAST_FULL} OR eff BETWEEN '{YEARS[-1]}01' AND '{PARTIAL_TO}')
    GROUP BY ALL""").df().pivot(index="los", columns="yr", values="n")
jan = db.sql(f"""SELECT substr(snap, 1, 4)::INT yr, {BAND_SQL} los, sum(n) n FROM emp
    WHERE snap LIKE '%01' AND los <> 'NA' GROUP BY ALL""").df().pivot(index="los", columns="yr", values="n")
assert set(full.index) == set(jan.index) == set(BANDS), (full.index, jan.index)   # no unbanded rows
full, jan = full.loc[list(BANDS), YEARS], jan.loc[list(BANDS), YEARS]
full.index = jan.index = list(BANDS.values())
assert full.notna().all().all() and jan.notna().all().all()

# ---- Same-months comparisons: January through the newest month of every year, each year counted only from files
# up to that month, so every year covers the same months. Pace = per month per 1,000 January staff.
LAST_M = PARTIAL_TO[4:]
WINDOW = f"substr(eff, 5, 2) <= '{LAST_M}' AND file <= substr(eff, 1, 4) || '{LAST_M}' AND substr(eff, 1, 4)::INT >= {YEARS[0]}"

# 3. People who left each year, stacked by years of service
full.astype(int).to_csv(OUT / "3_who_left_by_service.csv")
fig, ax = frame(5.2, bottom_in=1.15, right=0.84, left=0.03)
x, bottom = np.arange(len(YEARS)), np.zeros(len(YEARS))
for band, row in full.iterrows():
    ax.bar(x, row, bottom=bottom, color=BAND_COLOR[band], width=0.72, edgecolor=SURFACE, linewidth=1.5)
    ax.text(x[-1] + 0.5, bottom[-1] + row.iloc[-1] / 2, f"{band}  {thousands(row.iloc[-1])}", va="center", fontsize=9.5, color=INK)
    bottom += row.values
for k, t in enumerate(bottom):
    ax.text(k, t + bottom.max() * 0.012, thousands(t) + ("*" if k == len(YEARS) - 1 else ""), ha="center", fontsize=9.5,
            color=INK, fontweight=600 if k == len(YEARS) - 1 else "normal")
ax.set_xticks(x, YEAR_LABELS); ax.set_yticks([]); ax.set_xlim(-0.6, len(YEARS) - 0.4)
x3 = full[SHOCK].sum() / full[list(range(YEARS[0], SHOCK))].sum().mean()
claim("2025 text", x3 > 2, f"More than twice as many permanent employees left in {SHOCK} as in a typical year", f"{x3:.1f} times as many permanent employees left in {SHOCK}")
finish(fig, "3_who_left_by_service", "People who left each year, by years of service",
       "Permanent federal employees who left each year, by years of service",
       [f"*{YEARS[-1]} is {MONTH_SPAN.replace('-', ' through ')} only, so its bar is not comparable in height with the full years.",
        "DRP exits are included; transfers to other agencies are not."])

# 4. Pace of leaving: departures per month per 1,000 January staff
# the same months every year (WINDOW), so no year's pace depends on which months it covers
win = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, {BAND_SQL} los, sum(n) n FROM sep WHERE cat NOT IN {TRANSFERS} AND los <> 'NA' AND {WINDOW}
    GROUP BY ALL""").df().pivot(index="los", columns="yr", values="n").loc[list(BANDS), YEARS]
win.index = list(BANDS.values())
pace = win / int(LAST_M) / jan * 1000
pace.loc["All permanent staff"] = win.sum() / int(LAST_M) / jan.sum() * 1000
pace = pace.loc[["All permanent staff"] + list(BANDS.values())]


# Permanent staff each month from MONTHLY_FROM (the monthly headcount files), for the occupation and Schedule Policy/Career checks
db.execute(f"CREATE VIEW hc AS SELECT * FROM '{DATA}/hc.parquet' WHERE appt IN {PERM}")




FULL_YEARS = f"(substr(eff, 1, 4)::INT BETWEEN {YEARS[0]} AND {LAST_FULL} OR eff BETWEEN '{YEARS[-1]}01' AND '{PARTIAL_TO}')"


def window_pace(key, where="TRUE", full=False):
    """{kind: DataFrame of pace, index = group, columns = year}, plus January staff by group and year.
    full=False: the same months every year (WINDOW). full=True: whole years, the partial year as far as it goes."""
    d = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, {key} g, """ + ", ".join(f"sum(n) FILTER (WHERE {w}) {k}" for k, w in KIND.items())
               + f" FROM sep WHERE {FULL_YEARS if full else WINDOW} AND ({where}) GROUP BY ALL").df()
    j = db.sql(f"SELECT substr(snap, 1, 4)::INT yr, {key} g, sum(n) n FROM emp WHERE snap LIKE '%01' AND ({where}) GROUP BY ALL").df()
    m = d.merge(j, on=["yr", "g"])
    staff = m.pivot(index="g", columns="yr", values="n")
    months_ = m.yr.map(MONTHS) if full else int(LAST_M)
    return {k: m.assign(p=m[k].fillna(0) / months_ / m.n * 1000).pivot(index="g", columns="yr", values="p") for k in KIND}, staff, \
           {k: m.pivot(index="g", columns="yr", values=k).fillna(0) for k in KIND}


# ---- 6. Attorneys vs everyone else: quits -----------------------------------------------------------------
ATT_CODE = "0905"   # general attorney
ATT = f"occupational_series_code = '{ATT_CODE}'"
ATT_KEY = f"CASE WHEN {ATT} THEN 'Attorneys' ELSE 'Everyone else' END"
att_pace, att_staff, att_n = window_pace(ATT_KEY)            # same months every year: the chart and the facts
q6 = att_pace["quit"][YEARS]
r6 = q6.loc["Attorneys", YEARS[-1]] / q6.loc["Attorneys", BASE_YEARS].max()
att_ratio = att_pace["quit"].loc["Attorneys", YEARS[-1]] / att_pace["quit"].loc["Attorneys", BASE_YEARS].max()
head6 = claim("Chart 6 title", 1.7 <= r6 < 2.1, "Attorneys are quitting at nearly twice their old high",
             f"Attorneys are quitting at {r6:.1f} times their {YEARS[0]}-{SHOCK - 1} peak")   # drawn below, with the other quit rates the post names (chart 6)

# ---- 7. Experienced staff: quitting, not retiring --------------------------------------------------------
BAND_LABEL = BAND_SQL.replace("THEN 'a'", f"THEN '{BANDS['a']}'").replace("THEN 'b'", f"THEN '{BANDS['b']}'").replace("THEN 'c'", f"THEN '{BANDS['c']}'")
band_pace, band_staff, band_n = window_pace(BAND_LABEL, "los <> 'NA'")              # same months: the chart and the facts
q20, r20 = band_pace["quit"].loc[BANDS["c"]], band_pace["retire"].loc[BANDS["c"]]
q520, r520 = band_pace["quit"].loc[BANDS["b"]], band_pace["retire"].loc[BANDS["b"]]
# title check: 20+ years quitting "at about their PEAK7 peak": as reported within 5% of the 2015-2024 high, and with late
# records still within 15% of it
PEAK7 = q20[BASE_YEARS].idxmax()
r7 = q20[YEARS[-1]] / q20[PEAK7]
ok7q = 0.95 <= r7 and r7 * LAG_FACTOR["quit"][2] <= 1.15
# long-serving staff's retirements "aren't up", even after the most generous allowance for late-reported records
ok7r = r20[YEARS[-1]] * LAG_FACTOR["retire"][2] <= r20[BASE_YEARS].max()
rr7 = r20[YEARS[-1]] / r20[BASE_YEARS].max()

# ---- 4. One heatmap: all departures by years of service, then quits and retirements for 5-20 and 20+ years ---------
# Actual rates in every cell. The rows differ several-fold in size, so each row is shaded against its own range.
GROUPS4 = [("All departures", pace)] + [(lbl, band_pace[k].loc[[BANDS["b"], BANDS["c"]], YEARS]) for k, lbl in (("quit", "Quits"), ("retire", "Retirements"))]
heat = pd.concat({g: d[YEARS] for g, d in GROUPS4})
heat.round(2).to_csv(OUT / "4_leaving_pace_by_service.csv")
SMALL4 = 3   # rows whose rates are all below this show two decimals
shade = heat.sub(heat.min(axis=1), axis=0).div(heat.max(axis=1) - heat.min(axis=1), axis=0)
fig, ax = frame(0.5 * len(heat) + 1.5, bottom_in=1.1, left=0.33, right=0.99)
ax.imshow(shade.values, cmap=INTENSITY, aspect="auto", vmin=0, vmax=1)
for i in range(heat.shape[0]):
    for k in range(heat.shape[1]):
        v = heat.values[i, k]
        ax.text(k, i, f"{v:.1f}", ha="center", va="center", fontsize=10, color=SURFACE if shade.values[i, k] > 0.5 else INK,
                fontweight=600 if k == len(YEARS) - 1 else "normal")
ax.set_xticks(range(len(YEARS)), YEAR_LABELS); ax.set_yticks(range(len(heat)), [b_.replace("All permanent staff", "All staff") for _, b_ in heat.index])
ax.tick_params(axis="y", pad=16)
for sp in ax.spines.values():
    sp.set_visible(False)
row = 0
for g, d in GROUPS4:   # a group label left of each block, and a gap between blocks
    ax.text(0.01, row + (len(d) - 1) / 2, g, transform=matplotlib.transforms.blended_transform_factory(fig.transFigure, ax.transData),
            ha="left", va="center", fontsize=10.5, color=INK, fontweight=600)
    if row:
        ax.axhline(row - 0.5, color=SURFACE, lw=5)
    row += len(d)
for i, (_, band) in enumerate(heat.index):   # the same service colors as chart 3, as swatches
    if band in BAND_COLOR:
        ax.add_patch(plt.Rectangle((-0.64, i - 0.3), 0.08, 0.6, color=BAND_COLOR[band], clip_on=False))
lo4, hi4 = min(LAG_FACTOR[k][1] for k in ("total", "quit", "retire")), max(LAG_FACTOR[k][2] for k in ("total", "quit", "retire"))
ok4r = r20[YEARS[-1]] * LAG_FACTOR["retire"][0] < r20[BASE_YEARS].mean()   # "retirements are lower": below average even with the central late-records estimate
finish(fig, "4_leaving_pace_by_service", claim("Chart 4 title", ok7q and ok4r, f"Long-serving staff are quitting at about their {PEAK7} peak; retirements are lower",
                                               f"Long-serving staff: quits {r7:.2f} times their {YEARS[0]}-{SHOCK - 1} high, retirements {r20[YEARS[-1]] / r20[BASE_YEARS].mean():.2f} times their average"),
       f"Permanent employees who left per month, {RATE} on staff in January",
       [f"{MONTH_SPAN.replace('-', ' through ')} of every year. Each row is shaded against its own range. All departures include DRP exits; quits and retirements don't.",
        f"Transfers to other agencies are not counted. Retirement includes disability retirement. Records for recent months are still arriving: "
        f"once they do, {YEARS[-1]}* figures are likely {(lo4 - 1) * 100:.0f}-{(hi4 - 1) * 100:.0f}% higher."])

# ---- Rookie screen: did new hires leave unusually fast anywhere besides ICE? ----------------------------------
# Every agency component: new hires with no prior federal civilian or military service in the AUTUMN months of a year, and how many of them
# left (any departure but transfers) by the next August, counting only files up to that August. Departures are matched
# to the hire window by tenure (departure month minus months of service). Components need MIN_HIRES in every window.
RA, RS = f"{DATA}/rookie_acc.parquet", f"{DATA}/rookie_sep.parquet"
SCREEN_YEARS, MIN_HIRES = tuple(range(int(ROOKIE_FROM[:4]), YEARS[-1])), MIN_SCREEN_HIRES   # hiring autumns; the last is the newest
LATEST = SCREEN_YEARS[-1]
ROOKIE_HIRE_YM = "strftime(make_date(left(eff, 4)::INT, right(eff, 2)::INT, 15) - to_months(tenure_m), '%Y%m')"
parts = []
for y in SCREEN_YEARS:
    w0, w1, cut = f"{y}{AUTUMN[0]}", f"{y}{AUTUMN[1]}", f"{y + 1}{LAST_M}"
    hires_y = db.sql(f"""SELECT agency_subelement_code u, any_value(sub) component, sum(n) hires FROM '{RA}'
        WHERE appt IN {PERM} AND eff BETWEEN '{w0}' AND '{w1}' AND file <= '{cut}' GROUP BY 1""").df()
    left_y = db.sql(f"""SELECT agency_subelement_code u, sum(n) gone FROM '{RS}' WHERE appt IN {PERM} AND cat NOT IN {TRANSFERS}
        AND eff <= '{cut}' AND file <= '{cut}' AND {ROOKIE_HIRE_YM} BETWEEN '{w0}' AND '{w1}' GROUP BY 1""").df()
    parts.append(hires_y.merge(left_y, on="u", how="left").fillna({"gone": 0}).assign(year=y))
sc = pd.concat(parts)
sc["rate"] = sc.gone / sc.hires * 100
wide = sc.pivot(index="u", columns="year", values=["hires", "gone", "rate"])
screen = pd.DataFrame({"component": sc.groupby("u").component.first()} | {f"hires_{y}": wide["hires"][y] for y in SCREEN_YEARS}
                      | {f"left_{y}": wide["gone"][y] for y in SCREEN_YEARS} | {f"pct_left_{y}": wide["rate"][y] for y in SCREEN_YEARS})
screen = screen[(wide["hires"][list(SCREEN_YEARS)] >= MIN_HIRES).all(axis=1)].copy()
screen["rise"] = screen[f"pct_left_{LATEST}"] - screen[[f"pct_left_{y}" for y in SCREEN_YEARS[:-1]]].max(axis=1)
screen = screen.sort_values("rise", ascending=False)
screen.round(1).to_csv(OUT / "rookie_screen.csv")
all_latest_hires = sc[sc.year == LATEST].hires.sum()

# ---- facts.md: the numbers for the post, all computed above ---------------------------------------------------
newest = db.sql("SELECT max(file) FROM sep").fetchone()[0]
F = [f"# Facts for the post\n\nGenerated by `build.py` from OPM EHRI files through {month(newest)}. Permanent appointments "
     "unless noted; transfers to other agencies are not counted as leaving. Every number is computed from those files or read out of a downloaded source document (last section); none is typed in by hand.\n"]
h = lambda t: F.append(f"\n## {t}\n")
b = lambda t: F.append(f"- {t}")

h("1. ICE's new officers vs Border Patrol")
OTHER_CODES = "separation_category_code NOT IN ('SH', 'SD', 'SE', 'SG', 'SC', 'SA', 'SB') AND drp_indicator <> 'Y'"
shares, COHORT_ROWS = {}, []
for r, (name, fp) in zip(rows, COHORTS.items()):
    last = r.iloc[-1]; gone = last[list(TYPES)].sum(); hired = last.hired_so_far; shares[name] = gone / hired
    codes = dict(db.sql(f"""SELECT separation_category || ' (' || separation_category_code || ')', sum(count)::INT FROM '{SEP}'
        WHERE {fp} AND {PERM_LBL} AND {OTHER_CODES} AND event_ym >= '{ym[0]}' AND {HIRE_YM} >= '{ym[0]}' GROUP BY 1 ORDER BY 1""").fetchall())
    b(f"**{name}**: {gone:,.0f} of {hired:,.0f} hired since {month(ym[0])} with no prior federal civilian or military service had left by "
      f"{month(ym[-1])} ({gone / hired:.1%}). Quit: {last['Quit']:,.0f}. Other: {', '.join(f'{k} {v:,}' for k, v in codes.items())}.")
    tm = db.sql(f"""SELECT separation_category_code c, sum(count)::INT n, quantile_cont({LOS} * 12, 0.25) q1, median({LOS} * 12) md,
        quantile_cont({LOS} * 12, 0.75) q3 FROM '{SEP}' WHERE {fp} AND {PERM_LBL} AND event_ym >= '{ym[0]}' AND {HIRE_YM} >= '{ym[0]}'
        AND separation_category_code IN ('SC', 'SJ') AND drp_indicator <> 'Y' GROUP BY 1 ORDER BY 1""").df().set_index("c")
    COHORT_ROWS.append({"cohort": name, "hired": int(hired), "left": int(gone), "share left": round(gone / hired, 3), "quits": int(last["Quit"]),
                        "terminations": int(tm.loc["SJ", "n"]) if "SJ" in tm.index else 0,
                        "median months to quit": round(tm.loc["SC", "md"], 1) if "SC" in tm.index else None,
                        "median months to termination": round(tm.loc["SJ", "md"], 1) if "SJ" in tm.index else None})
    b(f"{name}, months from hire to departure (median, middle half): " + "; ".join(
        f"{lbl} {tm.loc[c, 'md']:.0f} ({tm.loc[c, 'q1']:.0f}-{tm.loc[c, 'q3']:.0f}; {tm.loc[c, 'n']:,})" for c, lbl in (("SC", "quits"), ("SJ", "terminations")) if c in tm.index)
      + ". Months of service at departure, from the leave service date to the middle of the departure month, so within a month or so.")
table("ice_vs_border_patrol", pd.DataFrame(COHORT_ROWS).set_index("cohort"))
ice_name, bp_name = list(COHORTS)
b(f"ICE's share is {shares[ice_name] / shares[bp_name]:.1f} times Border Patrol's.")

h("The rookie screen: did new hires wash out anywhere else?")
b(f"Method: every agency component with at least {MIN_HIRES} new hires (no prior federal civilian or military service) in {AUT} of "
  f"each of {', '.join(map(str, SCREEN_YEARS))}. Share of each autumn's hires who left by the next {pd.Timestamp(f'2000-{LAST_M}-01'):%B}, "
  f"{LATEST} compared with the higher of the earlier years. Component level, so ICE here includes non-officer hires.")
b(f"{len(screen)} components passed the size bar; they made {screen[f'hires_{LATEST}'].sum():,.0f} of the {all_latest_hires:,.0f} such "
  f"hires in {AUT} {LATEST} ({screen[f'hires_{LATEST}'].sum() / all_latest_hires:.0%}).")
table("rookie_screen_coverage", pd.Series({"components that passed the size bar": len(screen), f"their new hires, {AUT} {LATEST}": int(screen[f"hires_{LATEST}"].sum()),
      f"all new hires with no prior federal service, {AUT} {LATEST}": int(all_latest_hires),
      "share": round(screen[f"hires_{LATEST}"].sum() / all_latest_hires, 3)}).rename("value").to_frame())
for t in SCREEN_RISES:
    b(f"Components where the share leaving rose by {t}+ points: {(screen.rise >= t).sum()} of {len(screen)}.")
b(f"Median change: {screen.rise.median():+.1f} points.")
b("Largest rises:")
for u, r in screen.head(8).iterrows():
    F.append(f"  - {r.component} ({u}): " + ", ".join(f"{r[f'pct_left_{y}']:.1f}% of {r[f'hires_{y}']:,.0f} ({y})" for y in SCREEN_YEARS)
             + f"; {r.rise:+.1f} points")
if "HSBB" in screen.index:
    b(f"ICE ranks {list(screen.index).index('HSBB') + 1} of {len(screen)} by rise.")

h(f"2. How each example lost people in {SHOCK}")
hires_ex = db.sql(f"""SELECT agency_code || ' ' || occupational_series_code k, sum(n) n FROM '{DATA}/acc.parquet'
    WHERE appt IN {PERM} AND cat IN ('AC', 'AD', 'AE') AND eff BETWEEN '{INAUG}' AND '{EX_TO}' GROUP BY 1""").df().set_index("k").n
sjsl = db.sql(f"""SELECT agency_code || ' ' || occupational_series_code k, cat, sum(n) n FROM sep WHERE cat IN ('SJ', 'SL') AND drp <> 'Y'
    AND eff BETWEEN '{INAUG}' AND '{EX_TO}' GROUP BY ALL""").df().pivot(index="k", columns="cat", values="n").fillna(0)
for k, name in EXAMPLES.items():
    parts_ = ", ".join(f"{t.lower()} {share.loc[k, t]:.1f}% ({d2.loc[k, t]:,.0f})" for t in TYPES if d2.loc[k, t] > 0)
    nh = hires_ex.get(k, 0)
    b(f"**{name}** ({staff25[k]:,.0f} staff in {JAN}): {d2.loc[k].sum():,.0f} left ({share.loc[k].sum():.1f}%): {parts_}. "
      f"Other = termination (SJ) {sjsl.loc[k, 'SJ']:,.0f}, other separation (SL) {sjsl.loc[k, 'SL']:,.0f}. "
      f"New hires: {nh:,.0f} ({nh / staff25[k] * 100:.1f}% of {JAN} staff).")
table("2025_how_people_left", d2.assign(**{"all departures": d2.sum(axis=1), f"{JAN} staff": staff25, "new hires since": hires_ex.reindex(d2.index).fillna(0)})
      .astype(int).assign(**{"share left": (d2.sum(axis=1) / staff25).round(3), "new hires as share of staff": (hires_ex.reindex(d2.index).fillna(0) / staff25).round(3)})
      .set_axis([EXAMPLES[k] for k in d2.index]).rename_axis(f"{SHOCK} (new hires: {SHOCK} too)"))
ex_all = db.sql(f"""SELECT agency_code || ' ' || occupational_series_code k, sum(n) n FROM sep WHERE cat NOT IN {TRANSFERS}
    AND eff BETWEEN '{INAUG}' AND '{PARTIAL_TO}' GROUP BY 1""").df().set_index("k").n.reindex(list(EXAMPLES)).fillna(0)
hires_all = db.sql(f"""SELECT agency_code || ' ' || occupational_series_code k, sum(n) n FROM '{DATA}/acc.parquet' WHERE appt IN {PERM}
    AND cat IN ('AC', 'AD', 'AE') AND eff BETWEEN '{INAUG}' AND '{PARTIAL_TO}' GROUP BY 1""").df().set_index("k").n.reindex(list(EXAMPLES)).fillna(0)
table("hiring_examples_since_inauguration", pd.DataFrame({"departures": ex_all, "new hires": hires_all, f"{JAN} staff": staff25}).astype(int)
      .set_axis([EXAMPLES[k] for k in EXAMPLES]).rename_axis(f"{JAN} to {month(PARTIAL_TO)}"))
b(f"The same examples, {JAN} to {month(PARTIAL_TO)}: " + "; ".join(f"{EXAMPLES[k]} {ex_all[k]:,.0f} left, {hires_all[k]:,.0f} hired" for k in EXAMPLES) + ".")

h("3. Who left each year")
base = full[list(range(YEARS[0], SHOCK))].sum()
b("Departures per year: " + "; ".join(f"{y}{'*' if y == YEARS[-1] else ''} {v:,.0f}" for y, v in full.sum().items()))
b(f"{SHOCK}: {full[SHOCK].sum():,.0f}, {full[SHOCK].sum() / base.mean():.1f} times the {BASE} average ({base.mean():,.0f}) and "
  f"{full[SHOCK].sum() / base.max():.1f} times the highest year before it ({base.idxmax()}, {base.max():,.0f}).")
for band in BANDS.values():
    bb = full.loc[band, list(range(YEARS[0], SHOCK))]
    b(f"{band}: {SHOCK} {full.loc[band, SHOCK]:,.0f} vs {BASE} average {bb.mean():,.0f}; {YEARS[-1]}* {full.loc[band, YEARS[-1]]:,.0f}.")
b(f"*{YEARS[-1]} covers {MONTH_SPAN} only.")
no_los = dict(db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) FROM sep WHERE cat NOT IN {TRANSFERS} AND los = 'NA'
    AND substr(eff, 1, 4)::INT BETWEEN {YEARS[0]} AND {YEARS[-1]} AND eff <= '{PARTIAL_TO}' GROUP BY 1 ORDER BY 1""").fetchall())
b(f"Left out of these counts and of charts 3 and 4: departures with no length of service reported, or {MAX_LOS}+ years (a placeholder start date), {sum(no_los.values()):,.0f} in all ("
  + ", ".join(f"{y} {v:,.0f}" for y, v in no_los.items()) + f"). With them, {SHOCK} has {full[SHOCK].sum() + no_los.get(SHOCK, 0):,.0f} departures.")

h(f"4. Pace of leaving, per month {RATE} January staff, {MONTH_SPAN} of every year (as reported; the newest months are still filling in)")
b("Denominators, permanent staff each January with years of service reported: " + "; ".join(f"{y} {v:,.0f}" for y, v in jan.sum().items()) + ".")
for row in pace.index:
    bl = pace.loc[row, list(range(YEARS[0], SHOCK))]
    rank = int((bl >= pace.loc[row, YEARS[-1]]).sum()) + 1
    b(f"{row}: {YEARS[-1]}* {pace.loc[row, YEARS[-1]]:.2f}; {BASE} range {bl.min():.2f} ({bl.idxmin()}) to {bl.max():.2f} ({bl.idxmax()}); "
      f"{YEARS[-1]} would rank {rank} of {len(bl) + 1} among {BASE} plus {YEARS[-1]}"
      + (f" (higher: {', '.join(f'{y} {v:.2f}' for y, v in bl[bl >= pace.loc[row, YEARS[-1]]].sort_index().items())})" if rank > 1 else "")
      + f"; {SHOCK} was {pace.loc[row, SHOCK]:.2f}.")
_, lo_t, hi_t = LAG_FACTOR["total"]
bl = pace.loc["All permanent staff", list(range(YEARS[0], SHOCK))]
adj = [pace.loc["All permanent staff", YEARS[-1]] * f_ for f_ in (lo_t, hi_t)]
b(f"Adjusted for late records (Reporting lag section), all permanent staff, {YEARS[-1]}*: {adj[0]:.2f}-{adj[1]:.2f}, which would rank "
  f"{int((bl >= adj[1]).sum()) + 1}-{int((bl >= adj[0]).sum()) + 1} of {len(bl) + 1}.")
for band in BANDS.values():
    bl_ = pace.loc[band, list(range(YEARS[0], SHOCK))]
    a_ = [pace.loc[band, YEARS[-1]] * f_ for f_ in (lo_t, hi_t)]
    b(f"{band}, with the all-departures late-records factor (an approximation: late records aren't estimated by years of service): {YEARS[-1]}* "
      f"{a_[0]:.2f}-{a_[1]:.2f}, would rank {int((bl_ >= a_[1]).sum()) + 1}-{int((bl_ >= a_[0]).sum()) + 1} of {len(bl_) + 1}.")
u5 = jan.loc[BANDS["a"]] / jan.sum() * 100
b(f"Staff with {BANDS['a'].lower()} of service: {u5[SHOCK]:.1f}% of permanent staff in {JAN}, {u5[YEARS[-1]]:.1f}% in January {YEARS[-1]}.")

h("Reporting lag: records still arriving for recent months")
COMPLETE_TO = ym_of(mi(PARTIAL_TO) - LAG_H)    # the newest month with LAG_H months of follow-up
on_time = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) FILTER (WHERE {LAG_SQL} <= 0) / sum(n) s FROM sep WHERE {KIND['total']}
    AND {LAG_SQL} <= {LAG_H} AND eff BETWEEN '{YEARS[0]}01' AND '{COMPLETE_TO}' GROUP BY 1 ORDER BY 1""").df().set_index("yr").s
b(f"Share of a month's departures (of those reported within {LAG_H} months) that were in that month's own file, by year: "
  + "; ".join(f"{y} {v:.0%}" for y, v in on_time.items()) + f" ({on_time.index[-1]} through {month(COMPLETE_TO)}).")
on_time_m = db.sql(f"""SELECT eff, sum(n) FILTER (WHERE {LAG_SQL} <= 0) / sum(n) s FROM sep WHERE {KIND['total']} AND {LAG_SQL} <= {LAG_H}
    AND eff BETWEEN '{ym_of(mi(COMPLETE_TO) - 11)}' AND '{COMPLETE_TO}' GROUP BY 1 ORDER BY 1""").df().set_index("eff").s
b("By month, the latest months with that much follow-up: " + "; ".join(f"{month(e)} {v:.0%}" for e, v in on_time_m.items()))
table("2026_reporting_lag", pd.concat([on_time.rename(lambda y: str(y)), on_time_m.rename(month)]).round(3).rename("share of departures in their own month's file").rename_axis("year or month").to_frame())
for k in LAG_TABLES:
    a_ = ARRIVED[k]
    b(f"Arrival pattern for {LAG_TXT[k]} ({month(LAG_MONTHS[0])} to {month(LAG_MONTHS[-1])}; median, lowest-highest): " + "; ".join(
        f"by {L} month{'s' if L != 1 else ''} late {a_.loc[L].median():.0%} ({a_.loc[L].min():.0%}-{a_.loc[L].max():.0%})" for L in range(LAG_H)))
staff_y = db.sql("SELECT substr(snap, 1, 4)::INT yr, sum(n) n FROM emp WHERE snap LIKE '%01' GROUP BY 1").df().set_index("yr").n
LAG_ROWS = []
for k in LAG_TABLES:
    t, w = LAG_TABLES[k]
    base_n = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) n FROM {t} WHERE ({w}) AND {LAG_SQL} <= {LAG_H} AND substr(eff, 5, 2) <= '{LAST_M}'
        AND substr(eff, 1, 4)::INT BETWEEN {BASE_YEARS[0]} AND {BASE_YEARS[-1]} GROUP BY 1""").df().set_index("yr").n
    bp = (base_n / staff_y[base_n.index]).mean() * PER / int(LAST_M)
    obs, est, lo, hi = LAG[k]
    p_ = lambda v: v / staff_y[YEARS[-1]] * PER / int(LAST_M)
    LAG_ROWS.append({"measure": LAG_TXT[k], "reported so far": round(obs), "estimate with late records": round(est), "low": round(lo), "high": round(hi),
                     "times normal (estimate)": round(p_(est) / bp, 2), "times normal (low)": round(p_(lo) / bp, 2), "times normal (high)": round(p_(hi) / bp, 2),
                     "times normal (as reported)": round(p_(obs) / bp, 2)})
    b(f"{LAG_TXT[k].capitalize()}, {MONTH_SPAN} {YEARS[-1]}: {obs:,.0f} reported so far; with late reports an estimated {est:,.0f} ({lo:,.0f}-{hi:,.0f}). "
      f"{RATE.capitalize()} January staff per month: {p_(est):.2f} ({p_(lo):.2f}-{p_(hi):.2f}) vs a {BASE} average of {bp:.2f}, "
      f"{p_(est) / bp:.2f} times normal ({p_(lo) / bp:.2f}-{p_(hi) / bp:.2f}); as reported so far, {p_(obs) / bp:.2f}.")
table(f"{YEARS[-1]}_vs_normal_with_late_records", pd.DataFrame(LAG_ROWS).set_index("measure"))
for k in LAG_TABLES:   # the check: leave the newest months out, every year cut the same way (files through LAST_M)
    t, w = LAG_TABLES[k]
    r_ = []
    for c in CUSHIONS:
        end = f"{int(LAST_M) - c:02d}"
        d = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) n FROM {t} WHERE ({w}) AND substr(eff, 5, 2) <= '{end}'
            AND file <= substr(eff, 1, 4) || '{LAST_M}' AND substr(eff, 1, 4)::INT >= {YEARS[0]} GROUP BY 1""").df().set_index("yr").n
        pc = d / staff_y[d.index]
        r_.append(f"January-{pd.Timestamp(f'2000-{end}-01'):%B} {pc[YEARS[-1]] / pc[BASE_YEARS].mean():.2f}")
    b(f"Check, {LAG_TXT[k]} {RATE} staff against the {BASE} average with the newest months left out: " + "; ".join(r_) + ".")
b(f"The estimate assumes the newest months arrive like {month(LAG_MONTHS[0])}-{month(LAG_MONTHS[-1])} did, and counts a month as complete "
  f"after {LAG_H} months (later records are left out in every year). Figures elsewhere in this file are as reported unless they say otherwise; "
  f"for the newest months they are low.")

h("Government-wide scale")
staff_now = db.sql(f"SELECT sum(n) FROM hc WHERE snap = '{PARTIAL_TO}'").fetchone()[0]
staff_then = db.sql(f"SELECT sum(n) FROM emp WHERE snap = '{INAUG}'").fetchone()[0]
b(f"Permanent staff: {staff_then:,.0f} in {JAN}, {staff_now:,.0f} in {month(PARTIAL_TO)} ({staff_now - staff_then:+,.0f}, {(staff_now / staff_then - 1) * 100:+.1f}%).")
gw = dict(db.sql(f"""SELECT {type_case('drp', 'cat')} t, sum(n) FROM sep WHERE cat NOT IN {TRANSFERS} AND eff BETWEEN '{INAUG}' AND '{PARTIAL_TO}' GROUP BY 1""").fetchall())
b(f"Departures, {JAN} to {month(PARTIAL_TO)}: {sum(gw.values()):,.0f}: " + "; ".join(f"{t.lower()} {gw.get(t, 0):,.0f}" for t in TYPES) + ".")
hired_gw = db.sql(f"SELECT sum(n) FROM '{DATA}/acc.parquet' WHERE appt IN {PERM} AND cat IN ('AC', 'AD', 'AE') AND eff BETWEEN '{INAUG}' AND '{PARTIAL_TO}'").fetchone()[0]
b(f"New hires in the same period: {hired_gw:,.0f}.")
b(f"Separations coded as layoffs (reduction in force) were {gw.get('Layoff (RIF)', 0) / sum(gw.values()):.1%} of those departures; DRP was "
  f"{gw.get('Deferred resignation (DRP)', 0) / sum(gw.values()):.0%}.")
table("2025_since_inauguration", pd.Series({**{f"departures: {t}": gw.get(t, 0) for t in TYPES}, "departures: all": sum(gw.values()), "new hires": hired_gw,
      f"permanent staff, {JAN}": staff_then, f"permanent staff, {month(PARTIAL_TO)}": staff_now}).astype(int).rename(f"{JAN} to {month(PARTIAL_TO)}").to_frame())
dep_types = db.sql(f"""SELECT substr(eff, 1, 4)::INT AS "year", {type_case('drp', 'cat')} t, sum(n) n FROM sep WHERE cat NOT IN {TRANSFERS}
    AND substr(eff, 1, 4)::INT BETWEEN {YEARS[0]} AND {LAST_FULL} GROUP BY ALL""").df().pivot(index="year", columns="t", values="n").reindex(columns=list(TYPES)).fillna(0)
table("2025_departures_by_type", dep_types.assign(total=dep_types.sum(axis=1)).astype(int))
dt = dep_types.loc[SHOCK]
b(f"{SHOCK} alone: departures {dt.sum():,.0f}; " + "; ".join(f"{t.lower()} {dt[t]:,.0f} ({dt[t] / dt.sum():.1%})" for t in TYPES) + ".")
fy = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) n FROM '{DATA}/acc.parquet' WHERE appt IN {PERM} AND cat IN ('AC', 'AD', 'AE')
    AND substr(eff, 1, 4)::INT BETWEEN {YEARS[0]} AND {LAST_FULL} GROUP BY 1 ORDER BY 1""").df().set_index("yr").n
table("2025_hires_and_staff", pd.DataFrame({"new hires (whole year)": fy, "permanent staff in January": staff_y}).rename_axis("year").fillna(0).astype(int))
b("New hires, permanent appointments, whole years: " + "; ".join(f"{y} {v:,.0f}" for y, v in fy.items())
  + f". {SHOCK}: {fy[SHOCK] / fy[BASE_YEARS].mean():.0%} of the {BASE} average ({fy[BASE_YEARS].mean():,.0f}).")

h(f"Hiring compared with normal ({MONTH_SPAN})")
hy = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) n FROM '{DATA}/acc.parquet' WHERE appt IN {PERM} AND cat IN ('AC', 'AD', 'AE')
    AND {WINDOW} GROUP BY 1 ORDER BY 1""").df().set_index("yr").n
b("New hires, permanent appointments: " + "; ".join(f"{y} {v:,.0f}" for y, v in hy.items()))
b(f"{YEARS[-1]}: {hy[YEARS[-1]]:,.0f}, {(hy[YEARS[-1]] / hy[BASE_YEARS].mean() - 1) * 100:+.0f}% vs the {BASE} average ({hy[BASE_YEARS].mean():,.0f}); "
  f"lowest year before it: {hy[BASE_YEARS].idxmin()} ({hy[BASE_YEARS].min():,.0f}).")
xf = db.sql(f"SELECT substr(eff, 1, 4)::INT yr, sum(n) n FROM sep WHERE cat IN {TRANSFERS} AND {WINDOW} GROUP BY 1 ORDER BY 1").df().set_index("yr").n
hm = db.sql(f"""SELECT eff, sum(n) n FROM '{DATA}/acc.parquet' WHERE appt IN {PERM} AND cat IN ('AC', 'AD', 'AE') AND eff BETWEEN '{YEARS[-1]}01' AND '{PARTIAL_TO}'
    GROUP BY 1 ORDER BY 1""").df().set_index("eff").n
b(f"New hires by month, {YEARS[-1]} (as reported; the newest months are still filling in): " + "; ".join(f"{month(e)} {v:,.0f}" for e, v in hm.items()))
table("hiring_by_month", hm.rename(month).astype(int).rename("permanent new hires (as reported)").rename_axis("month").to_frame())
table("hiring_by_year", pd.DataFrame({"permanent new hires": hy, "transfers to another agency": xf}).rename_axis("year (January-August)").fillna(0).astype(int))
b("Transfers to another agency (a different federal job), same months: " + "; ".join(f"{y} {v:,.0f}" for y, v in xf.items())
  + f". {YEARS[-1]}*: {xf[YEARS[-1]] / xf[BASE_YEARS].mean() - 1:+.0%} vs the {BASE} average ({xf[BASE_YEARS].mean():,.0f}).")

h(f"Where hiring is happening ({MONTH_SPAN}; new hires, permanent appointments; each against its own {BASE} average for the same months)")
agname = dict(db.sql(f"SELECT agency_code, agency FROM '{DATA}/agency_names.parquet'").fetchall())
sname = dict(db.sql("SELECT occupational_series_code, any_value(series) FROM emp GROUP BY 1").fetchall())
ha = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) n, sum(n) FILTER (WHERE appt IN {PERM}) perm FROM '{DATA}/acc.parquet'
    WHERE cat IN ('AC', 'AD', 'AE') AND {WINDOW} GROUP BY 1 ORDER BY 1""").df().set_index("yr")
b(f"All appointments, temporary and term included: {YEARS[-1]}* {ha.n[YEARS[-1]]:,.0f} new hires vs a {BASE} average of {ha.n[BASE_YEARS].mean():,.0f} "
  f"({(ha.n[YEARS[-1]] / ha.n[BASE_YEARS].mean() - 1) * 100:+.0f}%); permanent share {ha.perm[YEARS[-1]] / ha.n[YEARS[-1]]:.0%} vs "
  f"{ha.perm[BASE_YEARS].sum() / ha.n[BASE_YEARS].sum():.0%}. Non-permanent (temporary and term) new hires: {YEARS[-1]}* {ha.n[YEARS[-1]] - ha.perm[YEARS[-1]]:,.0f} vs "
  f"{(ha.n - ha.perm)[BASE_YEARS].mean():,.0f} ({((ha.n - ha.perm)[YEARS[-1]] / (ha.n - ha.perm)[BASE_YEARS].mean() - 1) * 100:+.0f}%).")
table("hiring_all_appointments", pd.DataFrame({"all new hires": ha.n, "permanent": ha.perm, "temporary and term": ha.n - ha.perm}).astype(int).rename_axis("year (January-August)"))
for key, names, txt in (("agency_code", agname, "Agencies"),):   # temporary and term: where they're down
    nk = db.sql(f"""SELECT {key} k, substr(eff, 1, 4)::INT yr, sum(n) n FROM '{DATA}/acc.parquet' WHERE appt NOT IN {PERM}
        AND cat IN ('AC', 'AD', 'AE') AND {WINDOW} GROUP BY ALL""").df().pivot(index="k", columns="yr", values="n").reindex(columns=YEARS).fillna(0)
    gap = (nk[YEARS[-1]] - nk[BASE_YEARS].mean(axis=1)).sort_values()
    b(f"Non-permanent (temporary and term) new hires, {txt.lower()} with the biggest shortfalls, {YEARS[-1]}* vs {BASE}: " + "; ".join(
        f"{names.get(k, k).title()} ({k}) {nk.loc[k, YEARS[-1]]:,.0f} vs {nk.loc[k, BASE_YEARS].mean():,.0f}" for k in gap.index[:6])
      + f". Those six: {-gap.head(6).sum():,.0f} of the {-gap[gap < 0].sum():,.0f} fewer among {txt.lower()} below their average.")
    table(f"hiring_temp_by_{'agency' if key == 'agency_code' else 'occupation'}", pd.DataFrame({"name": [names.get(k, k).title() for k in gap.index],
          f"{YEARS[-1]}* hires": nk.loc[gap.index, YEARS[-1]].astype(int), f"{BASE} average": nk.loc[gap.index, BASE_YEARS].mean(axis=1).round().astype(int),
          "difference": gap.round().astype(int)}).head(15).rename_axis("code"))
for key, names, txt in (("agency_code", agname, "Agencies"), ("occupational_series_code", sname, "Occupations")):
    hk = db.sql(f"""SELECT {key} k, substr(eff, 1, 4)::INT yr, sum(n) n FROM '{DATA}/acc.parquet' WHERE appt IN {PERM}
        AND cat IN ('AC', 'AD', 'AE') AND {WINDOW} GROUP BY ALL""").df().pivot(index="k", columns="yr", values="n").reindex(columns=YEARS).fillna(0)
    avg, now = hk[BASE_YEARS].mean(axis=1), hk[YEARS[-1]]
    big = avg[avg >= MIN_AGENCY_HIRES].index
    pct = now[big] / avg[big]
    lab = lambda k: f"{names.get(k, k).title()} ({k})"
    table(f"hiring_by_{'agency' if key == 'agency_code' else 'occupation'}", pd.DataFrame({
        "name": [names.get(k, k).title() for k in big], f"{YEARS[-1]}* hires": now[big].astype(int).values,
        f"{BASE} average": avg[big].round().astype(int).values, "share of average": pct.round(2).values}, index=pd.Index(big, name="code")).sort_values(f"{YEARS[-1]}* hires", ascending=False))
    b(f"{txt} averaging {MIN_AGENCY_HIRES:,}+ hires in these months: {len(big)}, with {now[big].sum() / now.sum():.0%} of {YEARS[-1]}* hires. "
      f"At or above their average: {(pct >= 1).sum()}; under half of it: {(pct < 0.5).sum()}.")
    b(f"{txt}, most {YEARS[-1]}* hires: " + "; ".join(f"{lab(k)} {now[k]:,.0f} ({now[k] / now.sum():.0%} of all; average {avg[k]:,.0f})"
                                                    for k in now.sort_values(ascending=False).index[:TOP]))
    b(f"{txt}, furthest above their average: " + "; ".join(f"{lab(k)} {now[k]:,.0f} vs {avg[k]:,.0f} ({pct[k]:.0%})"
                                                         for k in pct.sort_values(ascending=False).index[:TOP]))
    b(f"{txt}, furthest below: " + "; ".join(f"{lab(k)} {now[k]:,.0f} vs {avg[k]:,.0f} ({pct[k]:.0%})" for k in pct.sort_values().index[:TOP]))
    if key == "agency_code":
        ag_up = pct.sort_values(ascending=False).index[:3]
    short = (avg - now).sort_values(ascending=False)
    b(f"{txt}, biggest shortfalls in number of hires: " + "; ".join(f"{lab(k)} {v:,.0f} fewer" for k, v in short.head(TOP).items())
      + f". Those {TOP} account for {short.head(TOP).sum() / short[short > 0].sum():.0%} of the {short[short > 0].sum():,.0f} fewer hires among "
      f"{txt.lower()} below their average ({(short < 0).sum()} others are above theirs by {-short[short < 0].sum():,.0f}; net {short.sum():,.0f} fewer).")

ao = db.sql(f"""SELECT agency_code a, occupational_series_code k, substr(eff, 1, 4)::INT yr, sum(n) n FROM '{DATA}/acc.parquet' WHERE appt IN {PERM}
    AND cat IN ('AC', 'AD', 'AE') AND {WINDOW} AND agency_code IN {tuple(ag_up)} GROUP BY ALL""").df()
dja = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) FILTER (WHERE appt IN {PERM}) perm, sum(n) FILTER (WHERE appt NOT IN {PERM}) other
    FROM '{DATA}/acc.parquet' WHERE agency_code = 'DJ' AND {ATT} AND cat IN ('AC', 'AD', 'AE') AND {WINDOW} GROUP BY 1 ORDER BY 1""").df().set_index("yr")
b(f"DOJ attorneys ({ATT_CODE}), new hires by appointment, {MONTH_SPAN}, permanent / other: " + "; ".join(f"{y} {r.perm:,.0f} / {r.other:,.0f}" for y, r in dja.iterrows())
  + f". All appointments, {YEARS[-1]}*: {dja.loc[YEARS[-1]].sum():,.0f} vs a {BASE} average of {dja.loc[BASE_YEARS].sum(axis=1).mean():,.0f}. "
  "DOJ began hiring attorneys into permanent appointments, so its permanent-only attorney hiring overstates the rise.")
HIRING_BACK = "NN"   # NASA: the post's hiring-back example (the recovery check in Data notes finds it)
for a in ag_up:   # what the agencies furthest above their average are hiring for
    t = ao[ao.a == a].pivot(index="k", columns="yr", values="n").reindex(columns=YEARS).fillna(0)
    extra = (t[YEARS[-1]] - t[BASE_YEARS].mean(axis=1)).sort_values(ascending=False)
    b(f"{agname.get(a, a).title()} ({a}): {YEARS[-1]}* hires {t[YEARS[-1]].sum():,.0f} vs an average of {t[BASE_YEARS].mean(axis=1).sum():,.0f}; "
      f"the occupations with the most extra hires: " + "; ".join(f"{k} {sname.get(k, '').title()} {t.loc[k, YEARS[-1]]:,.0f} vs {t.loc[k, BASE_YEARS].mean():,.0f}"
                                                              for k in extra.index[:3])
      + f" ({extra.head(3).sum() / extra[extra > 0].sum():.0%} of the extra hires in occupations above their average).")
    hs_ = db.sql(f"SELECT snap, sum(n) n FROM hc WHERE agency_code = '{a}' AND snap >= '{INAUG}' GROUP BY 1 ORDER BY 1").df().set_index("snap").n
    d12 = ym_of(mi(PARTIAL_TO) - 11)
    dd = db.sql(f"""SELECT sum(n), sum(n) FILTER (WHERE drp = 'Y') FROM sep WHERE agency_code = '{a}' AND cat NOT IN {TRANSFERS}
        AND eff BETWEEN '{d12}' AND '{PARTIAL_TO}'""").fetchone()
    b(f"{agname.get(a, a).title()} ({a}) permanent staff: {hs_.iloc[0]:,.0f} in {month(hs_.index[0])}, lowest {hs_.min():,.0f} ({month(hs_.idxmin())}), "
      f"{hs_.iloc[-1]:,.0f} in {month(hs_.index[-1])}. Departures {month(d12)} to {month(PARTIAL_TO)}: {dd[0]:,.0f}, of them DRP {dd[1] or 0:,.0f}.")
    dm = db.sql(f"""SELECT eff, sum(n) n FROM sep WHERE agency_code = '{a}' AND drp = 'Y' AND cat NOT IN {TRANSFERS} AND eff BETWEEN '{d12}' AND '{PARTIAL_TO}'
        GROUP BY 1 ORDER BY 1""").df().set_index("eff").n
    if dm.sum():
        top_m = dm[dm >= dm.sum() * 0.05]
        b(f"{agname.get(a, a).title()} ({a}) DRP exits by effective month: " + "; ".join(f"{month(e)} {v:,.0f}" for e, v in top_m.items())
          + f"; all other months {dm.sum() - top_m.sum():,.0f}. For comparison, staff fell by {hs_.iloc[0] - hs_.min():,.0f} from {month(hs_.index[0])} to the low; "
          f"DRP exits equal {dd[1] / (hs_.iloc[0] - hs_.min()):.0%} of that (hires and other departures moved the count too).")
    if a != HIRING_BACK:
        continue
    jan_ = db.sql(f"SELECT snap, sum(n) n FROM emp WHERE agency_code = '{a}' AND snap >= '{INAUG}' AND snap LIKE '%01' GROUP BY 1").df().set_index("snap").n
    st_ = pd.concat([hs_, jan_[~jan_.index.isin(hs_.index)]]).sort_index()   # the monthly files skip Januaries
    dm_all = db.sql(f"""SELECT eff, sum(n) n FROM sep WHERE agency_code = '{a}' AND drp = 'Y' AND cat NOT IN {TRANSFERS} AND eff BETWEEN '{INAUG}' AND '{PARTIAL_TO}'
        GROUP BY 1""").df().set_index("eff").n
    b(f"{agname.get(a, a).title()} ({a}) DRP exits, {month(INAUG)} to {month(PARTIAL_TO)}: {dm_all.sum():,.0f}.")
    mo_ = months_between(INAUG, PARTIAL_TO)
    nn_t = pd.DataFrame({"permanent staff": st_.reindex(mo_), "DRP exits that month": dm_all.reindex(mo_).fillna(0).astype(int)}).set_axis([month(x) for x in mo_])
    nn_t.loc["all months"] = [None, int(dm_all.sum())]
    table(f"hiring_up_{a.lower()}_staff_by_month", nn_t.rename_axis(agname.get(a, a).title()))
    table(f"hiring_up_{a.lower()}_by_occupation", pd.DataFrame({"name": [sname.get(k, "").title() for k in extra.index], f"{YEARS[-1]}* hires": t.loc[extra.index, YEARS[-1]].astype(int),
          f"{BASE} average": t.loc[extra.index, BASE_YEARS].mean(axis=1).round().astype(int), "extra hires": extra.round().astype(int)}).head(10).rename_axis("series"))

dh = db.sql(f"""SELECT occupational_series_code k, substr(eff, 1, 4)::INT yr, sum(n) n FROM '{DATA}/acc.parquet' WHERE appt IN {PERM}
    AND cat IN ('AC', 'AD', 'AE') AND {WINDOW} AND agency_code = 'HS' GROUP BY ALL""").df().pivot(index="k", columns="yr", values="n").reindex(columns=YEARS).fillna(0)
dh_gap = (dh[YEARS[-1]] - dh[BASE_YEARS].mean(axis=1)).sort_values()
table("hiring_dhs_by_occupation", pd.DataFrame({"name": [sname.get(k, "").title() for k in dh.index], f"{YEARS[-1]}* hires": dh[YEARS[-1]].astype(int),
      f"{BASE} average": dh[BASE_YEARS].mean(axis=1).round().astype(int), "difference": dh_gap.reindex(dh.index).round().astype(int)}).sort_values("difference").rename_axis("series"))
b(f"Homeland Security (HS), occupations hiring furthest below their average, {YEARS[-1]}* vs {BASE}: " + "; ".join(
    f"{k} {sname.get(k, '').title()} {dh.loc[k, YEARS[-1]]:,.0f} vs {dh.loc[k, BASE_YEARS].mean():,.0f}" for k in dh_gap.index[:4])
  + "; furthest above: " + "; ".join(f"{k} {sname.get(k, '').title()} {dh.loc[k, YEARS[-1]]:,.0f} vs {dh.loc[k, BASE_YEARS].mean():,.0f}" for k in dh_gap.index[::-1][:3]) + ".")

# Agency occupations with MIN_STAFF+ permanent staff in January SHOCK, and their size now: for the hiring-back check (Data notes)
K = "agency_code || ' ' || occupational_series_code"
occ = db.sql(f"""SELECT {K} k, sum(n) FILTER (WHERE snap = '{INAUG}') jan25 FROM emp GROUP BY 1""").df().set_index("k").jan25
now_ = db.sql(f"SELECT {K} k, sum(n) n FROM hc WHERE snap = '{PARTIAL_TO}' GROUP BY 1").df().set_index("k").n
occ = pd.DataFrame({"jan25": occ, "now": now_}).dropna()
occ = occ[occ.jan25 >= MIN_STAFF]
occ["index"] = occ.now / occ.jan25 * 100

h(f"Quitting vs retiring ({RATE} per month, {MONTH_SPAN} of every year)")
for band in (BANDS["a"], BANDS["b"], BANDS["c"]):
    for kind in ("quit", "retire"):
        x = band_pace[kind].loc[band]
        b(f"{band}, {kind}: {YEARS[-1]}* {x[YEARS[-1]]:.2f} ({band_n[kind].loc[band, YEARS[-1]]:,.0f} people); "
          f"{x[YEARS[-1]] / x[BASE_YEARS].max():.2f}x the {YEARS[0]}-{BASE_YEARS[-1]} high ({x[BASE_YEARS].max():.2f}, {x[BASE_YEARS].idxmax()}); "
          f"against {YEARS[0]} ({x[YEARS[0]]:.2f}): {x[YEARS[-1]] / x[YEARS[0]]:.2f}x.")

h(f"Education (quits and retirements, {MONTH_SPAN}, {RATE} per month)")
EDU = ("CASE WHEN edu IN ('DOCTORATE DEGREE', 'MASTERS OR PROFESSIONAL DEGREE') THEN 'graduate degree' WHEN edu = 'BACHELORS DEGREE' THEN 'bachelor''s' "
       "WHEN edu IN ('HIGH SCHOOL OR LESS', 'SOME COLLEGE OR ASSOCIATES DEGREE') THEN 'no degree' END")
BAND_LABEL = BAND_SQL.replace("THEN 'a'", f"THEN '{BANDS['a']}'").replace("THEN 'b'", f"THEN '{BANDS['b']}'").replace("THEN 'c'", f"THEN '{BANDS['c']}'")
edu_pace, edu_staff, edu_n = window_pace(f"({BAND_LABEL}) || ', ' || ({EDU})", f"los <> 'NA' AND ({EDU}) IS NOT NULL")
for g in sorted(edu_pace["total"].index):
    q, r_, a_ = (edu_pace[k].loc[g] for k in ("quit", "retire", "total"))
    b(f"{g} ({edu_staff.loc[g, YEARS[-1]]:,.0f} staff): all departures {a_[YEARS[-1]] / a_[BASE_YEARS].max():.2f}x the old high; "
      f"quits {q[YEARS[-1]]:.2f} ({q[YEARS[-1]] / q[BASE_YEARS].max():.2f}x); retirements {r_[YEARS[-1]]:.2f} ({r_[YEARS[-1]] / r_[BASE_YEARS].max():.2f}x).")
nodata = db.sql(f"SELECT sum(n) FROM emp WHERE snap = '{YEARS[-1]}01' AND edu NOT IN ('DOCTORATE DEGREE', 'MASTERS OR PROFESSIONAL DEGREE', 'BACHELORS DEGREE', 'HIGH SCHOOL OR LESS', 'SOME COLLEGE OR ASSOCIATES DEGREE')").fetchone()[0]
b(f"Left out: {nodata or 0:,.0f} January {YEARS[-1]} staff with no education reported.")
table("2026_departures_by_service_and_education", pd.DataFrame({"January staff": edu_staff[YEARS[-1]].astype(int)} | {
      f"{k}, {YEARS[-1]}*": edu_pace[k][YEARS[-1]].round(2) for k in ("total", "quit", "retire")} | {
      f"{k}, x the {BASE} high": (edu_pace[k][YEARS[-1]] / edu_pace[k][BASE_YEARS].max(axis=1)).round(2) for k in ("total", "quit", "retire")}).rename_axis(f"group ({RATE} per month, {MONTH_SPAN})"))

# Who the mid-career graduate-degree quits are: attorneys (a JD counts as a professional degree), VA's clinicians, CDC, everyone else.
CLINICAL = ("0602", "0185", "0660", "0180", "0610", "0601", "0685")   # physicians, social workers, pharmacists, psychologists, nurses, health scientists, public health
CDC_CODE = "HE39"
EDU6 = f"{BANDS['b']}, graduate degree"
GRAD_SPLIT = (f"CASE WHEN {ATT} THEN 'Attorneys, every agency' WHEN agency_code = 'VA' AND occupational_series_code IN {CLINICAL} "
              f"THEN 'VA doctors, nurses and other clinicians' WHEN agency_subelement_code = '{CDC_CODE}' THEN 'CDC' ELSE 'Everyone else' END")
gs_pace, gs_staff, gs_n = window_pace(GRAD_SPLIT, f"({BAND_LABEL}) = '{BANDS['b']}' AND ({EDU}) = 'graduate degree'")
gq, gn = gs_pace["quit"], gs_n["quit"]
gs = pd.DataFrame({"January staff": gs_staff[YEARS[-1]].astype(int), f"quits, {YEARS[-1]}*": gn[YEARS[-1]].astype(int),
                   f"quits, {BASE} average": gn[BASE_YEARS].mean(axis=1).round(0).astype(int), f"quit rate, {YEARS[-1]}*": gq[YEARS[-1]].round(2),
                   f"x the {BASE} high": (gq[YEARS[-1]] / gq[BASE_YEARS].max(axis=1)).round(2)})
gs = gs.sort_values(f"x the {BASE} high", ascending=False)
gs["extra quits vs the usual rate"] = (gn[YEARS[-1]] - gq[BASE_YEARS].mean(axis=1) * gs_staff[YEARS[-1]] * int(LAST_M) / PER).round(0).astype(int)
b(f"{EDU6} quits, split: " + "; ".join(f"{g}: {r[f'quits, {YEARS[-1]}*']:,.0f} vs a usual {r[f'quits, {BASE} average']:,.0f}, {r[f'x the {BASE} high']:.2f}x its old high"
                                        for g, r in gs.iterrows()) + ".")
table("2026_grad_degree_quits_split", gs.rename_axis(f"{EDU6} ({RATE} per month, {MONTH_SPAN})"))

h(f"Attorneys (same months, {MONTH_SPAN}, unless noted)")
qa = att_pace["quit"]
b(f"Attorney quits: {att_n['quit'].loc['Attorneys', YEARS[-1]]:,.0f} people, {qa.loc['Attorneys', YEARS[-1]]:.2f} {RATE} per month, "
  f"{att_ratio:.2f} times their {BASE} high ({qa.loc['Attorneys', BASE_YEARS].max():.2f}, {qa.loc['Attorneys', BASE_YEARS].idxmax()}). "
  f"Everyone else: {qa.loc['Everyone else', YEARS[-1]] / qa.loc['Everyone else', BASE_YEARS].max():.2f} times their high.")
ra_ = att_pace["retire"]
b(f"Attorney retirements: {ra_.loc['Attorneys', YEARS[-1]] / ra_.loc['Attorneys', BASE_YEARS].max():.2f} times their {BASE} high.")
occ_pace, occ_staff, occ_n = window_pace("occupational_series_code")
big = occ_staff[YEARS[-1]] >= MIN_STAFF
ratio = (occ_pace["quit"][YEARS[-1]] / occ_pace["quit"][BASE_YEARS].max(axis=1))[big & (occ_n["quit"][YEARS[-1]] >= MIN_QUITS)].sort_values(ascending=False)
b(f"Among {len(ratio)} occupations (government-wide series) with {MIN_STAFF:,}+ staff and {MIN_QUITS}+ quits in {YEARS[-1]}*, attorneys rank "
  f"{list(ratio.index).index(ATT_CODE) + 1} on quits relative to their own {BASE} high. Median occupation: {ratio.median():.2f}x. Top five:")
sname = dict(db.sql("SELECT occupational_series_code, any_value(series) FROM emp GROUP BY 1").fetchall())
for code, v in ratio.head(5).items():
    F.append(f"  - {code} {sname.get(code, '').title()}: {v:.2f}x ({occ_n['quit'].loc[code, YEARS[-1]]:,.0f} quits)")
ag_pace, ag_staff, ag_n = window_pace("agency_code", ATT)
ag = pd.DataFrame({"staff": ag_staff[YEARS[-1]], "quits": ag_n["quit"][YEARS[-1]],
                   "x": ag_pace["quit"][YEARS[-1]] / ag_pace["quit"][BASE_YEARS].max(axis=1)})
ag = ag[ag.staff >= MIN_ATTORNEYS].sort_values("quits", ascending=False)
b(f"Attorney quits by agency ({MIN_ATTORNEYS}+ attorneys): " + "; ".join(f"{a} {r.quits:,.0f} ({r.x:.2f}x)" for a, r in ag.iterrows()))
table("2026_attorney_quits_by_agency", ag.assign(name=[agname.get(a, a).title() for a in ag.index]).rename(columns={"staff": f"attorneys, January {YEARS[-1]}",
      "quits": f"quits, {MONTH_SPAN} {YEARS[-1]}", "x": f"quit pace, x the {BASE} high"})[["name", f"attorneys, January {YEARS[-1]}", f"quits, {MONTH_SPAN} {YEARS[-1]}", f"quit pace, x the {BASE} high"]]
      .astype({f"attorneys, January {YEARS[-1]}": int, f"quits, {MONTH_SPAN} {YEARS[-1]}": int}).round(2).rename_axis("agency"))
table("2026_occupations_below_old_high", pd.Series({"occupations compared": len(ratio), "quitting below their 2015-2024 high": int((ratio < 1).sum()),
      "median, x the old high": round(ratio.median(), 2)}).rename("value").to_frame())
table("2026_quits_vs_own_high_by_occupation", pd.DataFrame({"name": [sname.get(c, "").title() for c in ratio.index], f"quits, {MONTH_SPAN} {YEARS[-1]}": occ_n["quit"].loc[ratio.index, YEARS[-1]].astype(int),
      f"quit pace, x the {BASE} high": ratio.round(2)}).rename_axis("series"))

# ---- 6. One heatmap of quit rates: everyone, attorneys (all agencies, then the agencies where they're quitting at 2+ times
# their old high), air traffic controllers, and mid-career staff with graduate degrees. Same months every year; actual rates,
# each row shaded against its own range.
ATT_HIGH = 2
ATC_CODE = "2152"   # air traffic control
all_q = window_pace("'All permanent staff'")[0]["quit"]
ag_hot = ag[ag.x >= ATT_HIGH].index
rows6 = [("All permanent staff", all_q.loc["All permanent staff"]), ("Attorneys, every agency", att_pace["quit"].loc["Attorneys"])] \
    + [(f"Attorneys at {agname.get(a_, a_).title().replace('Department Of ', '').replace('Environmental Protection Agency', 'EPA')}", ag_pace["quit"].loc[a_]) for a_ in ag_hot] \
    + [("Air traffic controllers", occ_pace["quit"].loc[ATC_CODE]), (f"{BANDS['b']} of service, graduate degree", edu_pace["quit"].loc[EDU6])]
heat6 = pd.DataFrame({k: v[YEARS] for k, v in rows6}).T
heat6.round(2).to_csv(OUT / "6_attorney_quits.csv")
shade6 = heat6.sub(heat6.min(axis=1), axis=0).div(heat6.max(axis=1) - heat6.min(axis=1), axis=0)
fig, ax = frame(0.5 * len(heat6) + 1.5, bottom_in=1.1, left=0.3, right=0.99)
ax.imshow(shade6.values, cmap=INTENSITY, aspect="auto", vmin=0, vmax=1)
for i in range(heat6.shape[0]):
    for k in range(heat6.shape[1]):
        v = heat6.values[i, k]
        ax.text(k, i, f"{v:.2f}" if heat6.values[i].max() < SMALL4 else f"{v:.1f}", ha="center", va="center", fontsize=10,
                color=SURFACE if shade6.values[i, k] > 0.5 else INK, fontweight=600 if k == len(YEARS) - 1 else "normal")
ax.set_xticks(range(len(YEARS)), YEAR_LABELS); ax.set_yticks(range(len(heat6)), heat6.index)
for sp in ax.spines.values():
    sp.set_visible(False)
for edge in (0.5, 1.5 + len(ag_hot)):   # gaps around the attorney block
    ax.axhline(edge, color=SURFACE, lw=5)
finish(fig, "6_attorney_quits", head6,
       f"Permanent employees who quit per month, {RATE} on staff in January",
       [f"{MONTH_SPAN.replace('-', ' through ')} of every year. Each row is shaded against its own range. DRP exits are not counted as quits.",
        f"Attorneys: occupational series {ATT_CODE} (general attorney); the agencies shown are those with {MIN_ATTORNEYS}+ attorneys whose attorneys are quitting at "
        f"{ATT_HIGH}+ times their {BASE} high. Air traffic controllers: series {ATC_CODE}, every agency. Graduate degree: master's, professional or doctorate.",
        f"Records for recent months are still arriving: once they do, {YEARS[-1]}* quits are likely {(LAG_FACTOR['quit'][1] - 1) * 100:.0f}-{(LAG_FACTOR['quit'][2] - 1) * 100:.0f}% higher."])

# ---- Retirement eligibility, former feds coming back, young hires (age_*.parquet: age bracket by whole years of service) ----
for t in ("age_sep", "age_emp", "age_acc"):
    db.execute(f"CREATE VIEW {t} AS SELECT * FROM '{DATA}/{t}.parquet' WHERE appt IN {PERM}")
db.execute(f"CREATE VIEW age_acc_all AS SELECT * FROM '{DATA}/age_acc.parquet'")
rule = lambda pairs: " OR ".join(f"(age = '{a}' AND los_y >= {y})" for a, y in pairs)
SURE, UPPER = rule(ELIGIBLE_SURE), rule(ELIGIBLE_SURE + ELIGIBLE_MAYBE)
age_txt = lambda a: a.replace(" OR MORE", "+")
rules_txt = lambda pairs: ", ".join(f"age {age_txt(a)} with {y}+ years of service" for a, y in pairs)
AGE_OK = "age IS NOT NULL AND age <> 'UNSPECIFIED'"
LOS_OK = f"los_y IS NOT NULL AND los_y < {MAX_LOS}"          # MAX_LOS+ years is a placeholder start date (config.py)
KNOWN = f"{AGE_OK} AND {LOS_OK}"
YOUNG_SQL = "age IN (" + ", ".join(f"'{a}'" for a in YOUNG) + ")"
YOUNG_TXT = f"under {int(YOUNG[-1].split('-')[1]) + 1}"
NEW_HIRE = "cat IN ('AC', 'AD', 'AE')"
BANDS_Y = [f"under {LOS_CUTS[0]}"] + [f"{a}-{c}" for a, c in zip(LOS_CUTS, LOS_CUTS[1:])] + [f"{LOS_CUTS[-1]}+"]   # extract.py's bands, from whole years
LOS_SQL_Y = "CASE " + " ".join(f"WHEN los_y < {c} THEN '{l}'" for c, l in zip(LOS_CUTS, BANDS_Y)) + f" ELSE '{BANDS_Y[-1]}' END"

h("Retirement eligibility: is the slower pace because the eligible already left?")
b(f"Eligible for an immediate retirement, from age bracket and years of service: at least {rules_txt(ELIGIBLE_SURE)}; at most, also "
  f"{rules_txt(ELIGIBLE_MAYBE)} (in those brackets only some people have reached the qualifying age; the lower years-of-service "
  "bar there includes reduced annuities). Years of service is from OPM's leave service computation date, which includes creditable military time; "
  "early retirement offers (VERA) and disability retirement aren't counted as eligibility.")
pool = db.sql(f"""SELECT substr(snap, 1, 4)::INT yr, sum(n) FILTER (WHERE {SURE}) lo, sum(n) FILTER (WHERE {UPPER}) hi,
    sum(n) FILTER (WHERE {KNOWN}) known, sum(n) staff FROM age_emp WHERE snap LIKE '%01' GROUP BY 1 ORDER BY 1""").df().set_index("yr")
table("retirement_eligible_staff", pool.rename(columns={"lo": "eligible (at least)", "hi": "eligible (at most)", "known": "staff with age and service", "staff": "all permanent staff"}).rename_axis("January of").astype(int))
b("Retirement-eligible permanent staff each January (at least to at most, and share of staff): " + "; ".join(
    f"{y} {r.lo:,.0f}-{r.hi:,.0f} ({r.lo / r.known:.1%}-{r.hi / r.known:.1%})" for y, r in pool.iterrows()))
b("Staff with no age or years of service reported, left out of the shares: " + "; ".join(f"{y} {r.staff - r.known:,.0f}" for y, r in pool.iterrows()))
chg = pool.lo.diff()
base_chg = chg.loc[BASE_YEARS[1]:SHOCK]   # January-to-January changes up to January SHOCK
b(f"Change in the eligible pool (at least) from one January to the next: January {SHOCK} to January {YEARS[-1]} {chg[YEARS[-1]]:+,.0f} "
  f"({chg[YEARS[-1]] / pool.lo[SHOCK]:+.0%}); from {BASE_YEARS[0]} to {SHOCK} the yearly change ranged from {base_chg.min():+,.0f} to {base_chg.max():+,.0f}.")

# Departure pace, same months every year (WINDOW), by eligibility. Departures are grouped by age and service when they
# left, staff by age and service in January; people who cross a line during the year count as eligible when they leave.
GROUP = f"CASE WHEN {SURE} THEN 'eligible' WHEN {UPPER} THEN 'maybe' ELSE 'not eligible' END"
dep = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, {GROUP} g, sum(n) FILTER (WHERE cat NOT IN {TRANSFERS}) total,
    sum(n) FILTER (WHERE {KIND['retire']}) retire, sum(n) FILTER (WHERE drp = 'Y') buyout
    FROM age_sep WHERE {WINDOW} AND {KNOWN} GROUP BY ALL""").df()
stf = db.sql(f"SELECT substr(snap, 1, 4)::INT yr, {GROUP} g, sum(n) staff FROM age_emp WHERE snap LIKE '%01' AND {KNOWN} GROUP BY ALL").df()
dg = dep.merge(stf, on=["yr", "g"])
GROUP_TXT = {"eligible": "eligible (at least)", "maybe": "possibly eligible", "not eligible": "not eligible"}
elig_rows = {}
for g, txt in GROUP_TXT.items():
    d_ = dg[dg.g == g].set_index("yr").sort_index()
    p = d_.total / int(LAST_M) / d_.staff * PER
    elig_rows[txt] = p.round(2)
    b(f"Departures {RATE} {txt} staff per month, {MONTH_SPAN}: {YEARS[-1]}* {p[YEARS[-1]]:.2f}; {SHOCK} {p[SHOCK]:.2f}; "
      f"{BASE} range {p[BASE_YEARS].min():.2f} ({p[BASE_YEARS].idxmin()}) to {p[BASE_YEARS].max():.2f} ({p[BASE_YEARS].idxmax()}).")
table("2026_departures_by_retirement_eligibility", pd.DataFrame(elig_rows).rename_axis(f"year ({RATE} staff per month, {MONTH_SPAN})"))

# Who the long-serving quitters are: eligibility group and age bracket when they quit.
qa = db.sql(f"""SELECT CASE WHEN substr(eff, 1, 4)::INT = {YEARS[-1]} THEN 'now' WHEN substr(eff, 1, 4)::INT < {SHOCK} THEN 'base' END p, {GROUP} g, age,
    sum(n) n FROM age_sep WHERE {WINDOW} AND {KIND['quit']} AND {KNOWN} AND los_y >= {BAND_CUTS[1]} GROUP BY ALL""").df().dropna(subset=["p"])
gq = qa.pivot_table(index="p", columns="g", values="n", aggfunc="sum").fillna(0)
gq = gq.div(gq.sum(axis=1), axis=0)
aq = qa.pivot_table(index="p", columns="age", values="n", aggfunc="sum").fillna(0)
aq = aq.div(aq.sum(axis=1), axis=0)
b(f"Quits by staff with {BANDS['c'].lower()} of service, {MONTH_SPAN} ({YEARS[-1]}* vs {BASE} pooled), by eligibility when they quit: "
  + "; ".join(f"{GROUP_TXT[g]} {gq.loc['now', g]:.0%} vs {gq.loc['base', g]:.0%}" for g in GROUP_TXT if g in gq) + ". By age: "
  + "; ".join(f"{age_txt(a)} {aq.loc['now', a]:.0%} vs {aq.loc['base', a]:.0%}" for a in aq.columns if aq.loc[:, a].max() >= 0.01) + ".")

# Standardized pace: each year's departure rate in each age bracket x years-of-service cell, weighted by one fixed
# January's mix of staff. Holding the mix at INAUG's shows how much of the partial year's pace is the smaller pool.
CELL = f"age || ' / ' || {LOS_SQL_Y}"
cd = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, {CELL} c, sum(n) FILTER (WHERE cat NOT IN {TRANSFERS}) total,
    sum(n) FILTER (WHERE {KIND['retire']}) retire FROM age_sep WHERE {WINDOW} AND {KNOWN} GROUP BY ALL""").df()
cs = db.sql(f"SELECT substr(snap, 1, 4)::INT yr, {CELL} c, sum(n) staff FROM age_emp WHERE snap LIKE '%01' AND {KNOWN} GROUP BY ALL").df()
cm = cs.merge(cd, on=["yr", "c"], how="left").fillna({"total": 0, "retire": 0})
no_staff = cd.merge(cs, on=["yr", "c"], how="left").query("staff.isna()").groupby("yr").total.sum()   # can't have a rate; left out


def std_pace(kind, yr, mix_yr):
    r_ = cm[cm.yr == yr].set_index("c")
    w_ = cm[cm.yr == mix_yr].set_index("c").staff
    return (r_[kind] / r_.staff).reindex(w_.index).fillna(0).mul(w_).sum() / w_.sum() / int(LAST_M) * PER


for kind, txt in (("total", "Departures"), ("retire", "Retirements (DRP exits not counted)")):
    own = {y: std_pace(kind, y, y) for y in YEARS}
    on25 = {y: std_pace(kind, y, SHOCK) for y in YEARS}
    base_avg = np.mean([own[y] for y in BASE_YEARS])
    b(f"{txt} {RATE} staff per month, {MONTH_SPAN}: {YEARS[-1]}* {own[YEARS[-1]]:.2f} with its own January mix, "
      f"{on25[YEARS[-1]]:.2f} with {JAN}'s mix of ages and years of service; {BASE} average {base_avg:.2f} with their own mix, "
      f"{np.mean([on25[y] for y in BASE_YEARS]):.2f} with {JAN}'s.")
    base25 = np.mean([on25[y] for y in BASE_YEARS])
    b(f"So the change in the mix since {JAN} lowers {YEARS[-1]}*'s {txt.split(' ')[0].lower()} by {on25[YEARS[-1]] - own[YEARS[-1]]:.2f} {RATE} per month. "
      f"As reported, {YEARS[-1]}* is {own[YEARS[-1]] / base_avg:.2f} times the {BASE} average; with every year on {JAN}'s mix, {on25[YEARS[-1]] / base25:.2f} times.")
    _, lo, hi = LAG_FACTOR[kind]
    b(f"With late reports, {YEARS[-1]}* {txt.split(' ')[0].lower()} are likely {own[YEARS[-1]] * lo:.2f}-{own[YEARS[-1]] * hi:.2f} with its own mix "
      f"({own[YEARS[-1]] * lo / base_avg:.2f}-{own[YEARS[-1]] * hi / base_avg:.2f} times the {BASE} average) and {on25[YEARS[-1]] * lo:.2f}-{on25[YEARS[-1]] * hi:.2f} "
      f"with {JAN}'s ({on25[YEARS[-1]] * lo / base25:.2f}-{on25[YEARS[-1]] * hi / base25:.2f} times the average on that mix).")
cells_left = db.sql(f"SELECT sum(n) FROM age_sep WHERE {WINDOW} AND NOT ({KNOWN}) AND cat NOT IN {TRANSFERS} AND substr(eff, 1, 4)::INT = {YEARS[-1]}").fetchone()[0] or 0
b(f"Cells: OPM's age brackets by years of service ({', '.join(BANDS_Y)}). Left out in {YEARS[-1]}*: {cells_left:,.0f} departures with no age or years "
  f"of service, {no_staff.get(YEARS[-1], 0):,.0f} in a cell with no January staff.")
bad = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) n, min(file) f0, max(file) f1 FROM age_sep WHERE los_y >= {MAX_LOS} GROUP BY 1 ORDER BY 1""").df()
b(f"Departures listed with {MAX_LOS}+ years of service (a placeholder start date), counted as not reported here and in every years-of-service "
  f"figure above: " + "; ".join(f"{r.yr} {r.n:,.0f}" for r in bad.itertuples()) + f" (OPM files {month(bad.f0.min())} to {month(bad.f1.max())}).")

h(f"Are former federal employees coming back? (new hires, permanent appointments, {MONTH_SPAN})")
ret = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) all_, sum(n) FILTER (WHERE fresh) fresh,
    sum(n) FILTER (WHERE NOT fresh AND {LOS_OK} AND vet = 'N') prior_civ, sum(n) FILTER (WHERE NOT fresh AND {LOS_OK} AND vet = 'Y') prior_vet,
    sum(n) FILTER (WHERE vet = 'N') nonvet,
    sum(n) FILTER (WHERE fresh IS NULL OR los_y >= {MAX_LOS}) unk FROM age_acc WHERE {NEW_HIRE} AND {WINDOW} GROUP BY 1 ORDER BY 1""").df().set_index("yr")
b(f"New hires with prior service (years of service at hire of {NEW_HIRE_LOS * 12:.0f} months or more, from the leave service date), non-veterans, "
  "for whom it is mostly earlier federal civilian work (agencies can also credit some non-federal work experience toward leave): " + "; ".join(f"{y} {r.prior_civ:,.0f} ({r.prior_civ / r.all_:.0%} of hires)" for y, r in ret.iterrows()))
b("Veterans with prior service (creditable military time counts, so most veterans have it): " + "; ".join(f"{y} {r.prior_vet:,.0f}" for y, r in ret.iterrows()))
b("No prior service: " + "; ".join(f"{y} {r.fresh:,.0f}" for y, r in ret.iterrows()) + f". No years of service reported, or {MAX_LOS}+: "
  + "; ".join(f"{y} {r.unk:,.0f}" for y, r in ret.iterrows() if r.unk)
  + f". {YEARS[-1]}*: no prior service {(ret.fresh[YEARS[-1]] / ret.fresh[BASE_YEARS].mean() - 1) * 100:+.0f}% vs the {BASE} average ({ret.fresh[BASE_YEARS].mean():,.0f}).")
drop = {lbl: ret[c][YEARS[-1]] - ret[c][BASE_YEARS].mean() for c, lbl in (("fresh", "no prior federal service, civilian or military"),
        ("prior_vet", "veterans with prior service (mostly military time)"), ("prior_civ", "non-veterans with prior service (mostly former federal civilians)"))}
tot_drop = ret.all_[YEARS[-1]] - ret.all_[BASE_YEARS].mean()
table("hiring_by_prior_service", ret[["fresh", "prior_vet", "prior_civ", "all_"]].rename(columns={"fresh": "no prior federal service", "prior_vet": "veterans with prior service",
      "prior_civ": "non-veterans with prior service", "all_": "all new hires"}).rename_axis("year (January-August)").astype(int))
b(f"Where the {YEARS[-1]}* drop in new hires comes from ({tot_drop:,.0f} vs the {BASE} average): " + "; ".join(f"{k} {v:+,.0f} ({v / tot_drop:.0%})" for k, v in drop.items())
  + f"; years of service not reported {tot_drop - sum(drop.values()):+,.0f}.")
b("Non-veterans with prior service as a share of non-veteran new hires: " + "; ".join(f"{y} {r.prior_civ / r.nonvet:.0%}" for y, r in ret.iterrows()))
pc = ret.prior_civ
b(f"{YEARS[-1]}*: {pc[YEARS[-1]]:,.0f} non-veterans with prior service, {(pc[YEARS[-1]] / pc[BASE_YEARS].mean() - 1) * 100:+.0f}% vs the {BASE} average "
  f"({pc[BASE_YEARS].mean():,.0f}); all new hires {(ret.all_[YEARS[-1]] / ret.all_[BASE_YEARS].mean() - 1) * 100:+.0f}%.")
rl = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, {LOS_SQL_Y} band, sum(n) n FROM age_acc WHERE {NEW_HIRE} AND {WINDOW} AND NOT fresh AND {LOS_OK} AND vet = 'N'
    GROUP BY ALL""").df().pivot(index="yr", columns="band", values="n").fillna(0)
rl = rl[[c for c in BANDS_Y if c in rl]]
long_ = [c for c in BANDS_Y if c in (f"{LOS_CUTS[-2]}-{LOS_CUTS[-1]}", f"{LOS_CUTS[-1]}+")]
lp = rl[long_].sum(axis=1)
b(f"Non-veterans with {LOS_CUTS[-2]}+ years of prior service: {YEARS[-1]}* {lp[YEARS[-1]]:,.0f} vs a {BASE} average of {lp[BASE_YEARS].mean():,.0f} "
  f"({lp[YEARS[-1]] / lp[BASE_YEARS].mean():.2f}x), while all new hires are {ret.all_[YEARS[-1]] / ret.all_[BASE_YEARS].mean():.2f}x their average.")
pm = db.sql(f"""SELECT eff, sum(n) FILTER (WHERE NOT fresh AND {LOS_OK}) / sum(n) s FROM age_acc WHERE {NEW_HIRE} AND vet = 'N'
    AND eff BETWEEN '{ym_of(mi(PARTIAL_TO) - 11)}' AND '{PARTIAL_TO}' GROUP BY 1 ORDER BY 1""").df().set_index("eff").s
b("Share of non-veteran new hires with prior service, by month: " + "; ".join(f"{month(e)} {v:.0%}" for e, v in pm.items())
  + f". Every year here is on one definition. OPM's own years-of-service field changed definition in early {PARTIAL_TO[:4]} (Data notes); read as reported, "
  "it makes prior service among new hires look as if it jumped.")
b("Non-veterans with prior service, by years of it: " + "; ".join(f"{y} " + ", ".join(f"{c} {r[c]:,.0f}" for c in rl.columns) for y, r in rl.iterrows()))

h(f"Young hires ({YOUNG_TXT}; new hires, {MONTH_SPAN})")
for view, txt in (("age_acc", "permanent appointments"), ("age_acc_all", "all appointments")):
    yg = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) FILTER (WHERE {YOUNG_SQL}) young, sum(n) FILTER (WHERE {AGE_OK}) n,
        sum(n) FILTER (WHERE NOT ({AGE_OK})) unspec FROM {view} WHERE {NEW_HIRE} AND {WINDOW} GROUP BY 1 ORDER BY 1""").df().set_index("yr")
    sh = yg.young / yg.n
    if view == "age_acc":
        young_t = pd.DataFrame({"young hires (under 30)": yg.young.astype(int), "hires with age reported": yg.n.astype(int), "share young": sh.round(3)}).rename_axis("year (January-August)")
    b(f"Share of new hires {YOUNG_TXT}, {txt}: " + "; ".join(f"{y} {v:.1%}" for y, v in sh.items())
      + f". {YEARS[-1]}*: {yg.young[YEARS[-1]]:,.0f} young hires vs the {BASE} average of {yg.young[BASE_YEARS].mean():,.0f}. Age not reported, left out: "
      + ("; ".join(f"{y} {v:,.0f}" for y, v in yg.unspec.items() if v > 0) or "none") + ".")
xd = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) FILTER (WHERE {YOUNG_SQL}) / sum(n) FILTER (WHERE {AGE_OK}) s FROM age_acc
    WHERE {NEW_HIRE} AND {WINDOW} AND agency_code <> 'HS' GROUP BY 1 ORDER BY 1""").df().set_index("yr").s
table("young_hires", young_t.assign(**{"share young, Homeland Security left out": xd.round(3)}))
b(f"Share of new hires {YOUNG_TXT}, permanent appointments, Homeland Security (HS) left out: " + "; ".join(f"{y} {v:.1%}" for y, v in xd.items())
  + f". {BASE} average {xd[BASE_YEARS].mean():.1%}.")
pw = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) n FROM age_acc_all WHERE {NEW_HIRE} AND {WINDOW} AND pw IS NOT NULL GROUP BY 1 ORDER BY 1""").df().set_index("yr").n
b("Pathways hires (intern, recent graduate, PMF, student trainee), all appointments: " + "; ".join(f"{y} {v:,.0f}" for y, v in pw.items()))
pw = pw.reindex(YEARS).fillna(0)
table("pathways_hires", pw.astype(int).rename("Pathways new hires, all appointment types").rename_axis("year (January-August)").to_frame())
r9 = pw[YEARS[-1]] / pw[BASE_YEARS].mean()
fig, ax = frame(4.4, bottom_in=0.75, left=0.07, right=0.98)
ax.bar(range(len(YEARS)), pw.values, color=[BAND_COLOR[BANDS["b"]]] * (len(YEARS) - 1) + [BAND_COLOR[BANDS["c"]]], width=0.7)
for k, v in enumerate(pw.values):
    ax.text(k, v + pw.max() * 0.015, f"{v:,.0f}", ha="center", fontsize=9.5, color=INK, fontweight=600 if k == len(YEARS) - 1 else "normal")
ax.set_xticks(range(len(YEARS)), YEAR_LABELS); ax.set_yticks([])
for sp in ("top", "right", "left"):
    ax.spines[sp].set_visible(False)
finish(fig, "8_pathways_hires", claim("Chart 8 title", 0.25 <= r9 <= 0.42, "Pathways hiring is down about two-thirds",
                                    f"Pathways hiring, {MONTH_SPAN.replace('-', ' through ')}, is at {r9:.0%} of its {YEARS[0]}-{SHOCK - 1} average"),
       f"New hires through Pathways (internships, Recent Graduates, Presidential Management Fellows), {MONTH_SPAN} of each year, all appointment types",
       ["Pathways: OPM's pathways_group field on the hire record.", f"*{YEARS[-1]} is {MONTH_SPAN.replace('-', ' through ')}; every year here covers the same months."], perm=False)
ys = db.sql(f"""SELECT substr(snap, 1, 4)::INT yr, sum(n) FILTER (WHERE {YOUNG_SQL}) / sum(n) FILTER (WHERE {AGE_OK}) s
    FROM age_emp WHERE snap LIKE '%01' GROUP BY 1 ORDER BY 1""").df().set_index("yr").s
b(f"Permanent staff {YOUNG_TXT}, each January: " + "; ".join(f"{y} {v:.1%}" for y, v in ys.items()))

def split(t, col):
    """Change in a share (t[col + '0'] / t.n0 -> t[col + '1'] / t.n1, by occupation) split into the occupations hired for and the share
    within them. Mix: each occupation's change in its share of hires, valued at its base rate less the base average, so growth in an
    occupation above the average raises the share. Within: each occupation's change in rate, weighted by its current share of hires,
    so a tiny current cell weighs almost nothing. The two add up exactly. An occupation hired in only one period uses that period's rate."""
    s0, s1 = t.n0 / t.n0.sum(), t.n1 / t.n1.sum()
    y0, y1 = (t[col + "0"] / t.n0).where(t.n0 > 0), (t[col + "1"] / t.n1).where(t.n1 > 0)
    y0, y1 = y0.fillna(y1), y1.fillna(y0)
    Y0 = t[col + "0"].sum() / t.n0.sum()
    mix_c, within_c = (s1 - s0) * (y0 - Y0), s1 * (y1 - y0)
    tot = t[col + "1"].sum() / t.n1.sum() - Y0
    assert abs(mix_c.sum() + within_c.sum() - tot) < 1e-9
    split.avg = ((s1 - s0) * (y0 + y1) / 2).sum()   # the mix part with average weights instead, for comparison (tiny cells move it more)
    return s0, s1, y0, y1, mix_c, within_c, tot


def split_table(name, t, s0, s1, y0, y1, mix_c, within_c, what):
    """split()'s pieces by occupation, the biggest movers first, under a first row with the totals."""
    d = pd.DataFrame({"name": [sname.get(o, "").title() for o in t.index], f"share of {BASE} hires": s0, "share of these hires": s1,
                      f"{what}, {BASE}": y0, f"{what}, now": y1, "mix part (points)": mix_c * 100, "within part (points)": within_c * 100}, index=t.index)
    d = d.loc[(mix_c.abs() + within_c.abs()).sort_values(ascending=False).index[:20]]
    tot_row = pd.DataFrame({"name": "ALL OCCUPATIONS", f"share of {BASE} hires": 1.0, "share of these hires": 1.0, f"{what}, {BASE}": t.iloc[:, 0].sum() / t.n0.sum(),
                            f"{what}, now": t.iloc[:, 2].sum() / t.n1.sum(), "mix part (points)": mix_c.sum() * 100, "within part (points)": within_c.sum() * 100}, index=["all"])
    table(name, pd.concat([tot_row, d]).round(3).rename_axis("series"))


# Is it the jobs? Split the change in the young share of permanent new hires into the mix of occupations hired for and
# the young share within each occupation (split(), above).
oc = db.sql(f"""SELECT CASE WHEN substr(eff, 1, 4)::INT < {SHOCK} THEN 'base' ELSE substr(eff, 1, 4) END p, occ,
    sum(n) FILTER (WHERE {YOUNG_SQL}) young, sum(n) n FROM age_acc WHERE {NEW_HIRE} AND {WINDOW} AND {AGE_OK} GROUP BY ALL""").df()
for p1 in (str(YEARS[-1]),):
    t = oc[oc.p == "base"].set_index("occ")[["young", "n"]].join(oc[oc.p == p1].set_index("occ")[["young", "n"]], lsuffix="0", rsuffix="1", how="outer").fillna(0)
    s0, s1, y0, y1, mix_c, within_c, tot = split(t, "young")
    split_table(f"young_hires_by_occupation_{p1}", t, s0, s1, y0, y1, mix_c, within_c, "young")
    b(f"{p1 if p1 != str(YEARS[-1]) else p1 + '*'} vs {BASE} (pooled): young share of permanent new hires {t.young0.sum() / t.n0.sum():.1%} -> "
      f"{t.young1.sum() / t.n1.sum():.1%} ({tot * 100:+.1f} points): which occupations were hired for {mix_c.sum() * 100:+.1f} ({split.avg * 100:+.1f} with average weights), "
      f"younger or older hires within the same occupations {within_c.sum() * 100:+.1f}.")
    top = mix_c.sort_values().head(5)
    b(f"Occupations pulling the {p1} young share down most through the mix: " + "; ".join(
        f"{o} {sname.get(o, '').title()} ({s0[o]:.1%} of {BASE} hires -> {s1[o]:.1%}; {y0[o]:.0%} young) {v * 100:+.2f}" for o, v in top.items()))
    top_w = within_c.sort_values().head(5)
    b("Occupations pulling it down most within the occupation: " + "; ".join(
        f"{o} {sname.get(o, '').title()} ({y0[o]:.0%} -> {y1[o]:.0%} young) {v * 100:+.2f}" for o, v in top_w.items()))

# Education of new hires (edu_acc.parquet): OPM's education bracket at hire. A degree is a rough proxy for skills, and
# the jobs being filled drive it, so the change is split the same way as the young share: which occupations are hired
# for, and more or less education within the same occupations.
EDU_LVL = ("CASE WHEN edu IN ('DOCTORATE DEGREE', 'MASTERS OR PROFESSIONAL DEGREE') THEN 'graduate degree' WHEN edu = 'BACHELORS DEGREE' THEN 'bachelor''s' "
           "WHEN edu = 'SOME COLLEGE OR ASSOCIATES DEGREE' THEN 'some college' WHEN edu = 'HIGH SCHOOL OR LESS' THEN 'high school or less' END")
db.execute(f"CREATE VIEW edu_all AS SELECT *, {EDU_LVL} lvl FROM '{DATA}/edu_acc.parquet' WHERE appt IN {PERM}")
# Agencies whose hires in degree-required series are often recorded below a bachelor's (config.py: DEGREE_SERIES, EDU_BAD).
DS_SQL = "(" + ", ".join(f"'{o}'" for o in DEGREE_SERIES) + ")"
LOW = "lvl IN ('some college', 'high school or less')"
edq = db.sql(f"""SELECT agency_code a, sum(n) n, sum(n) FILTER (WHERE {LOW}) low FROM edu_all WHERE occ IN {DS_SQL} AND lvl IS NOT NULL AND {WINDOW}
    GROUP BY 1 HAVING sum(n) >= {MIN_DEGREE_HIRES}""").df().set_index("a")
edq["s"] = edq.low / edq.n
bad_ag = lambda cut: tuple(sorted(edq.index[edq.s >= cut])) or ("none",)
BAD_EDU = f"agency_code IN {bad_ag(EDU_BAD)!r}".replace(",)", ")")
db.execute(f"CREATE VIEW edu_acc AS SELECT * FROM edu_all WHERE NOT ({BAD_EDU})")
DEGREE = "lvl IN ('graduate degree', 'bachelor''s')"
h(f"Education of new hires ({MONTH_SPAN}; new hires, permanent appointments)")
el = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, lvl, sum(n) n FROM edu_acc WHERE {WINDOW} GROUP BY ALL""").df()
known_e = el.dropna(subset=["lvl"]).pivot(index="yr", columns="lvl", values="n").fillna(0)
sh_e = known_e.div(known_e.sum(axis=1), axis=0)
deg = sh_e["graduate degree"] + sh_e["bachelor's"]
table("education_of_new_hires", sh_e.assign(**{"bachelor's or more": deg}).round(3).rename_axis("year (January-August)"))
b("Share of new hires with a bachelor's degree or more: " + "; ".join(f"{y} {v:.1%}" for y, v in deg.items())
  + f". {BASE} average {deg[BASE_YEARS].mean():.1%}.")
for lv in ("graduate degree", "bachelor's", "some college", "high school or less"):
    b(f"Share with {lv}: " + "; ".join(f"{y} {v:.1%}" for y, v in sh_e[lv].items()))
nr = el[el.lvl.isna()].set_index("yr").n.sort_index()
b("No education reported, left out of the shares: " + "; ".join(f"{y} {v:,.0f}" for y, v in nr.items()) + ".")
left_n = db.sql(f"SELECT agency_code, sum(n) FROM edu_all WHERE {BAD_EDU} AND {WINDOW} GROUP BY 1").fetchall()
all_n = db.sql(f"SELECT sum(n) FROM edu_all WHERE {WINDOW}").fetchone()[0]
b(f"Education at hire is recorded unreliably at some agencies: in series that require a degree ({', '.join(DEGREE_SERIES)}), they record many hires "
  f"below a bachelor's. Agencies at {EDU_BAD:.0%} or more ({YEARS[0]} on, {MIN_DEGREE_HIRES}+ such hires), left out of these figures in every year: "
  + "; ".join(f"{agname.get(a, a).title()} ({a}) {edq.loc[a, 's']:.0%} of {edq.loc[a, 'n']:,.0f}" for a in bad_ag(EDU_BAD))
  + f". Together {sum(v for _, v in left_n):,.0f} of {all_n:,.0f} new hires ({sum(v for _, v in left_n) / all_n:.0%}). Median agency: {edq.s.median():.0%}.")
for cut in EDU_CHECK:
    wc = f"NOT (agency_code IN {bad_ag(cut)!r})".replace(",)", ")")
    x = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) FILTER (WHERE {DEGREE}) / sum(n) FILTER (WHERE lvl IS NOT NULL) s FROM edu_all
        WHERE {WINDOW} AND {wc} GROUP BY 1""").df().set_index("yr").s.sort_index()
    b(f"Check, bachelor's or more with {'no agency left out' if cut >= 1 else f'agencies at {cut:.0%} or more left out ({chr(44).join(bad_ag(cut))})'}: "
      f"{BASE} average {x[BASE_YEARS].mean():.1%} (range {x[BASE_YEARS].min():.1%} to {x[BASE_YEARS].max():.1%}); {SHOCK} {x[SHOCK]:.1%}; {YEARS[-1]}* {x[YEARS[-1]]:.1%}.")
xe = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) FILTER (WHERE {DEGREE}) / sum(n) FILTER (WHERE lvl IS NOT NULL) s FROM edu_acc
    WHERE {WINDOW} AND agency_code <> 'HS' GROUP BY 1 ORDER BY 1""").df().set_index("yr").s
b("Bachelor's or more, Homeland Security (HS) left out: " + "; ".join(f"{y} {v:.1%}" for y, v in xe.items()) + f". {BASE} average {xe[BASE_YEARS].mean():.1%}.")
ENF = "1801"   # general inspection, investigation, enforcement and compliance: ICE's deportation officers are most of DHS's hires in it lately
ef = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) n, sum(n) FILTER (WHERE {DEGREE}) / sum(n) FILTER (WHERE lvl IS NOT NULL) s FROM edu_acc
    WHERE {WINDOW} AND agency_code = 'HS' AND occ = '{ENF}' GROUP BY 1 ORDER BY 1""").df().set_index("yr")
b(f"Homeland Security (HS) new hires in series {ENF} {sname.get(ENF, '').title()}, share with a bachelor's or more: "
  + "; ".join(f"{y} {r.s:.0%} of {r.n:,.0f}" for y, r in ef.iterrows())
  + f". {BASE} range {ef.s[BASE_YEARS].min():.0%} to {ef.s[BASE_YEARS].max():.0%}. OPM's files don't record what the job required, so this shows who was hired, not whether a requirement changed.")
eo = db.sql(f"""SELECT CASE WHEN substr(eff, 1, 4)::INT < {SHOCK} THEN 'base' ELSE substr(eff, 1, 4) END p, occ,
    sum(n) FILTER (WHERE {DEGREE}) deg, sum(n) n FROM edu_acc WHERE {WINDOW} AND lvl IS NOT NULL GROUP BY ALL""").df()
for p1 in (str(YEARS[-1]),):
    t = eo[eo.p == "base"].set_index("occ")[["deg", "n"]].join(eo[eo.p == p1].set_index("occ")[["deg", "n"]], lsuffix="0", rsuffix="1", how="outer").fillna(0)
    s0, s1, y0, y1, mix_c, within_c, tot = split(t, "deg")
    split_table(f"education_by_occupation_{p1}", t, s0, s1, y0, y1, mix_c, within_c, "bachelor's or more")
    p1_txt = p1 + ("*" if p1 == str(YEARS[-1]) else "")
    b(f"{p1_txt} vs {BASE} (pooled): share with a bachelor's or more {t.deg0.sum() / t.n0.sum():.1%} -> {t.deg1.sum() / t.n1.sum():.1%} "
      f"({tot * 100:+.1f} points): which occupations were hired for {mix_c.sum() * 100:+.1f} ({split.avg * 100:+.1f} with average weights), more or less education within the same occupations {within_c.sum() * 100:+.1f}.")
    lab_o = lambda o: f"{o} {sname.get(o, '').title()} ({s0[o]:.1%} of {BASE} hires -> {s1[o]:.1%}; {y0[o]:.0%} with a degree)"
    b(f"{p1_txt}, occupations moving the share most through the mix, up: " + "; ".join(f"{lab_o(o)} {v * 100:+.2f}" for o, v in mix_c.sort_values(ascending=False).head(5).items())
      + "; down: " + "; ".join(f"{lab_o(o)} {v * 100:+.2f}" for o, v in mix_c.sort_values().head(5).items()))
    b(f"{p1_txt}, occupations moving it most within the occupation: " + "; ".join(
        f"{o} {sname.get(o, '').title()} ({y0[o]:.0%} -> {y1[o]:.0%}) {v * 100:+.2f}" for o, v in within_c.abs().sort_values(ascending=False).head(5).index.to_series().map(within_c).items()))

h(f"Veterans among new hires ({MONTH_SPAN}; new hires, permanent appointments)")
vh = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) FILTER (WHERE vet = 'Y') v, sum(n) n FROM age_acc WHERE {NEW_HIRE} AND {WINDOW} GROUP BY 1 ORDER BY 1""").df().set_index("yr")
b("Veterans as a share of new hires: " + "; ".join(f"{y} {r.v / r.n:.1%} ({r.v:,.0f})" for y, r in vh.iterrows())
  + f". {YEARS[-1]}* vs {BASE_YEARS[-1]}: {(vh.v / vh.n)[YEARS[-1]] * 100 - (vh.v / vh.n)[BASE_YEARS[-1]] * 100:+.1f} points.")
vs_ = db.sql(f"""SELECT file, sum(n) FILTER (WHERE vet = 'Y') / sum(n) s FROM '{DATA}/scd_check.parquet' WHERE ds = 'employment' AND file LIKE '%01'
    AND vet IN ('Y', 'N') GROUP BY 1 ORDER BY 1""").df().set_index("file").s
table("veterans_share_of_hires", pd.DataFrame({"veteran new hires": vh.v.astype(int), "all new hires": vh.n.astype(int), "share veterans": (vh.v / vh.n).round(3),
      "veterans' share of permanent staff, January": vs_.rename(lambda f: int(f[:4])).round(3)}).rename_axis("year (January-August)"))
b("Veterans as a share of permanent staff, each January: " + "; ".join(f"{f[:4]} {v:.1%}" for f, v in vs_.items()))
vo = db.sql(f"""SELECT substr(eff, 1, 4) p, occ, sum(n) FILTER (WHERE vet = 'Y') v, sum(n) n FROM age_acc WHERE {NEW_HIRE} AND {WINDOW}
    AND substr(eff, 1, 4) IN ('{BASE_YEARS[-1]}', '{YEARS[-1]}') GROUP BY ALL""").df()
t = vo[vo.p == str(BASE_YEARS[-1])].set_index("occ")[["v", "n"]].join(vo[vo.p == str(YEARS[-1])].set_index("occ")[["v", "n"]], lsuffix="0", rsuffix="1", how="outer").fillna(0)
s0, s1, y0, y1, mix_c, within_c, tot = split(t, "v")
b(f"{YEARS[-1]}* vs {BASE_YEARS[-1]}: veteran share {t.v0.sum() / t.n0.sum():.1%} -> {t.v1.sum() / t.n1.sum():.1%} ({tot * 100:+.1f} points): which occupations "
  f"were hired for {mix_c.sum() * 100:+.1f} ({split.avg * 100:+.1f} with average weights), more or fewer veterans within the same occupations {within_c.sum() * 100:+.1f}. Largest mix parts: "
  + "; ".join(f"{o} {sname.get(o, '').title()} ({s0[o]:.1%} -> {s1[o]:.1%} of hires; {y0[o]:.0%} veterans) {v * 100:+.2f}" for o, v in mix_c.abs().sort_values(ascending=False).head(4).index.to_series().map(mix_c).items()))

h("Political and other at-will appointments (all appointment types, headcount)")
AW_SQL = "(" + ", ".join(f"'{c_}'" for c_ in AT_WILL) + ")"
PC = [c_ for c_, lbl in AT_WILL.items() if lbl.startswith("Schedule Policy/Career")]   # the codes for Schedule Policy/Career
PC_SQL = "(" + ", ".join(f"'{c_}'" for c_ in PC) + ")"
aw = db.sql(f"""SELECT snap, appt, sum(n) n FROM (SELECT snap, appt, n FROM '{DATA}/emp.parquet' UNION ALL SELECT snap, appt, n FROM '{DATA}/hc.parquet')
    WHERE appt IN {AW_SQL} GROUP BY ALL""").df().pivot(index="snap", columns="appt", values="n").reindex(columns=list(AT_WILL)).fillna(0)
b("Codes: " + "; ".join(f"{c_} {lbl}" for c_, lbl in AT_WILL.items()) + f". {AT_WILL[PC[0]]} ({PC[0]}) is among the permanent codes, so those staff are also in every permanent figure in this file.")
for c_ in [c_ for c_ in AT_WILL if c_ not in PC]:
    j = aw.loc[[x for x in aw.index if x.endswith("01")], c_]
    b(f"{AT_WILL[c_][0].upper() + AT_WILL[c_][1:]}: each January " + "; ".join(f"{x[:4]} {v:,.0f}" for x, v in j.items()) + f"; {month(aw.index[-1])} {aw[c_].iloc[-1]:,.0f}. "
      f"January a year into each term: " + ", ".join(f"{int(t_[:4]) + 1} {aw.loc[f'{int(t_[:4]) + 1}01', c_]:,.0f}" for t_ in TERM_STARTS if f"{int(t_[:4]) + 1}01" in aw.index)
      + f". Highest January {YEARS[0]}-{BASE_YEARS[-1]}: {j[[x for x in j.index if int(x[:4]) <= BASE_YEARS[-1]]].max():,.0f}.")
pcs = aw[PC].sum(axis=1)
first_pc = pcs[pcs > 0].index.min()
pc_hires = db.sql(f"SELECT sum(n) FROM '{DATA}/acc.parquet' WHERE appt IN {PC_SQL}").fetchone()[0] or 0
pc_ag = db.sql(f"""SELECT agency_code, sum(n) n FROM '{DATA}/hc.parquet' WHERE appt IN {PC_SQL} AND snap = '{aw.index[-1]}' GROUP BY 1 ORDER BY 2 DESC LIMIT 6""").fetchall()
pc_oc = db.sql(f"""SELECT occupational_series_code, sum(n) n FROM '{DATA}/hc.parquet' WHERE appt IN {PC_SQL} AND snap = '{aw.index[-1]}' GROUP BY 1 ORDER BY 2 DESC LIMIT 5""").fetchall()
b(f"Schedule Policy/Career: first in the files in {month(first_pc)} ({pcs[first_pc]:,.0f}); {pcs.iloc[-1]:,.0f} in {month(aw.index[-1])}. Hires into it, in any file: {pc_hires:,.0f}, "
  "so nearly all are staff moved from other appointments (the files don't record the move). Largest agencies: "
  + "; ".join(f"{agname.get(a_, a_).title()} ({a_}) {n_:,.0f}" for a_, n_ in pc_ag) + ". Largest occupations: "
  + "; ".join(f"{o_} {sname.get(o_, '').title()} {n_:,.0f}" for o_, n_ in pc_oc) + ".")
tot_aw = aw.sum(axis=1)
table("at_will_appointments", aw.rename(columns=AT_WILL).assign(total=tot_aw).astype(int).rename_axis("month"))
b(f"All at-will appointments above: {month(aw.index[-1])} {tot_aw.iloc[-1]:,.0f}; January {SHOCK} {tot_aw[INAUG]:,.0f}; highest January {YEARS[0]}-{BASE_YEARS[-1]} "
  f"{tot_aw[[x for x in tot_aw.index if x.endswith('01') and int(x[:4]) <= BASE_YEARS[-1]]].max():,.0f}.")
awh = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, appt, sum(n) n FROM '{DATA}/acc.parquet' WHERE appt IN {AW_SQL} AND {WINDOW} GROUP BY ALL""").df().pivot(
    index="yr", columns="appt", values="n").reindex(columns=list(AT_WILL)).fillna(0)
ag_pc = db.sql(f"""SELECT agency_code a, sum(n) n, sum(n) FILTER (WHERE appt IN {PC_SQL}) pc FROM '{DATA}/hc.parquet' WHERE snap = '{aw.index[-1]}'
    GROUP BY 1 HAVING sum(n) >= {MIN_STAFF}""").df().fillna(0).set_index("a").sort_values("n", ascending=False)
none_pc = ag_pc[ag_pc.pc == 0]
b(f"Agencies with {MIN_STAFF:,}+ staff in {month(aw.index[-1])}: {len(ag_pc)}; with anyone in Schedule Policy/Career: {(ag_pc.pc > 0).sum()}; with no one yet: {len(none_pc)}, "
  + "including " + "; ".join(f"{agname.get(a_, a_).title()} ({a_}, {r.n:,.0f} staff)" for a_, r in none_pc.head(6).iterrows()) + ".")
pc_share = db.sql(f"""SELECT agency_code a, sum(n) n, sum(n) FILTER (WHERE appt IN {PC_SQL}) pc FROM '{DATA}/hc.parquet' WHERE snap = '{aw.index[-1]}'
    GROUP BY 1 HAVING sum(n) FILTER (WHERE appt IN {PC_SQL}) > 0 ORDER BY 1""").df().set_index("a")   # agency order breaks ties below
table("schedule_policy_career_share_by_agency", pc_share.assign(name=[agname.get(a_, a_).title() for a_ in pc_share.index], share=(pc_share.pc / pc_share.n).round(3))
      .rename(columns={"n": f"staff, {month(aw.index[-1])}", "pc": "in Schedule Policy/Career", "share": "share of staff"})
      .astype({f"staff, {month(aw.index[-1])}": int, "in Schedule Policy/Career": int}).sort_values("share of staff", ascending=False, kind="stable")[["name", f"staff, {month(aw.index[-1])}", "in Schedule Policy/Career", "share of staff"]].rename_axis("agency"))
table("schedule_policy_career_by_occupation", pd.DataFrame(pc_oc, columns=["series", "in Schedule Policy/Career"]).assign(name=lambda d: d.series.map(lambda o: sname.get(o, "").title()))
      .set_index("series").pipe(lambda d: pd.concat([d, pd.DataFrame({"in Schedule Policy/Career": [pc_hires], "name": ["(hires into it, any file)"]}, index=["hires"])])))
ser = {"Schedule C": aw["44"], "Noncareer and limited-term SES": aw["55"] + aw["60"]}   # Schedule Policy/Career has its own chart (10)
dates = pd.to_datetime([f"{x[:4]}-{x[4:]}-01" for x in aw.index])
# title check: each line is above its highest January before the shock, and Schedule C a year into this term is above the same point in every earlier term
old_jan = [x for x in aw.index if x.endswith("01") and int(x[:4]) <= BASE_YEARS[-1]]
above9 = {lbl: v.iloc[-1] / v[old_jan].max() for lbl, v in ser.items()}
yr_in = {t_: ser["Schedule C"].get(f"{int(t_[:4]) + 1}01") for t_ in TERM_STARTS}
yr_in = {t_: v for t_, v in yr_in.items() if v is not None}
fig, ax = frame(4.6, bottom_in=0.75, left=0.07, right=0.8)
for (lbl, v), color in zip(ser.items(), (TYPE_COLOR["Quit"], TYPE_COLOR["Retirement"])):
    ax.plot(dates, v.values, color=color, lw=2.4, marker="o", ms=3)
    ax.text(dates[-1] + pd.Timedelta(days=60), v.iloc[-1], f"{lbl}  {v.iloc[-1]:,.0f}", color=INK, va="center", fontsize=10, fontweight=600)
for t_ in TERM_STARTS:
    ax.axvline(pd.Timestamp(f"{t_[:4]}-{t_[4:]}-20"), color=MUTED, lw=1, ls=(0, (4, 3)))
    ax.text(pd.Timestamp(f"{t_[:4]}-{t_[4:]}-20"), ax.get_ylim()[1] * 0.97, " inauguration", color=MUTED, fontsize=8.5, va="top")
ax.grid(axis="y", color=GRID); ax.set_axisbelow(True); ax.tick_params(axis="y", colors=MUTED)
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
finish(fig, "9_at_will_appointments", claim("Chart 9 title", yr_in[max(yr_in)] > max(v for t_, v in yr_in.items() if t_ != max(yr_in)), "Political appointees have refilled faster than in either of the last two terms",
                                          "Political appointments: " + "; ".join(f"{lbl} {r_:.2f} times its highest January {YEARS[0]}-{BASE_YEARS[-1]}" for lbl, r_ in above9.items())),
       f"Political appointees, all appointment types: each January to {month(MONTHLY_FROM)}, then monthly",
       [f"Before {month(MONTHLY_FROM)} only January counts are read, so the lines skip the months between. Noncareer SES and limited-term SES are combined."], perm=False)

# ---- 10. Schedule Policy/Career: who is in it, by agency ------------------------------------------------------
PC_TOP = 10
pc_share = pc_share.assign(s_=pc_share.pc / pc_share.n).sort_values("s_", ascending=False, kind="stable")   # the agency where it's the largest share comes first
top_pc_name = agname.get(pc_share.index[0], pc_share.index[0]).title().replace(" Of ", " of ").replace(" And ", " and ")
top10 = pc_share.sort_values("pc", ascending=False, kind="stable").head(PC_TOP).iloc[::-1]
pc_tot = pcs.iloc[-1]
fig, ax = frame(0.42 * PC_TOP + 0.9, top_in=0.3, bottom_in=0.3, left=0.3, right=0.86)
ax.barh(range(PC_TOP), top10.pc, color=TYPE_COLOR["Layoff (RIF)"], height=0.62)
ax.set_yticks(range(PC_TOP), [agname.get(a_, a_).title().replace("Department Of The ", "").replace("Department Of ", "").replace(" Of ", " of ").replace(" And ", " and ") for a_ in top10.index], fontsize=10.5, color=INK)
for k_, (a_, r_) in enumerate(top10.iterrows()):
    ax.text(r_.pc + top10.pc.max() * 0.015, k_, f"{r_.pc:,.0f}  ({r_.pc / r_.n:.0%} of its staff)" if r_.pc / r_.n >= 0.1 else f"{r_.pc:,.0f}  ({r_.pc / r_.n:.1%} of its staff)",
            va="center", fontsize=10, color=INK)
ax.set_xlim(0, top10.pc.max() * 1.35); ax.set_xticks([])
for sp in ("top", "right", "bottom"):
    ax.spines[sp].set_visible(False)
finish(fig, "10_schedule_policy_career", claim("Chart 10 title", pc_share.pc.iloc[0] / pc_share.n.iloc[0] > 0.5,
                                              f"At the {top_pc_name}, Schedule Policy/Career is most of the agency",
                                              f"Schedule Policy/Career is {pc_share.pc.iloc[0] / pc_share.n.iloc[0]:.0%} of the {top_pc_name}"),
       f"Staff in Schedule Policy/Career, {month(aw.index[-1])}: the {PC_TOP} agencies with the most",
       [f"It first appears in the {month(first_pc)} files. {pc_hires:,.0f} of the {pc_tot:,.0f} were hired into it; the files don't record moves between appointments, so the rest are counted as moved.",
        "Share of staff is of all the agency's staff, every appointment type.",
        f"{aw[[c_ for c_ in PC if c_ in PERM]].iloc[-1].sum():,.0f} hold it as a permanent appointment, so they are in every permanent figure in the post; "
        f"{aw[[c_ for c_ in PC if c_ not in PERM]].iloc[-1].sum():,.0f} hold it as a nonpermanent one."], perm=False)
b(f"Arrivals into these appointments (hires and transfers in), {MONTH_SPAN}: " + "; ".join(f"{y} " + ", ".join(f"{AT_WILL[c_]} {r[c_]:,.0f}" for c_ in AT_WILL if c_ not in PC) for y, r in awh.iterrows()) + ".")

h("Data notes")
# When OPM's own length_of_service_years started following the leave service date (extract.py's scd_check: per file, by
# veteran status, the share of permanent records whose OPM value is within SCD_TOL years of the time since that date).
sc = db.sql(f"""SELECT ds, file, vet, sum(n) n, sum(same) / sum(n) same, sum(opm_mean * n) / sum(n) opm, sum(scd_mean * n) / sum(n) scd
    FROM '{DATA}/scd_check.parquet' WHERE vet IN ('Y', 'N') GROUP BY ALL""").df()
sw = sc.pivot_table(index=["ds", "file"], columns="vet", values="same")
switched = sw[(sw.min(axis=1) >= 0.99)].reset_index().groupby("ds").file.min()   # first file where both groups match
assert switched.nunique() == 1 and (sw.loc[(slice(None), slice(switched.iloc[0], None)), :].min(axis=1) >= 0.98).all()
SWITCH = switched.iloc[0]
pre = sw[sw.index.get_level_values("file") < ym_of(mi(SWITCH) - 1)]
b(f"Years of service: OPM changed how it reports them, without a note in its release notes (checked by hand). From the {month(SWITCH)} files on, "
  "OPM's length_of_service_years equals the time since the leave service date (service_computation_date_leave) for every record; before, "
  f"it often left military time out. Share of permanent records where the two agree (within {SCD_TOL} years), veterans / non-veterans:")
for ds in ("separations", "accessions", "employment"):
    x = sw.loc[ds]
    pr = pre.loc[ds]
    F.append(f"  - {ds.capitalize()}: files before {month(ym_of(mi(SWITCH) - 1))}, {pr.Y.min():.0%}-{pr.Y.max():.0%} / {pr.N.min():.0%}-{pr.N.max():.0%}; "
             + "; ".join(f"{month(f)} {x.loc[f, 'Y']:.0%} / {x.loc[f, 'N']:.0%}" for f in x.index if mi(SWITCH) - 3 <= mi(f) <= mi(SWITCH) + 1) + ".")
table("years_of_service_check", sw.rename(columns={"Y": "veterans", "N": "non-veterans"}).round(3).reset_index().assign(file=lambda d: d.file.map(month))
      .set_index(["ds", "file"]).rename_axis(["file type", f"file (share where OPM's years of service match the leave service date within {SCD_TOL} years)"]))
v_ = sc[(sc.ds == "employment") & (sc.vet == "Y")].set_index("file").sort_index()
b("Veteran permanent staff, average years of service, OPM's field vs from the leave service date: "
  + "; ".join(f"{month(f)} {v_.loc[f, 'opm']:.1f} vs {v_.loc[f, 'scd']:.1f}" for f in v_.index if mi(SWITCH) - 2 <= mi(f) <= mi(SWITCH)) + ".")
b("So every years-of-service figure in this file (bands, retirement eligibility, prior service at hire, the new-hire cohorts) is computed from "
  "the leave service date in every file, putting all years on OPM's definition (Outside sources). Using OPM's field as reported would mix two "
  "definitions inside one year: departures on the new one, the January staff they're divided by on the old.")
# What OPM's field as published would show (extract.py's asis_*: both measures on the same records, same months every year).
AS_SEP, AS_ACC, AS_EMP = (f"'{DATA}/asis_{t}.parquet'" for t in ("sep", "acc", "emp"))
asis = {}
for col in ("band_opm", "band_scd"):
    q_ = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) q FROM {AS_SEP} WHERE {WINDOW} AND cat = 'SC' AND drp <> 'Y' AND {col} = 'c'
        GROUP BY 1""").df().set_index("yr").q
    st_ = db.sql(f"SELECT substr(snap, 1, 4)::INT yr, sum(n) st FROM {AS_EMP} WHERE {col} = 'c' GROUP BY 1").df().set_index("yr").st
    pr_ = db.sql(f"""SELECT substr(eff, 1, 4)::INT yr, sum(n) FILTER (WHERE {col.replace('band', 'prior')}) / sum(n) s FROM {AS_ACC}
        WHERE {WINDOW} AND vet = 'N' GROUP BY 1""").df().set_index("yr").s
    asis[col] = (q_.reindex(YEARS), st_.reindex(YEARS), (q_ / int(LAST_M) / st_ * PER).reindex(YEARS), pr_.reindex(YEARS))
# The recomputed side must reproduce the figures elsewhere in this file (same records, same definition).
assert (asis["band_scd"][0] == band_n["quit"].loc[BANDS["c"], YEARS]).all(), (asis["band_scd"][0], band_n["quit"].loc[BANDS["c"], YEARS])
assert (asis["band_scd"][1] == band_staff.loc[BANDS["c"], YEARS]).all()
asis_t = pd.DataFrame({f"{BANDS['c']} quits {RATE} per month, as published": asis["band_opm"][2].round(2),
                       f"{BANDS['c']} quits {RATE} per month, recomputed": asis["band_scd"][2].round(2),
                       "non-veteran new hires with prior service, as published": asis["band_opm"][3].round(3),
                       "non-veteran new hires with prior service, recomputed": asis["band_scd"][3].round(3)}).rename_axis(f"year ({MONTH_SPAN})")
table("years_of_service_as_published", asis_t)
for col, txt in (("band_opm", "as published (OPM's length_of_service_years)"), ("band_scd", "recomputed from the leave service date (every figure in this file)")):
    pq, pv = asis[col][2], asis[col][3]
    b(f"Years of service {txt}, {MONTH_SPAN}: {BANDS['c']} quits {RATE} per month {YEARS[-1]}* {pq[YEARS[-1]]:.2f}, {pq[YEARS[-1]] / pq[BASE_YEARS].max():.2f}x the {BASE} high "
      f"({pq[BASE_YEARS].max():.2f}, {pq[BASE_YEARS].idxmax()}); non-veteran new hires with prior service {pv[YEARS[-1]]:.0%} vs a {BASE} average of {pv[BASE_YEARS].mean():.0%} "
      f"({pv[YEARS[-1]] / pv[BASE_YEARS].mean():.2f}x).")
own = db.sql(f"""SELECT eff, sum(n) FILTER (WHERE file = eff) own, sum(n) total FROM sep WHERE substr(eff, 1, 4) = '{BASE_YEARS[-1]}' AND cat NOT IN {TRANSFERS}
    GROUP BY 1 ORDER BY 1""").df()
own["share"] = own.own / own.total * 100
own_now = db.sql(f"""SELECT eff, sum(n) FILTER (WHERE file = eff) / sum(n) * 100 AS pct FROM sep WHERE eff IN {tuple(LAG_MONTHS)} AND cat NOT IN {TRANSFERS}
    GROUP BY 1""").df().pct
b(f"Share of a month's departures that were in its own file: {BASE_YEARS[-1]} months, a median {own.share.median():.1f}% (range {own.share.min():.1f}% to {own.share.max():.1f}%); "
  f"{month(LAG_MONTHS[0])} to {month(LAG_MONTHS[-1])}, a median {own_now.median():.0f}% ({own_now.min():.0f}% to {own_now.max():.0f}%). So the newest months, {NEWEST} most, "
  "will rise by more than they used to; the Reporting lag section estimates how much.")
# Monthly agency headcounts (agencies with MIN_STAFF or more) that jump away from both neighbouring months and come straight back (GLITCH_PCT or more).
# The data can't say whether such a month is missing or duplicated records or a real event that reversed, so each is
# listed with that month's recorded flows; flagged agency-months are left out of the month-by-month lows further down.
def glitches(s_):
    s_, out = s_.dropna().astype(float).copy(), []
    while len(s_) >= 3:
        mid = (s_.shift(1) + s_.shift(-1)) / 2
        cand = ((s_ - mid) / mid).abs().where((s_ - s_.shift(1)) * (s_.shift(-1) - s_) < 0)
        if cand.isna().all() or cand.max() * 100 < GLITCH_PCT:
            break
        k = cand.idxmax()
        out.append((k, s_[k], mid[k]))
        s_[k] = mid[k]   # set it aside and look again
    return out


agy_m = db.sql("SELECT snap, agency_code a, sum(n) n FROM hc GROUP BY ALL").df().pivot(index="snap", columns="a", values="n")
agy_m = agy_m.loc[:, agy_m.median() >= MIN_STAFF]   # in smaller agencies a few people move a month by GLITCH_PCT
FLAGGED = [(a, k, v, mid) for a in agy_m.columns for k, v, mid in glitches(agy_m[a])]
for a, k, v, mid in FLAGGED:
    out_, in_ = (db.sql(f"SELECT sum(n) FROM {t} WHERE agency_code = '{a}' AND eff = '{k}'").fetchone()[0] or 0
                 for t in ("sep", f"(SELECT * FROM '{DATA}/acc.parquet' WHERE appt IN {PERM})"))
    b(f"Agency {a}, {month(k)}: {v:,.0f} permanent staff against {mid:,.0f} on average in the months either side ({(v - mid) / mid * 100:+.1f}%, "
      f"{v - mid:+,.0f}), then back. Recorded that month: {out_:,.0f} departures and transfers out, {in_:,.0f} arrivals.")
assert not any(k.split()[0] in DEFENSE for k in EXAMPLES)
b("No named example is a Defense occupation.")
doj = {k: db.sql(q).fetchone()[0] or 0 for k, q in {
    "jan25": f"SELECT sum(n) FROM emp WHERE snap = '{INAUG}' AND agency_code = 'DJ' AND {ATT}",
    "now": f"SELECT sum(n) FROM hc WHERE snap = '{PARTIAL_TO}' AND agency_code = 'DJ' AND {ATT}",
    "left": f"SELECT sum(n) FROM sep WHERE agency_code = 'DJ' AND {ATT} AND eff BETWEEN '{AFTER}' AND '{PARTIAL_TO}'",
    "in": f"SELECT sum(n) FROM '{DATA}/acc.parquet' WHERE appt IN {PERM} AND agency_code = 'DJ' AND {ATT} AND eff BETWEEN '{AFTER}' AND '{PARTIAL_TO}'"}.items()}
b(f"DOJ attorneys, a check before quoting them: headcount went from {doj['jan25']:,.0f} ({JAN}) to {doj['now']:,.0f} ({NEWEST}), {doj['now'] - doj['jan25']:+,.0f}; "
  f"recorded arrivals minus departures (transfers included) since {month(AFTER)}: {doj['in'] - doj['left']:+,.0f}. "
  f"A gap of {(doj['now'] - doj['jan25']) - (doj['in'] - doj['left']):+,.0f} that the hires and departures files don't account for.")
# The gap's other side: DOJ's nonpermanent attorneys (appointment codes 40 and 48) shrank by about as much more than their own flows explain.
NP = "(" + ", ".join(f"'{c}'" for c in NONPERM_ATTORNEY) + ")"
npd = {k: db.sql(q).fetchone()[0] or 0 for k, q in {
    "jan25": f"SELECT sum(n) FROM '{DATA}/emp.parquet' WHERE snap = '{INAUG}' AND agency_code = 'DJ' AND {ATT} AND appt IN {NP}",
    "now": f"SELECT sum(n) FROM '{DATA}/hc.parquet' WHERE snap = '{PARTIAL_TO}' AND agency_code = 'DJ' AND {ATT} AND appt IN {NP}",
    "left": f"SELECT sum(n) FROM '{DATA}/sep.parquet' WHERE agency_code = 'DJ' AND {ATT} AND appt IN {NP} AND eff BETWEEN '{AFTER}' AND '{PARTIAL_TO}'",
    "in": f"SELECT sum(n) FROM '{DATA}/acc.parquet' WHERE agency_code = 'DJ' AND {ATT} AND appt IN {NP} AND eff BETWEEN '{AFTER}' AND '{PARTIAL_TO}'"}.items()}
np_gap = (npd["now"] - npd["jan25"]) - (npd["in"] - npd["left"])
mo = db.sql(f"""SELECT snap, sum(n) FILTER (WHERE appt IN {PERM}) p, sum(n) FILTER (WHERE appt IN {NP}) np FROM '{DATA}/hc.parquet'
    WHERE agency_code = 'DJ' AND {ATT} GROUP BY 1 ORDER BY 1""").df().set_index("snap").diff()
big = mo.np.idxmin()
assert np_gap < 0 and abs(np_gap + ((doj['now'] - doj['jan25']) - (doj['in'] - doj['left']))) < 0.15 * abs(np_gap)
b(f"The other side of that gap: DOJ's nonpermanent attorneys (appointment codes {' and '.join(NONPERM_ATTORNEY)}) went from {npd['jan25']:,.0f} to {npd['now']:,.0f}, "
  f"a drop {abs(np_gap):,.0f} bigger than their own arrivals ({npd['in']:,.0f}) and departures ({npd['left']:,.0f}) explain. The largest monthly move was into "
  f"{month(big)}: nonpermanent {mo.np[big]:+,.0f}, permanent {mo.p[big]:+,.0f}. The two gaps match in size and timing, which fits attorneys being "
  "converted from nonpermanent to permanent appointments; neither file records a conversion, so this is an inference. If so, permanent-only attorney "
  "figures include them from the month they converted.")
jan26 = f"{PARTIAL_TO[:4]}01"
by_sub = db.sql(f"""SELECT agency_subelement_code sub, sum(n) FILTER (WHERE snap = '{INAUG}') a, sum(n) FILTER (WHERE snap = '{jan26}') b_
    FROM '{DATA}/emp.parquet' WHERE agency_code = 'DJ' AND {ATT} AND appt IN {NP} GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT 3""").df()
sub_names = dict(db.sql(f"SELECT agency_subelement_code, any_value(sub) FROM '{RA}' WHERE agency_code = 'DJ' GROUP BY 1").fetchall())
b(f"DOJ nonpermanent attorneys by component, {JAN} to {month(jan26)}: "
  + "; ".join(f"{sub_names.get(r.sub, r.sub).title()} ({r.sub}) {r.a:,.0f} to {r.b_:,.0f}" for r in by_sub.itertuples()) + ".")


h("Rookie screen: what's behind each component that rose")
behind = []
for u in screen.index[screen.rise >= SCREEN_RISES[0]]:
    w0, w1, cut = f"{LATEST}{AUTUMN[0]}", f"{LATEST}{AUTUMN[1]}", f"{LATEST + 1}{LAST_M}"
    ser = db.sql(f"""SELECT occupational_series_code, sum(n) n FROM '{RA}' WHERE agency_subelement_code = '{u}' AND appt IN {PERM}
        AND eff BETWEEN '{w0}' AND '{w1}' AND file <= '{cut}' GROUP BY 1 ORDER BY 2 DESC LIMIT 3""").fetchall()
    how = db.sql(f"""SELECT cat, sum(n) n FROM '{RS}' WHERE agency_subelement_code = '{u}' AND appt IN {PERM} AND cat NOT IN {TRANSFERS}
        AND eff <= '{cut}' AND file <= '{cut}' AND {ROOKIE_HIRE_YM} BETWEEN '{w0}' AND '{w1}' GROUP BY 1 ORDER BY 2 DESC""").fetchall()
    b(f"{screen.loc[u, 'component']} ({u}), {LATEST} hires: top series " + ", ".join(f"{s_} {sname.get(s_, '').title()} ({n:,.0f})" for s_, n in ser)
      + "; how they left (OPM codes): " + ", ".join(f"{c} {n:,.0f}" for c, n in how)
      + "; hires per autumn: " + ", ".join(f"{y} {screen.loc[u, f'hires_{y}']:,.0f}" for y in SCREEN_YEARS) + ".")
    behind.append({"component": screen.loc[u, "component"], f"top series of {LATEST} hires": "; ".join(f"{s_} {sname.get(s_, '').title()} ({n:,.0f})" for s_, n in ser),
                   "how they left (OPM codes: SC quit, SJ termination, SL other)": "; ".join(f"{c} {n:,.0f}" for c, n in how)})
table("rookie_screen_behind", pd.DataFrame(behind).set_index("component"))

h(f"Does headcount change match the flows? ({JAN} to {NEWEST})")
fl = {k: db.sql(q).fetchone()[0] or 0 for k, q in {
    "hires": f"SELECT sum(n) FROM '{DATA}/acc.parquet' WHERE appt IN {PERM} AND cat IN ('AC', 'AD', 'AE') AND eff BETWEEN '{AFTER}' AND '{PARTIAL_TO}'",
    "xin": f"SELECT sum(n) FROM '{DATA}/acc.parquet' WHERE appt IN {PERM} AND cat IN ('AA', 'AB') AND eff BETWEEN '{AFTER}' AND '{PARTIAL_TO}'",
    "left": f"SELECT sum(n) FROM sep WHERE cat NOT IN {TRANSFERS} AND eff BETWEEN '{AFTER}' AND '{PARTIAL_TO}'",
    "xout": f"SELECT sum(n) FROM sep WHERE cat IN {TRANSFERS} AND eff BETWEEN '{AFTER}' AND '{PARTIAL_TO}'"}.items()}
flow = fl["hires"] + fl["xin"] - fl["left"] - fl["xout"]
b(f"Headcount change {staff_now - staff_then:+,.0f}; hires {fl['hires']:,.0f} + transfers in {fl['xin']:,.0f} - departures {fl['left']:,.0f} - transfers out "
  f"{fl['xout']:,.0f} = {flow:+,.0f}; unexplained {(staff_now - staff_then) - flow:+,.0f} ({abs((staff_now - staff_then) - flow) / staff_then:.2%} of {JAN} staff). "
  "The cause of the gap isn't in this data.")

h("OPM separation codes by year")
codes = db.sql(f"SELECT DISTINCT substr(eff, 1, 4)::INT yr, cat FROM sep WHERE substr(eff, 1, 4)::INT >= {YEARS[0]}").df()
old_codes = codes[codes.cat.isin(["SF", "SI", "SK"])]
assert old_codes.empty, old_codes   # disability retirement, removals and deaths are folded into SG and SL in every year
b(f"Codes present {YEARS[0]}-{YEARS[-1]}: {', '.join(sorted(codes.cat.unique()))}. The retired codes SF (disability retirement), SI (removal) and SK (death) "
  "appear in no year, so OPM's folding of them into SG and SL applies to the whole history here.")

h(f"Occupations that stand out ({MIN_STAFF:,}+ permanent staff; {JAN} = 100; {NEWEST})")
mon = db.sql(f"SELECT snap, {K} k, sum(n) n FROM hc WHERE snap >= '{AFTER}' GROUP BY ALL").df().pivot(index="k", columns="snap", values="n")
for a, k, *_ in FLAGGED:   # flagged agency-months don't count as an occupation's low
    mon.loc[mon.index.str.startswith(a + " "), k] = np.nan
occ2 = occ.join(mon.min(axis=1).rename("low")).join(names_occ := db.sql(f"SELECT {K} k, any_value(series) se FROM emp GROUP BY 1").df().set_index("k"))
occ2["low_idx"] = occ2.low / occ2.jan25 * 100
fl_occ = db.sql(f"""SELECT {K} k, sum(n) FILTER (WHERE cat NOT IN {TRANSFERS}) d FROM sep WHERE eff BETWEEN '{AFTER}' AND '{PARTIAL_TO}' GROUP BY 1""").df().set_index("k").d
in_occ = db.sql(f"""SELECT {K} k, sum(n) a FROM '{DATA}/acc.parquet' WHERE appt IN {PERM} AND eff BETWEEN '{AFTER}' AND '{PARTIAL_TO}' GROUP BY 1""").df().set_index("k").a
xo_occ = db.sql(f"SELECT {K} k, sum(n) x FROM sep WHERE cat IN {TRANSFERS} AND eff BETWEEN '{AFTER}' AND '{PARTIAL_TO}' GROUP BY 1").df().set_index("k").x
occ2["flow_gap"] = ((occ2.now - occ2.jan25) - (in_occ.reindex(occ2.index).fillna(0) - fl_occ.reindex(occ2.index).fillna(0) - xo_occ.reindex(occ2.index).fillna(0))) / occ2.jan25 * 100
ok_ = occ2[occ2.flow_gap.abs() <= FLOW_GAP_PCT]
lab = lambda k: f"{k} {str(ok_.loc[k, 'se']).title() if k in ok_.index else str(occ2.loc[k, 'se']).title()}"
b(f"Left out: {len(occ2) - len(ok_)} occupations whose headcount change and recorded flows differ by more than {FLOW_GAP_PCT}% of staff (the cause isn't in this data): "
  + "; ".join(f"{lab(k)} ({occ2.loc[k, 'flow_gap']:+.0f})" for k in occ2.index[occ2.flow_gap.abs() > FLOW_GAP_PCT]))
b("Grew most: " + "; ".join(f"{lab(k)} {v:.0f}" for k, v in ok_["index"].sort_values(ascending=False).head(5).items()))
b("Shrank most: " + "; ".join(f"{lab(k)} {v:.0f}" for k, v in ok_["index"].sort_values().head(5).items()))
rec = ok_[(ok_.low_idx <= LOW_INDEX) & (ok_["index"] - ok_.low_idx >= RECOVERY) & (~ok_.index.str.startswith(DEFENSE))]
b(f"Dropped to {LOW_INDEX} or below, then recovered {RECOVERY}+ points (Defense excluded: its monthly counts have record gaps; flagged months left out): "
  + ("; ".join(f"{lab(k)}: low {r.low_idx:.0f}, now {r['index']:.0f}" for k, r in rec.sort_values("jan25", ascending=False).iterrows()) or "none"))
if len(rec):   # a recovery with few or no arrivals is staff moved in from other series, not hiring
    low_at = mon.loc[rec.index].idxmin(axis=1)
    arr = {k: db.sql(f"""SELECT sum(n) FROM '{DATA}/acc.parquet' WHERE appt IN {PERM} AND {K} = '{k}' AND eff > '{low_at[k]}' AND eff <= '{PARTIAL_TO}'""").fetchone()[0] or 0
           for k in rec.index}
    b("The same occupations, staff gained since the low against permanent hires and transfers in since then: "
      + "; ".join(f"{lab(k)}: +{mon.loc[k, mon.columns.max()] - mon.loc[k, low_at[k]]:,.0f} staff, {arr[k]:,.0f} arrivals" for k in rec.index))
    table("hiring_back_recovered_occupations", pd.DataFrame({"name": [lab(k) for k in rec.index], f"low ({JAN} = 100)": rec.low_idx.round(1), f"{NEWEST} ({JAN} = 100)": rec["index"].round(1),
          "staff gained since the low": [int(mon.loc[k, mon.columns.max()] - mon.loc[k, low_at[k]]) for k in rec.index], "hires and transfers in since the low": [int(arr[k]) for k in rec.index]}).rename_axis("agency and series"))

h("Suggested chart headlines (not on the images)")
for name, title in HEADLINES:
    b(f"{name}: {title}")
h("Chart notes (footnotes for the post; not on the images)")
for name, notes in NOTES:
    b(f"{name}: " + " ".join(n.strip() for n in notes))
h("Chart titles and notes: claims checked against the data")
for chart, said, held, used in CLAIMS:
    b(f"{chart}: \"{said.strip()}\" " + ("holds." if held else f"doesn't hold with these settings, so the chart says \"{used.strip()}\" instead."))
nd = dict(NOTES)
table("charts", pd.DataFrame([{"chart": n, "headline": t, "description": nd[n][0], "notes": " ".join(x.strip() for x in nd[n][1:])} for n, t in HEADLINES]).set_index("chart"))
table("chart_claims", pd.DataFrame(CLAIMS, columns=["chart", "claim", "holds", "wording used"]).set_index("chart"))

h("Check against OPM's own files (verify_opm.py)")
chk = pd.read_csv(DATA / "opm_check.csv", dtype=str)
bad = chk[chk.match != "True"]
assert bad.empty, bad   # every file read here is OPM's current version, byte for byte
unchecked = set(db.sql(f"SELECT DISTINCT 'separations', file FROM '{DATA}/sep.parquet'").fetchall()) - set(zip(chk.dataset, chk.file))
if unchecked:
    b(f"Not yet checked against OPM: {len(unchecked)} separations files ({min(f for _, f in unchecked)} to {max(f for _, f in unchecked)}). Run verify_opm.py.")
b(f"All {len(chk)} files checked ({', '.join(f'{n} {d}' for d, n in chk.dataset.value_counts().items())}) are the version OPM marks current "
  f"on data.opm.gov and are byte-identical to OPM's download (SHA-256), checked {chk.checked.max()}.")

h("Chart 1's job label")
SRC = DATA / "sources"
jobs = db.sql(f"""SELECT series, CASE WHEN positionTitle ILIKE '%deportation officer%' THEN 'Deportation Officer'
        WHEN positionTitle ILIKE '%criminal investigator%' THEN 'Criminal Investigator' ELSE 'other title' END title, count(*) n
    FROM '{SRC}/usajobs_ice_1801_1811.parquet' WHERE payScale = 'GL' GROUP BY ALL ORDER BY ALL""").df()
b(f"Chart 1's job label: ICE's USAJOBS postings on the GL pay plan (the one chart 1 uses), opened {pd.Timestamp(USAJOBS_FROM):%B %Y} to {NEWEST} "
  "(usajobs_historical archive): " + "; ".join(f"series {r.series}: {r.n} titled {r.title}" for r in jobs.itertuples())
  + ". Postings, not hires: one posting can fill many jobs.")

(OUT / "facts.md").write_text("\n".join(F) + "\n")
subprocess.run([sys.executable, "check_literals.py"], check=True)   # no digit typed into facts.md or chart text
print("\n".join(F))
