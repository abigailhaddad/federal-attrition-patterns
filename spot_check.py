# A second, independent computation of the headline numbers: OPM's raw files straight from data.opm.gov, read with
# pandas, sharing no code with extract.py or build.py. Compares each number with charts/facts.md.
# python3 spot_check.py  ->  checks/spot_check.md  (run after build.py; downloads about 120 MB)
import io, json, re, urllib.request
import pandas as pd
from pathlib import Path
from config import INAUG, ICE_FROM, NEW_HIRE_LOS, BAND_CUTS, YOUNG, ELIGIBLE_SURE, MAX_LOS

OPM = "https://data.opm.gov/api/v1/files"
PERM = {"10", "15", "30", "32", "35", "36", "38", "50", "67"}
CURRENT = {ds: {x["year"] + x["month"]: x["version"] for x in json.load(urllib.request.urlopen(f"{OPM}/{ds}?current=true"))}
           for ds in ("separations", "accessions", "employment")}


def opm(ds, ym, cols, perm=True):
    with urllib.request.urlopen(f"{OPM}/{ds}/{ym[:4]}/{ym[4:]}/{CURRENT[ds][ym]}/download", timeout=600) as r:
        df = pd.read_parquet(io.BytesIO(r.read()), columns=cols)
    df["count"] = df["count"].astype(int)
    return df[df.appointment_type_code.astype(str).isin(PERM)] if perm else df


def svc(df, day):
    """Years of service from the leave service date, measured at `day` (as build.py does; OPM's own field changed definition in 2026)."""
    return (day - pd.to_datetime(df.service_computation_date_leave, errors="coerce")).dt.days / 365.25


mid = lambda yyyymm: pd.to_datetime(yyyymm.astype(str) + "15", format="%Y%m%d", errors="coerce")


def months(a, b):
    return [str(p).replace("-", "") for p in pd.period_range(f"{a[:4]}-{a[4:]}", f"{b[:4]}-{b[4:]}", freq="M")]


facts = open("charts/facts.md").read()
newest = max(CURRENT["separations"])
label = lambda ym: pd.Timestamp(f"{ym[:4]}-{ym[4:]}-01").strftime("%B %Y")
Y, JAN, PY = INAUG[:4], label(INAUG), newest[:4]                 # the change year, its January, the partial year
PREV = f"{int(Y) - 1}01"                                         # read from a year earlier: actions can be filed ahead
OLD = f"{BAND_CUTS[1]}+ years"
SEP_COLS = ["agency_code", "agency_subelement_code", "occupational_series_code", "pay_plan_code", "separation_category_code",
            "drp_indicator", "appointment_type_code", "service_computation_date_leave", "personnel_action_effective_date_yyyymm", "count"]
ACC_COLS = ["age_bracket", "veteran_indicator", "education_level_bracket", "agency_subelement_code", "occupational_series_code", "pay_plan_code", "accession_category_code", "appointment_type_code",
            "service_computation_date_leave", "personnel_action_effective_date_yyyymm", "count"]
# Every separations file from the year before INAUG on: an action can be processed before its effective month (a retirement filed in December,
# effective in January) or after it.
sep = pd.concat([opm("separations", ym, SEP_COLS) for ym in months(PREV, newest)], ignore_index=True)
sep = sep[~sep.separation_category_code.isin(["SA", "SB"])].reset_index(drop=True)   # transfers to another agency are not departures
eff = sep.personnel_action_effective_date_yyyymm.astype(str)
los = svc(sep, mid(eff))
los = los.where(los < MAX_LOS)   # MAX_LOS+ years is a placeholder start date: counted as not reported, as in build.py
checks = []


def check(label, ours, pattern):
    m = re.search(pattern, facts)
    theirs = m.group(1) if m else "not found"
    checks.append((label, ours, theirs, ours == theirs))


