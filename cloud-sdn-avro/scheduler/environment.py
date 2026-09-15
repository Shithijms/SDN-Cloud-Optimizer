"""
environment.py
--------------
SDN Cloud simulation environment.

Connects all components:
- VMState instances (dynamic VM resources)
- Task workload generator
- AVRO and Round Robin schedulers
- Metrics collection

This is the simulation layer that Mininet will replace in Month 2.
The interface is designed to be identical — swapping in real
Mininet stats requires only changing get_vm_stats_list().
"""

import time
import numpy as np
from src.scheduler.vm_state    import VMState
from src.scheduler.avro        import AVROScheduler
from src.scheduler.round_robin import RoundRobinScheduler
from src.scheduler.fitness     import compute_fitness


class CloudEnvironment:

    def __init__(self,
                 num_vms:    int   = 4,
                 tick_size:  float = 0.5,
                 seed:       int   = None):
        """
        Parameters
        ----------
        num_vms   : int   — number of virtual machines
        tick_size : float — simulation time step
        seed      : int   — random seed for reproducibility
        """
        if seed is not None:
            np.random.seed(seed)

        self.num_vms   = num_vms
        self.tick_size = tick_size

        # Create VMs with different base characteristics
        # Simulates heterogeneous data center
        self.vms = [
            VMState(vm_id=0, cpu_cores=2, memory_gb=4.0,
                    base_delay=8.0),   # weak VM
            VMState(vm_id=1, cpu_cores=4, memory_gb=8.0,
                    base_delay=5.0),   # standard VM
            VMState(vm_id=2, cpu_cores=4, memory_gb=8.0,
                    base_delay=5.0),   # standard VM
            VMState(vm_id=3, cpu_cores=8, memory_gb=16.0,
                    base_delay=3.0),   # powerful VM
        ]

        # Metrics storage
        self.metrics = {
            'task_records':    [],   # per-task timing data
            'vm_load_history': {i: [] for i in range(num_vms)},
        }

    # ── Environment interface ────────────────────────────────────

    def get_vm_stats_list(self) -> list:
        """
        Get current stats for all VMs.

        This is the ONLY method that changes in Month 2.
        Instead of VMState.get_stats(), it will call
        Ryu controller's OpenFlow port stats API.
        """
        return [vm.get_stats() for vm in self.vms]

    def record_vm_loads(self, tick: int):
        """Record current load of all VMs for plotting"""
        for vm in self.vms:
            self.metrics['vm_load_history'][vm.vm_id].append({
                'tick':  tick,
                'cpu':   vm.cpu,
                'queue': vm.queue_length,
            })

    def tick(self):
        """Advance all VMs by one time step"""
        completed_tasks = []
        for vm in self.vms:
            completed = vm.tick(self.tick_size)
            completed_tasks.extend(completed)
        return completed_tasks

    # ── Experiment runner ────────────────────────────────────────

    def run_experiment(self,
                       tasks:         list,
                       scheduler,
                       experiment_name: str = "") -> dict:
        """
        Run a complete scheduling experiment.

        Parameters
        ----------
        tasks           : list — task dicts from simulation.py
        scheduler       : AVROScheduler or RoundRobinScheduler
        experiment_name : str — label for results

        Returns
        -------
        dict — complete metrics for this experiment
        """
        # Reset VM states
        for vm in self.vms:
            vm.active_tasks           = []
            vm.total_tasks_received   = 0
            vm.total_tasks_completed  = 0

        self.metrics = {
            'task_records':    [],
            'vm_load_history': {i: [] for i in range(self.num_vms)},
        }

        task_records    = []
        current_tick    = 0
        task_idx        = 0
        start_time      = time.time()
        fitness_history = []

        # Sort tasks by arrival time
        tasks = sorted(tasks, key=lambda t: t['arrival_time'])
        max_arrival = tasks[-1]['arrival_time'] if tasks else 0

        # Simulation loop
        while task_idx < len(tasks) or any(
                vm.queue_length > 0 for vm in self.vms):

            sim_time = current_tick * self.tick_size

            # Process all tasks that have arrived by sim_time
            while (task_idx < len(tasks) and
                   tasks[task_idx]['arrival_time'] <= sim_time):

                task = tasks[task_idx]

                # In the task assignment section, capture all VM fitnesses
                vm_stats      = self.get_vm_stats_list()
                all_fitnesses = [compute_fitness(vm) for vm in vm_stats]
                avg_available = np.mean(all_fitnesses)
                max_available = np.max(all_fitnesses)

                decision_start = time.time()
                selected_vm_id = scheduler.select_vm(vm_stats)
                decision_time  = (time.time() - decision_start) * 1000

                self.vms[selected_vm_id].assign_task(task)

                chosen_fitness = compute_fitness(vm_stats[selected_vm_id])

                # Decision quality: 1.0 = picked best, 0.0 = picked worst
                fitness_range = max_available - min(all_fitnesses)
                if fitness_range > 1e-6:
                    decision_quality = (chosen_fitness - min(all_fitnesses)) / fitness_range
                else:
                    decision_quality = 1.0  # all VMs equal, any choice is perfect

                fitness_history.append(chosen_fitness)

                task_records.append({
                    'task_id':          task['task_id'],
                    'profile':          task['profile'],
                    'arrival_time':     task['arrival_time'],
                    'selected_vm':      selected_vm_id,
                    'fitness':          chosen_fitness,
                    'decision_quality': decision_quality,  # ← new
                    'avg_available':    avg_available,     # ← new
                    'decision_ms':      decision_time,
                    'start_tick':       current_tick,
                    'end_tick':         None,
                })

                task_idx += 1

            # Record VM loads
            self.record_vm_loads(current_tick)

            # Advance simulation
            completed = self.tick()

            # Mark completed tasks
            for task_id in completed:
                for record in task_records:
                    if (record['task_id'] == task_id and
                            record['end_tick'] is None):
                        record['end_tick'] = current_tick
                        break

            current_tick += 1

            # Safety limit
            if current_tick > 10000:
                break

        wall_time = time.time() - start_time

        return self._compute_metrics(
            task_records, fitness_history,
            wall_time, experiment_name)

    # ── Metrics computation ──────────────────────────────────────

    def _compute_metrics(self,
                         task_records:    list,
                         fitness_history: list,
                         wall_time:       float,
                         name:            str) -> dict:
        """Compute all QoS metrics from experiment records"""

        completed = [r for r in task_records if r['end_tick']]
        n_total   = len(task_records)
        n_done    = len(completed)

        # Makespan — total time from first to last task completion
        if completed:
            makespan = (max(r['end_tick'] for r in completed) -
                        min(r['start_tick'] for r in task_records))
            makespan *= self.tick_size
        else:
            makespan = float('inf')

        # Response times
        response_times = [
            (r['end_tick'] - r['start_tick']) * self.tick_size
            for r in completed
        ]
        avg_response = np.mean(response_times) if response_times else 0

        # Throughput — tasks completed per time unit
        total_sim_time = makespan if makespan > 0 else 1
        throughput     = n_done / total_sim_time

        # VM distribution
        vm_dist = {i: 0 for i in range(self.num_vms)}
        for r in task_records:
            vm_dist[r['selected_vm']] += 1

        # Weighted load balance — accounts for VM capability
        # Strong VMs should receive more tasks (proportional to cores)
        vm_capacities  = [vm.cpu_cores for vm in self.vms]
        total_capacity = sum(vm_capacities)
        expected_dist  = [
            (c / total_capacity) * n_total
            for c in vm_capacities
        ]
        actual_dist    = [vm_dist[i] for i in range(self.num_vms)]

        # Weighted deviation — penalizes sending tasks to weak VMs
        weighted_dev = sum(
            abs(actual_dist[i] - expected_dist[i]) / (expected_dist[i] + 1)
            for i in range(self.num_vms)
        ) / self.num_vms

        # Simple std for reference
        dist_values  = list(vm_dist.values())
        load_balance_std = np.std(dist_values) / (
            np.mean(dist_values) + 1e-10)

        # Average fitness of decisions
        avg_fitness = np.mean(fitness_history) if fitness_history else 0

        # Decision speed
        avg_decision_ms = np.mean(
            [r['decision_ms'] for r in task_records]) if task_records else 0

        # Decision quality score [0.0, 1.0]
        # 1.0 = always picked best VM
        # 0.5 = picked randomly
        # Shows algorithm intelligence independent of absolute load
        decision_qualities = [
            r.get('decision_quality', 0) for r in task_records]
        avg_decision_quality = np.mean(decision_qualities) if decision_qualities else 0

        return {
            'name':             name,
            'n_tasks':          n_total,
            'n_completed':      n_done,
            'makespan':         round(makespan, 2),
            'avg_response':     round(avg_response, 4),
            'throughput':       round(throughput, 4),
            'avg_fitness':      round(avg_fitness, 4),
            'load_balance_std': round(load_balance_std, 4),
            'weighted_dev':     round(weighted_dev, 4),
            'decision_quality': round(avg_decision_quality, 4),
            'avg_decision_ms':  round(avg_decision_ms, 4),
            'vm_distribution':  vm_dist,
            'wall_time_s':      round(wall_time, 2),
        }
    
    