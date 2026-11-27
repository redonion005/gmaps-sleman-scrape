#!/usr/bin/env python3
"""
Run browser_exec scraper for pilot batches
"""

import json
import sys
from pathlib import Path

# Load a batch and run via browser_exec
def run_batch_via_browser_exec(batch_num, batch_dir, output_dir):
    batch_file = batch_dir / f"batch_{batch_num:04d}.jsonl"
    output_file = output_dir / f"results_{batch_num:04d}.jsonl"
    
    if not batch_file.exists():
        return False, "Batch file not found"
    
    # Read the browser_exec code
    scraper_code_path = Path(__file__).parent / "gmaps_browser_exec.py"
    with open(scraper_code_path, 'r') as f:
        code = f.read()
    
    # Extract the SCRAPE_CODE string
    import re
    match = re.search(r'SCRAPE_CODE = \'\'\'(.*?)\'\'\'', code, re.DOTALL)
    if not match:
        return False, "Could not extract SCRAPE_CODE"
    
    scrape_code = match.group(1)
    
    # Replace placeholders
    scrape_code = scrape_code.replace('{{BATCH_FILE}}', str(batch_file))
    scrape_code = scrape_code.replace('{{OUTPUT_FILE}}', str(output_file))
    
    # This would be passed to browser_exec tool
    # For now, return the code for manual execution
    return True, scrape_code


if __name__ == '__main__':
    batch_dir = Path(__file__).parent.parent / "data" / "pilot"
    output_dir = Path(__file__).parent.parent / "data" / "pilot" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Show first batch code for testing
    success, code = run_batch_via_browser_exec(1, batch_dir, output_dir)
    if success:
        print("Browser exec code for batch 1:")
        print(code[:2000] + "..." if len(code) > 2000 else code)
    else:
        print(f"Error: {code}")