y25 = sep[eff.str[:4] == Y]
check(f"Departures effective in {Y}, length of service reported (chart 3)", f"{y25[los.notna()]['count'].sum():,}", rf"- {Y}: ([\d,]+), ")
check(f"Departures effective in {Y}, all", f"{y25['count'].sum():,}", rf"With them, {Y} has ([\d,]+) departures")
irs_all = sep[(sep.agency_code == "TR") & (sep.occupational_series_code == "0592") & eff.between(INAUG, newest)]
check(f"IRS tax examiners who left, {JAN} on", f"{irs_all['count'].sum():,}", r"The same examples, .*?IRS tax examiners ([\d,]+) left")
irs = irs_all[eff.between(INAUG, f"{Y}12")]   # chart 2: the whole of Y
check(f"IRS tax examiners who left in {Y} (chart 2)", f"{irs['count'].sum():,}", rf"IRS tax examiners\*\* \([\d,]+ staff in {JAN}\): ([\d,]+) left")
check("... of them through DRP", f"{irs[irs.drp_indicator == 'Y']['count'].sum():,}", r"IRS tax examiners.*?deferred resignation \(drp\) [\d.]+% \(([\d,]+)\)")
att = sep[(sep.occupational_series_code == "0905") & (sep.separation_category_code == "SC")
          & eff.between(newest[:4] + "01", newest)]
check(f"Attorney quits, January-{label(newest)}", f"{att['count'].sum():,}", r"Attorney quits: ([\d,]+) people")
old = sep[(los >= BAND_CUTS[1]) & (sep.separation_category_code == "SC") & eff.between(newest[:4] + "01", newest)]
check(f"Quits by staff with {OLD}, {PY}*", f"{old['count'].sum():,}", rf"{re.escape(OLD)}, quit: {PY}\* [\d.]+ \(([\d,]+) people\)")

# ICE's new officers (chart 1): GL pay plan, series 1801/1811, hired ICE_FROM on with under NEW_HIRE_LOS years of service.
acc_all = pd.concat([opm("accessions", ym, ACC_COLS, perm=False) for ym in months(ICE_FROM, newest)], ignore_index=True)
acc = acc_all[acc_all.appointment_type_code.astype(str).isin(PERM)]
ice = lambda d: d[(d.agency_subelement_code == "HSBB") & (d.pay_plan_code == "GL") & d.occupational_series_code.isin(["1801", "1811"])]
hired = ice(acc)
hired = hired[hired.accession_category_code.isin(["AC", "AD", "AE"]) & (svc(hired, mid(hired.personnel_action_effective_date_yyyymm)) < NEW_HIRE_LOS)
              & (hired.personnel_action_effective_date_yyyymm.astype(str) >= ICE_FROM)]
gone = ice(sep)
g_eff = pd.PeriodIndex(gone.personnel_action_effective_date_yyyymm.astype(str), freq="M")
g_hire = g_eff - svc(gone, mid(gone.personnel_action_effective_date_yyyymm)).mul(12).round().fillna(10_000).astype(int).values
start = pd.Period(f"{ICE_FROM[:4]}-{ICE_FROM[4:]}", "M")
gone = gone[(g_eff >= start) & (g_hire >= start)]
check(f"ICE new officers hired since {label(ICE_FROM)}", f"{hired['count'].sum():,}", r"ICE deportation officers and criminal investigators\*\*: [\d,]+ of ([\d,]+) hired")
check("... of them who had left", f"{gone['count'].sum():,}", r"ICE deportation officers and criminal investigators\*\*: ([\d,]+) of")

emp_cols = ["appointment_type_code", "service_computation_date_leave", "age_bracket", "count"]
jan25, now = opm("employment", INAUG, emp_cols), opm("employment", newest, emp_cols)
check(f"Permanent staff, {JAN}", f"{jan25['count'].sum():,}", rf"Permanent staff: ([\d,]+) in {JAN}")
check(f"Permanent staff, {label(newest)}", f"{now['count'].sum():,}", rf"Permanent staff: [\d,]+ in {JAN}, ([\d,]+) in")
yrs25 = svc(jan25, pd.Timestamp(f"{INAUG[:4]}-{INAUG[4:]}-15"))
known = yrs25.notna() & (yrs25 < MAX_LOS)
check(f"{JAN} staff with a length of service (chart 4's denominators)", f"{jan25[known]['count'].sum():,}", rf"Denominators, .*?{INAUG[:4]} ([\d,]+)")

