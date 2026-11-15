# Logs how often SMHI's SNOW1g point forecast gets a new createdTime, and whether the contents
# actually change. Run every ~5 minutes by .github/workflows/runlog.yml, for 48 hours.
#
# Files:
#   checks.csv  - every check: when, and the createdTime/referenceTime SMHI reported.
#   runs.csv    - every new createdTime per point: changed/identical vs the point's previous
#                 forecast, the number of changed time steps, and the largest differences.
#   runs/<point>/<createdTime>.json.gz - the forecast, saved only when it changed.
#   state.json  - start time, last createdTime, the hash of each point's last forecast.
import csv, gzip, hashlib, json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

BASE = "https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1/"
POINTS = {
    "uppsala": (59.8586, 17.6389),     # Central Uppsala (Stora torget).
    "skane": (55.75, 13.60),           # Countryside in Skåne.
    "norrbotten": (67.00, 20.50),      # Countryside in Norrbotten.
}
DURATION = timedelta(hours=48)
KEYS = ["air_temperature", "wind_speed", "wind_speed_of_gust", "cloud_area_fraction",
        "precipitation_amount_mean", "probability_of_precipitation", "symbol_code", "visibility_in_air"]
ROOT = os.path.dirname(os.path.abspath(__file__))


def get(url):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return body
        except Exception as e:
            last = e
            time.sleep(5 * (attempt + 1))
    raise last


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def append_csv(name, header, row):
    path = os.path.join(ROOT, name)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerow(row)


def compare(old, new):
    """Changed time steps (in common) and the largest absolute difference per key."""
    a = {t["time"]: t["data"] for t in old}
    b = {t["time"]: t["data"] for t in new}
    common = [t for t in b if t in a]
    changed = 0
    maxd = {}
    for t in common:
        if a[t] != b[t]:
            changed += 1
        for k in KEYS:
            x, y = a[t].get(k), b[t].get(k)
            if x != y and isinstance(x, (int, float)) and isinstance(y, (int, float)):
                maxd[k] = max(maxd.get(k, 0), round(abs(x - y), 2))
    return changed, len(common), maxd


def main():
    state_path = os.path.join(ROOT, "state.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    now = now_utc()
    if "start" not in state:
        state["start"] = iso(now)
    start = datetime.strptime(state["start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if now - start > DURATION:
        print("DONE")   # The workflow disables itself when it sees this.
        return

    ct = json.loads(get(BASE + "createdtime.json"))
    created, reference = ct["createdTime"], ct["referenceTime"]
    append_csv("checks.csv", ["checked", "createdTime", "referenceTime"], [iso(now), created, reference])

    if created != state.get("lastCreatedTime"):
        hashes = state.setdefault("hashes", {})
        files = state.setdefault("files", {})
        for name, (lat, lon) in POINTS.items():
            fmt = lambda x: ("%.5f" % x).rstrip("0").rstrip(".")   # As the app: at most 5 decimals.
            url = BASE + "geotype/point/lon/{}/lat/{}/data.json".format(fmt(lon), fmt(lat))
            body = get(url)
            fc = json.loads(body)
            series = fc["timeSeries"]
            h = hashlib.sha256(json.dumps(series, sort_keys=True).encode()).hexdigest()
            if name not in hashes:
                status, changed, common, maxd = "first", "", "", {}
            elif h == hashes[name]:
                status, changed, common, maxd = "identical", 0, len(series), {}
            else:
                with gzip.open(os.path.join(ROOT, files[name]), "rt", encoding="utf-8") as f:
                    old = json.load(f)["timeSeries"]
                changed, common, maxd = compare(old, series)
                status = "changed"
            saved = ""
            if status != "identical":
                rel = os.path.join("runs", name, fc["createdTime"].replace(":", "") + ".json.gz")
                os.makedirs(os.path.dirname(os.path.join(ROOT, rel)), exist_ok=True)
                with gzip.open(os.path.join(ROOT, rel), "wb") as f:
                    f.write(body)
                files[name] = rel.replace("\\", "/")
                hashes[name] = h
                saved = files[name]
            append_csv("runs.csv",
                       ["checked", "point", "createdTime", "referenceTime", "status", "changedSteps", "commonSteps", "maxDiffs", "file"],
                       [iso(now), name, fc["createdTime"], fc["referenceTime"], status, changed, common,
                        json.dumps(maxd, sort_keys=True) if maxd else "", saved])
        state["lastCreatedTime"] = created

    with open(state_path, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
