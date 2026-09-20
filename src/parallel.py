"""
Run one function over many chips in parallel worker processes.

This laptop has 4 physical cores (8 threads). Each worker is limited to ONE BLAS/OpenMP thread,
otherwise 4 workers x several threads each would fight for the same cores and run slower. Workers
are started with 'spawn' (not fork) because forking after OpenMP has been used can deadlock.
"""

from concurrent.futures import ProcessPoolExecutor
from functools import partial
import multiprocessing as mp


def _init_worker():
    from threadpoolctl import threadpool_limits
    threadpool_limits(1)


def map_chips(fn, chip_ids, n_jobs=4, **kwargs):
    """
    [fn(chip_id, **kwargs) for chip_id in chip_ids], in the same order, using n_jobs processes.
    fn must be a top-level (picklable) function and kwargs must be picklable.
    n_jobs=1 runs serially in this process, which is what the tests compare against.
    """
    chip_ids = list(chip_ids)
    if n_jobs <= 1:
        return [fn(c, **kwargs) for c in chip_ids]
    with ProcessPoolExecutor(n_jobs, mp_context=mp.get_context("spawn"),
                             initializer=_init_worker) as pool:
        return list(pool.map(partial(fn, **kwargs), chip_ids, chunksize=2))


def stream_map(fn, items, n_jobs=4, chunksize=2, **kwargs):
    """
    Like map_chips but yields each result as soon as it (and all earlier ones) are ready, so a long
    run can log progress. Same worker rules: spawn, one thread per worker, picklable fn and kwargs.
    """
    items = list(items)
    if n_jobs <= 1:
        for item in items:
            yield fn(item, **kwargs)
        return
    with ProcessPoolExecutor(n_jobs, mp_context=mp.get_context("spawn"), initializer=_init_worker) as pool:
        yield from pool.map(partial(fn, **kwargs), items, chunksize=chunksize)
