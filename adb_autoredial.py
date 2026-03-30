#!/usr/bin/env python3
"""
Auto-redial with human answer detection via ADB.

Repeatedly calls a number until a human answer is detected (call active beyond
ValidAfterSeconds threshold), or until MaxRetries is reached.

Cross-platform: Windows, Linux, macOS.
"""

import argparse
import io
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    # Enable ANSI escape sequences on Windows 10+
    os.system("")


def supports_unicode() -> bool:
    """Check if terminal likely supports Unicode."""
    if sys.platform == "win32":
        return os.environ.get("WT_SESSION") is not None  # Windows Terminal
    return True


BAR_FILL = "#" if not supports_unicode() else "█"
BAR_EMPTY = "-" if not supports_unicode() else "░"


def log(message: str, level: str = "INFO", log_file: str = "") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {message}"
    print(line)
    if log_file:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def progress_bar(elapsed: int, total: int, prefix: str = "") -> None:
    width = 30
    pct = min(100, int((elapsed / total) * 100))
    filled = int(width * elapsed / total)
    bar = BAR_FILL * filled + BAR_EMPTY * (width - filled)
    print(f"\r{prefix} [{bar}] {pct}% ({elapsed}s/{total}s)", end="", flush=True)


def clear_progress() -> None:
    print("\r" + " " * 80 + "\r", end="", flush=True)


def invoke_adb(arguments: str, dry_run: bool = False) -> str:
    if dry_run:
        log(f"[DRY-RUN] adb {arguments}", "DEBUG")
        return ""
    try:
        # Use shell=False for cross-platform compatibility
        # Split arguments properly, but handle "shell" command specially
        args_list = ["adb"] + arguments.split()

        result = subprocess.run(
            args_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10
        )
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        return stdout + stderr
    except subprocess.TimeoutExpired:
        return ""
    except FileNotFoundError:
        log("adb not found in PATH", "ERROR")
        sys.exit(1)
    except Exception as e:
        log(f"ADB error: {e}", "ERROR")
        return ""


def get_call_state(dry_run: bool = False, debug: bool = False) -> str:
    if dry_run:
        return "NONE"
    dump = invoke_adb("shell dumpsys telecom")
    if debug:
        # Print all STATE: lines for debugging
        for line in dump.splitlines():
            if "STATE" in line.upper():
                print(f"  [DEBUG] {line.strip()}")
    # Check both formats: "STATE: ACTIVE" and "state=ACTIVE"
    if "state=ACTIVE" in dump or "STATE: ACTIVE" in dump:
        return "ACTIVE"
    if "state=DIALING" in dump or "STATE: DIALING" in dump:
        return "DIALING"
    if "state=CONNECTING" in dump or "STATE: CONNECTING" in dump:
        return "DIALING"
    if "state=RINGING" in dump or "STATE: RINGING" in dump:
        return "RINGING"
    if "state=DISCONNECTED" in dump:
        return "NONE"
    return "NONE"


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    clear_progress()
    print("\nInterrupted by user. Hanging up...")
    invoke_adb("shell input keyevent KEYCODE_ENDCALL")
    sys.exit(130)


def main() -> None:
    # Set up signal handler for graceful exit
    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(
        description="Auto-redial with human answer detection via ADB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 0123456789
  %(prog)s 0123456789 -v 25 -m 10
  %(prog)s 0123456789 --dry-run
        """
    )
    parser.add_argument("number", help="Phone number to call")
    parser.add_argument(
        "-v", "--valid-after", type=int, default=20, dest="valid_after",
        help="Minimum call duration (seconds) to confirm human answer (default: 20)"
    )
    parser.add_argument(
        "-d", "--retry-delay", type=int, default=3, dest="retry_delay",
        help="Seconds to wait between attempts (default: 3)"
    )
    parser.add_argument(
        "-m", "--max-retries", type=int, default=0, dest="max_retries",
        help="Maximum attempts, 0 = unlimited (default: 0)"
    )
    parser.add_argument(
        "-t", "--timeout", type=int, default=60, dest="timeout_call",
        help="Seconds before unanswered call is terminated (default: 60)"
    )
    parser.add_argument(
        "-l", "--log-file", type=str, default="", dest="log_file",
        help="Path to log file (optional)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Simulate without placing real calls"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Show raw call state output from dumpsys"
    )

    args = parser.parse_args()

    log("========================================", log_file=args.log_file)
    log("Auto-redial starting", log_file=args.log_file)
    log(f"  Target number    : {args.number}", log_file=args.log_file)
    log(f"  Valid after      : {args.valid_after}s", log_file=args.log_file)
    log(f"  Call timeout     : {args.timeout_call}s", log_file=args.log_file)
    log(f"  Retry delay      : {args.retry_delay}s", log_file=args.log_file)
    log(f"  Max retries      : {'unlimited' if args.max_retries == 0 else args.max_retries}", log_file=args.log_file)
    log(f"  Log file         : {args.log_file or 'none'}", log_file=args.log_file)
    log(f"  Dry-run          : {args.dry_run}", log_file=args.log_file)
    log("========================================", log_file=args.log_file)

    attempt = 0

    while True:
        attempt += 1

        if args.max_retries > 0 and attempt > args.max_retries:
            log(f"Max retries ({args.max_retries}) reached. Exiting.", "WARN", args.log_file)
            sys.exit(1)

        attempt_label = f"{attempt} / {args.max_retries}" if args.max_retries > 0 else str(attempt)
        log(f"Attempt {attempt_label} -- dialing {args.number}", log_file=args.log_file)

        invoke_adb(f"shell am start -a android.intent.action.CALL -d tel:{args.number}", args.dry_run)

        start_time = time.time()
        answered = False

        while True:
            time.sleep(1)
            elapsed_sec = int(time.time() - start_time)
            state = get_call_state(args.dry_run, args.debug)

            if state == "ACTIVE":
                answered = True
            elif state == "DIALING":
                log(f"  Dialing... ({elapsed_sec}s)", "DEBUG", args.log_file)
            elif state == "RINGING":
                log(f"  Ringing... ({elapsed_sec}s)", "DEBUG", args.log_file)

            if answered:
                progress_bar(elapsed_sec, args.valid_after, "Call active")

            if answered and elapsed_sec >= args.valid_after:
                clear_progress()
                log(f"Human answer confirmed after {elapsed_sec}s. Call left active.", log_file=args.log_file)
                sys.exit(0)

            if state == "NONE" and elapsed_sec > 5:
                clear_progress()
                outcome = f"auto-attendant (hung up at {elapsed_sec}s)" if answered else "no answer / busy"
                log(f"Call ended -- {outcome}", "WARN", args.log_file)
                break

            if elapsed_sec >= args.timeout_call:
                clear_progress()
                log(f"Call timeout after {elapsed_sec}s -- hanging up", "WARN", args.log_file)
                invoke_adb("shell input keyevent KEYCODE_ENDCALL", args.dry_run)
                break

        invoke_adb("shell input keyevent KEYCODE_ENDCALL", args.dry_run)

        log(f"Waiting {args.retry_delay}s before next attempt", log_file=args.log_file)
        for i in range(1, args.retry_delay + 1):
            progress_bar(i, args.retry_delay, "Retry in")
            time.sleep(1)
        clear_progress()


if __name__ == "__main__":
    main()
