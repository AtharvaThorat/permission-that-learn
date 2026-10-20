"""Bounded thread scheduling for independent native episodes and external services."""
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import threading
import time
from .artifacts import atomic
from .store import Index


def schedule(spec, resolved, directory, execute, *, retry_statuses=(), actors=None, cancel=None):
    cancel = cancel or threading.Event()
    index = Index(directory, spec.limits.lease_seconds)
    try:
        index.coordinate()
    except BaseException:
        index.close()
        raise
    selected = [j for j in resolved['jobs'] if actors is None or j['actor_profile'] in actors]
    if actors and set(actors) - spec.actors.keys():
        raise ValueError('Unknown selected actor phase')
    iterator = iter(selected)
    pending, running = deque(), {}
    counts, resources = Counter(), Counter()
    exhausted = False
    started = time.monotonic()
    phase = None
    executor = ThreadPoolExecutor(max_workers=spec.limits.global_episodes)
    try:
        while pending or running or not exhausted:
            if time.monotonic() - started >= spec.limits.run_seconds:
                cancel.set()
            index.heartbeat()
            while not exhausted and len(pending) < spec.limits.pending_queue and not cancel.is_set():
                try:
                    pending.append((next(iterator), time.monotonic()))
                except StopIteration:
                    exhausted = True
            admitted = False
            for job, queued in list(pending):
                actor = job['actor_profile']
                profile = spec.actors[actor]
                group = profile.resource_group
                if cancel.is_set() or len(running) >= spec.limits.global_episodes:
                    break
                if spec.limits.sequential_models and phase is not None and actor != phase and running:
                    continue
                if counts[actor] >= profile.max_concurrent_requests or resources[group] >= spec.limits.resource_groups[group]:
                    continue
                claimed = index.claim(job, retry_statuses)
                pending.remove((job, queued))
                if claimed is None:
                    continue
                phase = actor
                attempt, path = claimed
                counts[actor] += 1
                resources[group] += 1
                future = executor.submit(execute, job, attempt, path, time.monotonic() - queued, cancel)
                running[future] = (job, attempt, actor, group)
                admitted = True
            if running:
                finished, _ = wait(running, timeout=min(0.2, spec.limits.lease_seconds / 3), return_when=FIRST_COMPLETED)
                for future in finished:
                    job, attempt, actor, group = running.pop(future)
                    counts[actor] -= 1
                    resources[group] -= 1
                    # Unexpected worker exceptions leave an incomplete attempt;
                    # no success-returning placeholder or overwritten trace.
                    result = future.result()
                    index.publish(job, attempt, result)
            elif cancel.is_set():
                break
            elif not admitted and exhausted and not pending:
                break
    except KeyboardInterrupt:
        cancel.set()
        # Drain bounded in-flight episodes; they check cancellation at turn boundaries.
        while running:
            index.heartbeat()
            finished, _ = wait(running, timeout=0.2, return_when=FIRST_COMPLETED)
            for future in finished:
                job, attempt, _, _ = running.pop(future)
                index.publish(job, attempt, future.result())
    finally:
        cancel.set()
        executor.shutdown(wait=True, cancel_futures=True)
        atomic(directory / 'run-index.json', {'schema_version': 1, 'attempts': index.snapshot()})
        index.close()
