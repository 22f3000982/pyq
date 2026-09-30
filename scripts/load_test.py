"""Small dependency-free concurrency smoke test for a running PYQ Studio service."""
import argparse
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_once(url, timeout):
    started = time.perf_counter()
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:
            response.read()
            return response.status, (time.perf_counter() - started) * 1000, None
    except HTTPError as error:
        return error.code, (time.perf_counter() - started) * 1000, str(error)
    except (URLError, TimeoutError, OSError) as error:
        return 0, (time.perf_counter() - started) * 1000, str(error)


def run(url, users, requests_per_user, timeout):
    total_requests = users * requests_per_user
    with ThreadPoolExecutor(max_workers=users) as pool:
        results = list(pool.map(lambda _: request_once(url, timeout), range(total_requests)))
    latencies = [latency for _, latency, _ in results]
    successful = sum(status == 200 for status, _, _ in results)
    failures = [(status, detail) for status, _, detail in results if status != 200]
    report = {
        "url": url,
        "users": users,
        "requests": total_requests,
        "successful": successful,
        "failed": len(failures),
        "min_ms": round(min(latencies), 2),
        "median_ms": round(statistics.median(latencies), 2),
        "p95_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2),
        "max_ms": round(max(latencies), 2),
    }
    print(report)
    if failures:
        print("first_failure:", failures[0])
    return 0 if not failures else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5000/healthz")
    parser.add_argument("--users", type=int, nargs="+", default=[50, 100, 150, 200])
    parser.add_argument("--requests-per-user", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    if any(value < 1 for value in (*args.users, args.requests_per_user)):
        parser.error("users and requests-per-user must be positive")
    exit_code = 0
    for users in args.users:
        exit_code = max(exit_code, run(args.url, users, args.requests_per_user, args.timeout))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
