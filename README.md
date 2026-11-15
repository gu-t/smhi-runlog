# smhi-runlog

Logs, for 48 hours, how often SMHI's SNOW1g point forecast gets a new `createdTime` and whether the
contents actually change, for three points (central Uppsala, countryside in Skåne and Norrbotten).
Used to decide how Grafväder should cache SMHI's forecast.

- `checks.csv`: every check (about every 10 minutes) with the `createdTime`/`referenceTime` SMHI reported.
- `runs.csv`: every new `createdTime` per point: `first`, `identical` or `changed` (changed time steps and the
  largest differences for some parameters).
- `runs/<point>/`: the forecast (gzip), saved only when it changed.

The workflow disables itself after 48 hours. Data: SMHI, CC BY 4.0.
