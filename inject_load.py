#!/usr/bin/env python3
import json
import time
import sys

def inject_load(scenario="balanced"):
    try:
        with open('/tmp/cloud_host_stats.json', 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # Default balanced (all ~10%)
    if scenario == "balanced":
        for h in ['h1','h2','h3','h4','h5','h6','h7','h8']:
            if h in data:
                data[h]['cpu'] = 10.0
    elif scenario == "one_overloaded":
        data['h1']['cpu'] = 95.0
        for h in ['h2','h3','h4']:
            data[h]['cpu'] = 10.0
    elif scenario == "two_overloaded":
        data['h1']['cpu'] = 95.0
        data['h2']['cpu'] = 90.0
        data['h3']['cpu'] = 10.0
        data['h4']['cpu'] = 10.0
    elif scenario == "gradual":
        data['h1']['cpu'] = 80.0
        data['h2']['cpu'] = 60.0
        data['h3']['cpu'] = 40.0
        data['h4']['cpu'] = 20.0
    elif scenario == "memory_pressure":
        data['h1']['cpu'] = 10.0
        data['h1']['mem'] = 95.0
        for h in ['h2','h3','h4']:
            data[h]['cpu'] = 10.0
            data[h]['mem'] = 50.0
    else:
        # custom: e.g., "h1=95,h2=80,h3=20,h4=10"
        pairs = scenario.split(',')
        for pair in pairs:
            h, val = pair.split('=')
            if h in data:
                data[h]['cpu'] = float(val)

    with open('/tmp/cloud_host_stats.json', 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Injected scenario: {scenario}")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        scenario = sys.argv[1]
    else:
        scenario = "balanced"
    inject_load(scenario)
    
    # If you want to keep overwriting, add --loop
    if '--loop' in sys.argv:
        while True:
            time.sleep(2)
            inject_load(scenario)
