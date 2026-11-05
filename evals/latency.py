"""Voice latency from ORION's own log. Run: python -m evals.latency [path/to/orion.log]

Each spoken turn logs "Latency stt_ms=... think_ms=... total_ms=...". This prints
the median and 90th percentile of each, so a change can be judged by numbers.
Target: total under 1500 ms on a cloud backend.
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

_LINE = re.compile(r"Latency stt_ms=(\d+) think_ms=(\d+) total_ms=(\d+)")


def read(path: Path) -> dict[str, list[float]]:
    found: dict[str, list[float]] = {"stt_ms": [], "think_ms": [], "total_ms": []}
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _LINE.search(line)
        if match:
            for key, value in zip(found, match.groups()):
                found[key].append(float(value))
    return found


def summary(samples: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    report = {}
    for key, values in samples.items():
        if not values:
            continue
        ordered = sorted(values)
        p90 = ordered[min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))]
        report[key] = {"turns": len(values), "p50": statistics.median(values), "p90": p90}
    return report


def main() -> None:
    from app.paths import logs_dir

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else logs_dir() / "orion.log"
    report = summary(read(path))
    if not report:
        print(f"No spoken turns with timings in {path} yet.")
        return
    for key, values in report.items():
        print(f"{key:9} turns={values['turns']:<4} p50={values['p50']:.0f} ms  p90={values['p90']:.0f} ms")


if __name__ == "__main__":
    main()
