# Builds the post as a Word file: python3 post.py DRAFT.md OUT.docx
# DRAFT.md is the post's text in Markdown, with a line {{chart N}} (or {{chart N title}}, which adds the headline, or
# {{chart N image}}, the image alone when the text carries its own headline and caption) wherever
# chart N goes. Each marker becomes the chart's description, its notes as a footnote and the image, all as build.py
# wrote them (charts/tables/charts.csv and charts/*.png), so the doc's charts change whenever the data does.
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CHARTS = pd.read_csv(HERE / "charts" / "tables" / "charts.csv", index_col=0)


def block(m):
    name = next(n for n in CHARTS.index if n.startswith(f"{m.group(1)}_"))
    c = CHARTS.loc[name]
    notes = re.sub(r"\s*Source: .*$", "", c.notes).replace("*", "").strip()   # the post names its source once, up top
    img = f"![]({HERE / 'charts' / name}.png){{width=6.5in}}"
    if m.group(2) == " image":   # the post supplies its own headline and caption
        return img
    head = f"**{c.headline}**\n\n" if m.group(2) else ""
    return f"{head}{c.description}^[{notes}]\n\n{img}"


src, out = sys.argv[1], sys.argv[2]
text = re.sub(r"^\{\{chart (\d+)( title| image)?\}\}$", block, Path(src).read_text(), flags=re.M)
left = re.findall(r"\{\{.*?\}\}", text)
assert not left, left   # every marker filled
subprocess.run(["pandoc", "-f", "markdown-auto_identifiers", "-o", out], input=text, text=True, check=True)
print(f"{out}: {len(re.findall(r'!\[\]', text))} charts")
