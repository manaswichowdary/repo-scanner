"""Time the deployed API.   python benchmark/bench_api.py https://YOUR-APP.up.railway.app

Each repo is scanned once cold (the API caches repeats for 10 minutes), so use repos
nobody has scanned in the last 10 minutes. Cached repeats are timed separately.
"""

import statistics
import sys
import time

import httpx

REPOS = ["pallets/flask", "psf/requests", "Textualize/rich", "encode/httpx",
         "pallets/click", "expressjs/express", "tj/commander.js", "gin-gonic/gin"]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    base = sys.argv[1].rstrip("/")
    with httpx.Client(timeout=60) as c:
        t = time.perf_counter()
        c.get(f"{base}/health")
        print(f"warm up (may include a cold start): {time.perf_counter() - t:.1f}s")
        cold, ok = [], 0
        for repo in REPOS:
            t = time.perf_counter()
            r = c.post(f"{base}/analyze", json={"repo_url": repo})
            dt = time.perf_counter() - t
            status = r.status_code
            print(f"{repo:22} {status} {dt:5.1f}s")
            if status == 200:
                ok += 1
                cold.append(dt)
        warm = []
        for repo in REPOS[:3]:
            t = time.perf_counter()
            c.post(f"{base}/analyze", json={"repo_url": repo})
            warm.append(time.perf_counter() - t)
    if cold:
        print(f"\ncold: {ok}/{len(REPOS)} ok, median {statistics.median(cold):.1f}s, "
              f"slowest {max(cold):.1f}s, {sum(1 for x in cold if x < 5)} under 5s")
    if warm:
        print(f"cached: median {statistics.median(warm):.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
