import time
import random

def _rand_sleep(a: float = 0.25, b: float = 1.5) -> None:
    time.sleep(random.uniform(a, b))