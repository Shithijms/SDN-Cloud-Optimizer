import os
import time

def get_host_cpu_usage(host_name):
    cpuacct_path = f'/sys/fs/cgroup/cpuacct/{host_name}/cpuacct.usage'
    try:
        with open(cpuacct_path, 'r') as f:
            total_time_ns = int(f.read().strip())
    except FileNotFoundError:
        return 0.0

    if not hasattr(get_host_cpu_usage, "last_times"):
        get_host_cpu_usage.last_times = {}

    last_total = get_host_cpu_usage.last_times.get(host_name, 0)
    get_host_cpu_usage.last_times[host_name] = total_time_ns

    if last_total == 0:
        return 0.0

    delta_ns = total_time_ns - last_total
    delta_seconds = float(delta_ns) / 1_000_000_000.0
    usage_percent = min(100.0, (delta_seconds * 100.0) / 1.0)

    get_host_cpu_usage.last_times[host_name] = total_time_ns

    return usage_percent

if __name__ == "__main__":
    hosts = ["h1", "h2", "h3", "h4"]
    print(f"Monitoring CPU usage for hosts: {hosts}\n")
    for host in hosts:
        cpu_percent = get_host_cpu_usage(host)
        print(f"{host:2} is using {cpu_percent:.1f}% CPU")
