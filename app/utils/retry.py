import time
from typing import Callable, Optional, Type, TypeVar, Tuple

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    *,
    retries: int = 3,
    backoff_seconds: float = 0.5,
    retry_on: Optional[Tuple[Type[BaseException], ...]] = (Exception,),
) -> T:
    """Run fn() with retries and exponential backoff. If retry_on is None, defaults to (Exception,).
    Why available: Used by indexer.embed_texts and other OpenAI calls to handle transient API failures without failing the request."""
    exc_types: Tuple[Type[BaseException], ...] = retry_on or (Exception,)

    last_err: Optional[BaseException] = None

    for attempt in range(retries + 1):
        try:
            return fn()
        except exc_types as e:
            last_err = e
            if attempt >= retries:
                raise
            sleep_s = backoff_seconds * (2 ** attempt)
            time.sleep(sleep_s)

    # Should be unreachable, but keeps type-checkers happy.
    assert last_err is not None
    raise last_err
