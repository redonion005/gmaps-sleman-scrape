#!/usr/bin/env python3
"""
Launcher - Runs all 4 chunks in parallel via subprocess
Usage: python launcher.py
"""

import subprocess
import sys
import os

BASE = r"C:\Users\Eromo\Downloads\gmaps_sweep_browser"

def check_requirements():
    """Check if browser-use is installed"""
    try:
        import browser_use
        print(f"browser-use: OK ({browser_use.__version__})")
    except ImportError:
        print("browser-use NOT installed")
        print("Run: pip install browser-use")
        return False

    # Check Chrome
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]
    for p in chrome_paths:
        if os.path.exists(p):
            print(f"Chrome found: {p}")
            return True
    print("Chrome NOT found in standard locations")
    return False

if __name__ == "__main__":
    if not check_requirements():
        sys.exit(1)

    print("Starting 4 parallel scrapers...")
    procs = []

    for i in range(4):
        script = os.path.join(BASE, f"scrape_chunk_{i}.py")
        # Each in its own console window
        proc = subprocess.Popen(
            [sys.executable, script],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            cwd=BASE
        )
        procs.append(proc)
        print(f"Launched chunk {i} (PID: {proc.pid})")

    print("\nAll 4 running. Press Ctrl+C to stop all.")
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\nStopping all...")
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait()
        print("Stopped.")

    print("All chunks complete.")