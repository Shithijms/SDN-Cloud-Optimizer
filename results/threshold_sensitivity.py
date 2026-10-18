# Save as results/threshold_sensitivity.py and run it
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.scheduler.avro import AVROScheduler
from src.scheduler.environment import CloudEnvironment
from src.scheduler.simulation import (generate_uniform_workload,
    generate_bursty_workload, generate_gravity_workload)

for threshold in [0.2, 0.3, 0.4]:
    fast_count = 0
    total = 0
    dq_scores = {'Uniform': [], 'Bursty': [], 'Gravity': []}

    for run in range(10):
        for wname, wfn in [
            ('Uniform', lambda: generate_uniform_workload(200)),
            ('Bursty',  lambda: generate_bursty_workload(200)),
            ('Gravity', lambda: generate_gravity_workload(200))
        ]:
            env = CloudEnvironment(num_vms=4, seed=run)
            sched = AVROScheduler(
                pop_size=10,
                max_iter=30,
                threshold=threshold,
            )
            result = env.run_experiment(wfn(), sched, wname)
            dq_scores[wname].append(result['decision_quality'])

    import numpy as np
    print(f"\nThreshold {threshold}:")
    for w in ['Uniform','Bursty','Gravity']:
        print(f"  {w}: DQ={np.mean(dq_scores[w]):.4f} ±{np.std(dq_scores[w]):.4f}")