# Retirement-eligible staff (at least) in January of the partial year; prior-service and young new hires in the partial year.
jan_py = opm("employment", f"{PY}01", emp_cols)
yrs = svc(jan_py, pd.Timestamp(f"{PY}-01-15"))
yrs = yrs.where(yrs < MAX_LOS)
sure = pd.Series(False, index=jan_py.index)
for a, y in ELIGIBLE_SURE:
    sure |= (jan_py.age_bracket == a) & (yrs >= y)
check(f"Retirement-eligible staff (at least), January {PY}", f"{jan_py[sure]['count'].sum():,}", rf"; {PY} ([\d,]+)-[\d,]+ \(")
nh = acc[acc.accession_category_code.isin(["AC", "AD", "AE"]) & (acc.personnel_action_effective_date_yyyymm.astype(str).str[:4] == PY)]
nh_los = svc(nh, mid(nh.personnel_action_effective_date_yyyymm))
nh_los = nh_los.where(nh_los < MAX_LOS)
prior = nh[(nh_los >= NEW_HIRE_LOS) & (nh.veteran_indicator == "N")]
check(f"Non-veteran new hires with prior service, {PY}*", f"{prior['count'].sum():,}", rf"toward leave\): .*; {PY} ([\d,]+) \(")
known_age = nh[nh.age_bracket.notna() & (nh.age_bracket != "UNSPECIFIED")]
check(f"Share of permanent new hires under {int(YOUNG[-1].split('-')[1]) + 1}, {PY}*", f"{known_age[known_age.age_bracket.isin(YOUNG)]['count'].sum() / known_age['count'].sum():.1%}",
      rf"permanent appointments: .*; {PY} ([\d.]+%)")

known_edu = nh[~nh.education_level_bracket.isin(["NO DATA REPORTED"]) & nh.education_level_bracket.notna()]
degree = known_edu.education_level_bracket.isin(["BACHELORS DEGREE", "MASTERS OR PROFESSIONAL DEGREE", "DOCTORATE DEGREE"])
check(f"Share of permanent new hires with a bachelor's or more, all agencies, {PY}*", f"{known_edu[degree]['count'].sum() / known_edu['count'].sum():.1%}",
      rf"bachelor's or more with no agency left out: .*; {PY}\* ([\d.]+%)")

# Hiring in the partial year, permanent and every appointment type (the post's named groups): Treasury's tax staff are all at the IRS (TR93).
nh_all = acc_all[acc_all.accession_category_code.isin(["AC", "AD", "AE"]) & (acc_all.personnel_action_effective_date_yyyymm.astype(str).str[:4] == PY)]
tr = nh_all.agency_subelement_code.astype(str).str[:2] == "TR"
for name, series in (("IRS tax examiners", "0592"), ("IRS contact representatives", "0962")):
    g = nh_all[tr & (nh_all.occupational_series_code == series)]
    check(f"{name}, new hires {PY}*, permanent", f"{g[g.appointment_type_code.astype(str).isin(PERM)]['count'].sum():,}", rf"{name} \({series}\): .*?hires: permanent ([\d,]+) vs")
    check(f"{name}, new hires {PY}*, every appointment type", f"{g['count'].sum():,}", rf"{name} \({series}\): .*?every appointment type ([\d,]+) vs")
check(f"Treasury new hires {PY}*, every appointment type", f"{nh_all[tr]['count'].sum():,}", r"- Treasury: .*?every appointment type ([\d,]+) vs")

out = ["# Spot check: headline numbers recomputed from OPM's raw files", "",
       f"`spot_check.py` downloads OPM's current files from data.opm.gov and recomputes these with pandas, sharing no code with "
       f"extract.py or build.py. Files through {newest}.", "", "| Number | Recomputed | facts.md | Match |", "|---|---|---|---|"]
out += [f"| {l} | {a} | {b} | {'yes' if ok else '**NO**'} |" for l, a, b, ok in checks]
out += ["", f"{JAN} staff with no length of service reported: {jan25[~known]['count'].sum():,}."]
Path("checks").mkdir(exist_ok=True)
open("checks/spot_check.md", "w").write("\n".join(out) + "\n")
print("\n".join(out))
assert all(ok for *_, ok in checks)
