import json
import matplotlib.pyplot as plt

# Load results
with open("results/reports/results.json", "r") as f:
    data = json.load(f)

task_sizes = []
rr_times = []
pr_times = []

for entry in data:
    task_sizes.append(entry["tasks"])
    rr_times.append(entry["rr"])
    pr_times.append(entry["proposed"])

# Plot
plt.figure()
plt.plot(task_sizes, rr_times, marker='o', label="Round Robin")
plt.plot(task_sizes, pr_times, marker='s', label="Proposed Algorithm")

plt.xlabel("Number of Tasks")
plt.ylabel("Average Response Time")
plt.title("SDN Cloud Optimization Comparison")
plt.legend()

# Save graph
plt.savefig("results/reports/comparison.png")
plt.show()