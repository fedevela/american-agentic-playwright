#!/usr/bin/env python3
"""Wrapper to run trigger.py N times in sequence."""

import argparse
import subprocess
import sys

def main() -> int:
    parser = argparse.ArgumentParser(description="Run trigger.py N times")
    parser.add_argument("-n", "--count", type=int, default=5, help="Number of times to run")
    
    parsed, unknown = parser.parse_known_args()
    
    cmd = [sys.executable, "trigger.py"] + unknown
    
    for i in range(1, parsed.count + 1):
        print(f"\n{'='*80}")
        print(f"Executing trigger.py (Run {i}/{parsed.count})")
        print(f"Command: {' '.join(cmd)}")
        print(f"{'='*80}\n")
        
        result = subprocess.run(cmd)
        
        if result.returncode != 0:
            print(f"\n[!] Execution {i} failed with exit code {result.returncode}. Stopping sequence.")
            return result.returncode
            
        print(f"\n[+] Execution {i} completed successfully.")
        
    print(f"\nAll {parsed.count} executions completed successfully.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
