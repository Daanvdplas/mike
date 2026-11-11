"""Run one owned model job with conservative macOS memory budgets."""

import argparse
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import time

MAX_RSS_KIB = 1536 * 1024
MAX_SWAP_GROWTH_MIB = 128


def command_timeout_limit(command, serve_preview=False):
    if not command:
        raise ValueError("Supply a command")
    if not serve_preview:
        return 600
    binary = command[0]
    if (len(command) != 2 or command[1] != "serve"
            or Path(binary).name != "texas-case-finder" or not os.path.dirname(binary)):
        raise ValueError("--serve-preview requires a direct backend path followed only by serve")
    return 7200


def violation(sample, baseline_swap_mib, elapsed, timeout):
    if sample["rss_kib"] >= MAX_RSS_KIB:
        return "rss_limit"
    if sample["pressure_level"] != 1:
        return "system_memory_pressure"
    if sample["swap_used_mib"] - baseline_swap_mib >= MAX_SWAP_GROWTH_MIB:
        return "swap_growth"
    if elapsed >= timeout:
        return "timeout"
    return None


def system_metrics():
    pressure = int(subprocess.check_output(
        ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], text=True, timeout=3
    ).strip())
    swap = subprocess.check_output(["sysctl", "-n", "vm.swapusage"], text=True, timeout=3)
    match = re.search(r"used\s*=\s*([0-9.]+)([KMG])", swap)
    if not match:
        raise ValueError("Cannot read swap usage")
    scale = {"K": 1 / 1024, "M": 1, "G": 1024}[match[2]]
    return {"pressure_level": pressure, "swap_used_mib": float(match[1]) * scale}


def owned_processes(pgid):
    output = subprocess.check_output(["ps", "-axo", "pid=,pgid=,rss="], text=True, timeout=3)
    rows = []
    for line in output.splitlines():
        pid, group, rss = map(int, line.split())
        if group == pgid:
            rows.append({"pid": pid, "rss_kib": rss})
    return rows


def stop_owned_group(child):
    # This group was created by this guard; never signal unrelated processes.
    pgid = child.pid
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            child.poll()
            try:
                if not owned_processes(pgid):
                    return
            except (OSError, ValueError, subprocess.SubprocessError):
                break
            time.sleep(0.1)


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180)
    parser.add_argument("--serve-preview", action="store_true",
                        help="Allow up to 7200 seconds only for a direct backend serve command")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        limit = command_timeout_limit(command, args.serve_preview)
    except ValueError as error:
        parser.error(str(error))
    if not 0 < args.timeout_seconds <= limit:
        parser.error(f"Supply a timeout in (0, {limit}] seconds")
    return args, command


def main():
    args, command = parse_arguments()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    report = {"label": args.label, "rss_limit_mib": MAX_RSS_KIB / 1024,
              "swap_growth_limit_mib": MAX_SWAP_GROWTH_MIB, "interval_seconds": 1,
              "timeout_seconds": args.timeout_seconds, "serve_preview": args.serve_preview,
              "samples": []}
    child = None
    reason = None
    interrupted = False
    start = time.monotonic()

    def request_stop(_signal, _frame):
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        baseline = system_metrics()
        report["baseline"] = baseline
        if baseline["pressure_level"] != 1:
            raise ValueError("Preflight: system memory pressure is not normal")
        with args.log.open("w") as log:
            child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            report["owned_pgid"] = child.pid
            last_update = -10
            while child.poll() is None:
                sample = system_metrics()
                sample["processes"] = owned_processes(child.pid)
                sample["rss_kib"] = sum(p["rss_kib"] for p in sample["processes"])
                sample["elapsed_seconds"] = round(time.monotonic() - start, 3)
                report["samples"].append(sample)
                reason = "interrupted" if interrupted else violation(
                    sample, baseline["swap_used_mib"], sample["elapsed_seconds"], args.timeout_seconds
                )
                if reason:
                    stop_owned_group(child)
                    break
                if sample["elapsed_seconds"] - last_update >= 10:
                    print(f"{args.label}: {sample['elapsed_seconds']:.0f}s RSS={sample['rss_kib']/1024:.1f}MiB pressure={sample['pressure_level']} swap_delta={sample['swap_used_mib']-baseline['swap_used_mib']:.1f}MiB", flush=True)
                    last_update = sample["elapsed_seconds"]
                time.sleep(1)
            child.wait()
            report["exit_code"] = child.returncode
            # ru_maxrss captures short-lived peaks between one-second samples too.
            peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            report["child_peak_rss_mib"] = peak / (1024 * 1024 if sys.platform == "darwin" else 1024)
            if report["child_peak_rss_mib"] >= MAX_RSS_KIB / 1024:
                reason = reason or "rss_limit"
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        reason = "metrics_or_launch_error"
        report["error"] = str(error)
    finally:
        if child is not None:
            stop_owned_group(child)
            child.wait()
        report["reason"] = reason
        report["duration_seconds"] = round(time.monotonic() - start, 3)
        report["peak_group_rss_mib"] = max((s["rss_kib"] for s in report["samples"]), default=0) / 1024
        report["status"] = "passed" if reason is None and report.get("exit_code") == 0 else "stopped_or_failed"
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({key: value for key, value in report.items() if key != "samples"}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
