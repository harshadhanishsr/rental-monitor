class BreakerOpen(Exception):
    ...


class Breaker:
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.failures = 0

    @property
    def is_open(self) -> bool:
        return self.failures >= self.threshold

    def record_failure(self) -> None:
        self.failures += 1

    def record_success(self) -> None:
        self.failures = 0

    def check(self) -> None:
        if self.is_open:
            raise BreakerOpen()
