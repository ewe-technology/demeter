import re, json, csv
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter

NY, UTC = ZoneInfo('America/New_York'), ZoneInfo('UTC')
lo, hi = datetime(2021, 5, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)
rows = []

fomc = open('/tmp/macro/fomc.htm').read()
for d in sorted(set(re.findall(r'pressreleases/monetary(\d{8})a\.htm', fomc))):
    if d == '20250822':  # notation vote on Statement on Longer-Run Goals (10:00 ET), not a policy statement
        continue
    loc = datetime.strptime(d + ' 14:00', '%Y%m%d %H:%M').replace(tzinfo=NY)
    rows.append(('FOMC', loc.astimezone(UTC),
                 f'https://www.federalreserve.gov/newsevents/pressreleases/monetary{d}a.htm'))

for fn, (url, emb, _) in json.load(open('/tmp/macro/cpi_verify.json')).items():
    m = re.match(r'(\d+):(\d+) a\.m\. \(ET\) (?:\w+, )?(\w+ \d+, \d{4})$', emb)
    loc = datetime.strptime(f'{m.group(3)} {m.group(1)}:{m.group(2)}', '%B %d, %Y %H:%M').replace(tzinfo=NY)
    assert loc.strftime('%m%d%Y') == fn[4:12], fn
    rows.append(('CPI', loc.astimezone(UTC), url))

rows = sorted((r for r in rows if lo <= r[1] < hi), key=lambda r: (r[1], r[0]))
out = '/Users/dinohuang/Desktop/demeter-momentum/.claude/worktrees/goal-v642/samples/macro_events_utc.csv'
with open(out, 'w', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(['event', 'release_utc', 'source'])
    for e, t, s in rows:
        w.writerow([e, t.strftime('%Y-%m-%d %H:%M'), s])
print(len(rows), sorted(Counter((e, t.year) for e, t, _ in rows).items()))
print(Counter((e, t.strftime('%H:%M')) for e, t, _ in rows))
