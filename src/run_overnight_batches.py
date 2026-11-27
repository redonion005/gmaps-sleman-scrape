#!/usr/bin/env python3
"""
Overnight Batch Runner
Reads batch files and executes them via browser_exec.
Run this script - it will output browser_exec calls for the agent to execute.
"""

import json
from pathlib import Path

BATCH_DIR = Path(__file__).parent.parent / "data" / "overnight"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "overnight" / "results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_batch(batch_file):
    with open(batch_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_browser_exec_code(batch):
    """Generate browser_exec code for a batch"""
    tasks = batch['tasks']
    corridor_id = batch['corridor_id']
    road_name = batch['road_name']
    tier = batch['tier']
    point_id = batch['point_id']
    lat = batch['lat']
    lng = batch['lng']
    
    # Build the code
    code_lines = [
        f"# Batch: {corridor_id} - {road_name} - {point_id}",
        f"# {len(tasks)} queries at ({lat}, {lng})",
        "import urllib.parse",
        "import json",
        "import time",
        "",
        "all_results = []",
        ""
    ]
    
    for task in tasks:
        query = task['query']
        encoded = urllib.parse.quote(query)
        url = f"https://www.google.com/maps/search/{encoded}/@{lat},{lng},16z"
        
        code_lines.append(f"# Query: {query}")
        code_lines.append(f'goto_url("{url}")')
        code_lines.append("wait_for_load()")
        code_lines.append("time.sleep(2.5)")
        code_lines.append("")
        code_lines.append("prev = 0")
        code_lines.append("for _ in range(8):")
        code_lines.append('    js("var feed = document.querySelector(\'[role=feed]\'); if (feed) feed.scrollTop = feed.scrollHeight;")')
        code_lines.append("    time.sleep(1)")
        code_lines.append('    curr = js("document.querySelectorAll(\'[role=article]\').length")')
        code_lines.append("    if curr == prev:")
        code_lines.append("        break")
        code_lines.append("    prev = curr")
        code_lines.append("")
        code_lines.append("EXTRACT_JS = r\"\"\"")
        code_lines.append("(() => {")
        code_lines.append("    var articles = document.querySelectorAll('[role=article]');")
        code_lines.append("    var results = [];")
        code_lines.append("    for (var i = 0; i < articles.length; i++) {")
        code_lines.append("        var article = articles[i];")
        code_lines.append("        var link = article.querySelector('a.hfpxzc') || article.querySelector('a[href*=\"/maps/place/\"]');")
        code_lines.append("        var name = link ? (link.getAttribute('aria-label') || '') : '';")
        code_lines.append("        var href = link ? link.href : '';")
        code_lines.append("        var lat = null, lng = null;")
        code_lines.append("        if (href) {")
        code_lines.append("            var latMatch = href.match(/!3d(-?[\\\\d.]+)/);")
        code_lines.append("            var lngMatch = href.match(/!4d(-?[\\\\d.]+)/);")
        code_lines.append("            if (latMatch) lat = parseFloat(latMatch[1]);")
        code_lines.append("            if (lngMatch) lng = parseFloat(lngMatch[1]);")
        code_lines.append("        }")
        code_lines.append("        var text = article.textContent || '';")
        code_lines.append("        var ratingMatch = text.match(/(\\\\d+[,.]\\\\d)/);")
        code_lines.append("        var rating = ratingMatch ? ratingMatch[1] : '';")
        code_lines.append("        var cleanText = text;")
        code_lines.append("        if (name && text.indexOf(name) === 0) {")
        code_lines.append("            cleanText = text.substring(name.length);")
        code_lines.append("        }")
        code_lines.append("        results.push({name: name, rating: rating, lat: lat, lng: lng, raw_text: cleanText.substring(0, 300)});")
        code_lines.append("    }")
        code_lines.append("    return JSON.stringify(results);")
        code_lines.append("})()")
        code_lines.append("\"\"\"")
        code_lines.append("raw = js(EXTRACT_JS)")
        code_lines.append("businesses = json.loads(raw)")
        code_lines.append("")
        code_lines.append("for b in businesses:")
        code_lines.append("    if b.get('name') and b.get('lat') is not None and b.get('lng') is not None:")
        code_lines.append(f"        all_results.append({{")
        code_lines.append(f"            'name': b['name'],")
        code_lines.append(f"            'rating': b.get('rating', ''),")
        code_lines.append(f"            'lat': b['lat'],")
        code_lines.append(f"            'lng': b['lng'],")
        code_lines.append(f"            'raw_text': b.get('raw_text', ''),")
        code_lines.append(f"            'query': '{query}',")
        code_lines.append(f"            'corridor_id': '{corridor_id}',")
        code_lines.append(f"            'point_id': '{point_id}',")
        code_lines.append(f"            'road_name': '{road_name}',")
        code_lines.append(f"            'tier': '{tier}'")
        code_lines.append(f"        })")
        code_lines.append(f"    print(f\"{query}: {{len(businesses)}} results\")")
        code_lines.append("    time.sleep(2)")
        code_lines.append("")
    
    code_lines.append("# Save results")
    code_lines.append("output_file = f\"C:\\\\Users\\\\Eromo\\\\Downloads\\\\gmaps_sweep_browser\\\\data\\\\overnight\\\\results\\\\{corridor_id}_{point_id}.jsonl\"")
    code_lines.append("with open(output_file, 'w', encoding='utf-8') as f:")
    code_lines.append("    for r in all_results:")
    code_lines.append("        f.write(json.dumps(r, ensure_ascii=False) + '\\n')")
    code_lines.append(f"print(f\"Saved {{len(all_results)}} venues to {{output_file}}\")")
    
    return '\n'.join(code_lines)

def main():
    batch_files = sorted(BATCH_DIR.glob("batch_*.json"))
    print(f"Found {len(batch_files)} batch files")
    
    # Process in pairs (2 batches = 20 searches per session)
    for i in range(0, len(batch_files), 2):
        batch_pair = batch_files[i:i+2]
        
        combined_code = []
        combined_code.append("# Combined batch execution")
        combined_code.append("import urllib.parse")
        combined_code.append("import json")
        combined_code.append("import time")
        combined_code.append("")
        combined_code.append("all_results = []")
        combined_code.append("")
        
        for batch_file in batch_pair:
            batch = load_batch(batch_file)
            tasks = batch['tasks']
            corridor_id = batch['corridor_id']
            road_name = batch['road_name']
            tier = batch['tier']
            point_id = batch['point_id']
            lat = batch['lat']
            lng = batch['lng']
            
            combined_code.append(f"# === Batch: {corridor_id} - {road_name} - {point_id} ===")
            
            for task in tasks:
                query = task['query']
                encoded = urllib.parse.quote(query)
                url = f"https://www.google.com/maps/search/{encoded}/@{lat},{lng},16z"
                
                combined_code.append(f"# Query: {query}")
                combined_code.append(f'goto_url("{url}")')
                combined_code.append("wait_for_load()")
                combined_code.append("time.sleep(2.5)")
                combined_code.append("")
                combined_code.append("prev = 0")
                combined_code.append("for _ in range(8):")
                combined_code.append('    js("var feed = document.querySelector(\'[role=feed]\'); if (feed) feed.scrollTop = feed.scrollHeight;")')
                combined_code.append("    time.sleep(1)")
                combined_code.append('    curr = js("document.querySelectorAll(\'[role=article]\').length")')
                combined_code.append("    if curr == prev:")
                combined_code.append("        break")
                combined_code.append("    prev = curr")
                combined_code.append("")
                combined_code.append("EXTRACT_JS = r\"\"\"")
                combined_code.append("(() => {")
                combined_code.append("    var articles = document.querySelectorAll('[role=article]');")
                combined_code.append("    var results = [];")
                combined_code.append("    for (var i = 0; i < articles.length; i++) {")
                combined_code.append("        var article = articles[i];")
                combined_code.append("        var link = article.querySelector('a.hfpxzc') || article.querySelector('a[href*=\"/maps/place/\"]');")
                combined_code.append("        var name = link ? (link.getAttribute('aria-label') || '') : '';")
                combined_code.append("        var href = link ? link.href : '';")
                combined_code.append("        var lat = null, lng = null;")
                combined_code.append("        if (href) {")
                combined_code.append("            var latMatch = href.match(/!3d(-?[\\\\d.]+)/);")
                combined_code.append("            var lngMatch = href.match(/!4d(-?[\\\\d.]+)/);")
                combined_code.append("            if (latMatch) lat = parseFloat(latMatch[1]);")
                combined_code.append("            if (lngMatch) lng = parseFloat(lngMatch[1]);")
                combined_code.append("        }")
                combined_code.append("        var text = article.textContent || '';")
                combined_code.append("        var ratingMatch = text.match(/(\\\\d+[,.]\\\\d)/);")
                combined_code.append("        var rating = ratingMatch ? ratingMatch[1] : '';")
                combined_code.append("        var cleanText = text;")
                combined_code.append("        if (name && text.indexOf(name) === 0) {")
                combined_code.append("            cleanText = text.substring(name.length);")
                combined_code.append("        }")
                combined_code.append("        results.push({name: name, rating: rating, lat: lat, lng: lng, raw_text: cleanText.substring(0, 300)});")
                combined_code.append("    }")
                combined_code.append("    return JSON.stringify(results);")
                combined_code.append("})()")
                combined_code.append("\"\"\"")
                combined_code.append("raw = js(EXTRACT_JS)")
                combined_code.append("businesses = json.loads(raw)")
                combined_code.append("")
                combined_code.append("for b in businesses:")
                combined_code.append("    if b.get('name') and b.get('lat') is not None and b.get('lng') is not None:")
                combined_code.append("        all_results.append({")
                combined_code.append(f"            'name': b['name'],")
                combined_code.append(f"            'rating': b.get('rating', ''),")
                combined_code.append(f"            'lat': b['lat'],")
                combined_code.append(f"            'lng': b['lng'],")
                combined_code.append(f"            'raw_text': b.get('raw_text', ''),")
                combined_code.append(f"            'query': '{query}',")
                combined_code.append(f"            'corridor_id': '{corridor_id}',")
                combined_code.append(f"            'point_id': '{point_id}',")
                combined_code.append(f"            'road_name': '{road_name}',")
                combined_code.append(f"            'tier': '{tier}'")
                combined_code.append("        })")
                combined_code.append(f"    print(f\"{query}: {{len(businesses)}} results\")")
                combined_code.append("    time.sleep(2)")
                combined_code.append("")
        
        # Save combined results
        combined_code.append("# Save all results from this session")
        combined_code.append('output_file = f"C:\\\\Users\\\\Eromo\\\\Downloads\\\\gmaps_sweep_browser\\\\data\\\\overnight\\\\results\\\\session_{i//2+1:03d}.jsonl"')
        combined_code.append("with open(output_file, 'w', encoding='utf-8') as f:")
        combined_code.append("    for r in all_results:")
        combined_code.append("        f.write(json.dumps(r, ensure_ascii=False) + '\\n')")
        combined_code.append('print(f"Session {i//2+1}: Saved {len(all_results)} venues to {output_file}")')
        
        code = '\n'.join(combined_code)
        
        # Save code to file for reference
        code_file = BATCH_DIR / f"session_{i//2+1:03d}_code.py"
        with open(code_file, 'w', encoding='utf-8') as f:
            f.write(code)
        
        print(f"\nSession {i//2+1}: {len(batch_pair)} batches ({sum(len(load_batch(f)['tasks']) for f in batch_pair)} searches)")
        print(f"Code saved to {code_file}")
        print(f"Run with: browser_exec(session='overnight_{i//2+1}', timeout_s=300)")
        print("---")
    
    print(f"\nTotal sessions needed: {(len(batch_files) + 1) // 2}")

if __name__ == '__main__':
    main()