# Member 2 — Monitoring & Data Pipeline Module

## Files
- `resource_monitor.py`   → Main module (VM CPU, memory, queue, delay)
- `openflow_stats.py`     → Network link stats (plugs into Member 1's Ryu)
- `integration_example.py`→ Shows teammates how to use your module
- `test_monitor.py`       → Run this to verify everything works

## Quick Start (no Mininet needed)
```bash
python3 test_monitor.py
```

## With Real Mininet
```python
from resource_monitor import ResourceMonitor
# After net.start():
monitor = ResourceMonitor(hosts=net.hosts, simulated=False)
stats = monitor.get_all_vm_stats()
```

## Data Contract (share with all teammates)
```python
vm_stats = {
    'vm_id':        int,    # 0, 1, 2, 3
    'cpu':          float,  # 0.0–1.0
    'memory':       float,  # 0.0–1.0
    'queue_length': int,    # tasks waiting
    'delay':        float,  # milliseconds
    'timestamp':    float   # Unix time
}
```

## Key Methods
| Method | Who calls it |
|--------|-------------|
| `get_all_vm_stats()` | Member 3 (AVRO scheduler) |
| `task_assigned(vm_id)` | Member 3 after scheduling |
| `task_completed(vm_id)` | Member 1 after flow completes |
| `save_to_csv()` | Member 4 (Evaluation) |
| `update_port_stats(...)` | Member 1's Ryu handler |
