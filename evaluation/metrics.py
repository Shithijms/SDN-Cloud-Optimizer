def response_time(arrival, finish):
    return finish - arrival


def throughput(total_tasks, total_time):
    return total_tasks / total_time if total_time > 0 else 0


def makespan(finish_times):
    return max(finish_times) if finish_times else 0


def avg_delay(delays):
    return sum(delays) / len(delays) if delays else 0


def utilization(usages):
    return sum(usages) / len(usages) if usages else 0