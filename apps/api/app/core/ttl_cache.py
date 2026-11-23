# 거의 바뀌지 않는 조회 결과(교육 기수·강좌 분류·센터 연락처)를 짧게 쥐는 프로세스 안 TTL 캐시(ADR-114)
import threading
import time
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

T = TypeVar("T")
MAX_ENTRIES = 256  # 키는 (종류, 묶음, 날짜) 정도라 이 값을 넘지 않는다. 넘으면 비운다
_MISSING: Any = object()


class TtlCache:
    """유효 시간이 지나면 다시 읽는다. 0이면 꺼져 있어 늘 읽는다.

    프로세스마다 따로 가지므로 값을 바꿔도 다른 프로세스는 유효 시간이 지나야 새 값을 본다.
    그래서 쓰기 경로나 판정(신청 가능 여부 등)에는 쓰지 않고 주민 화면의 읽기에만 쓴다.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._ttl = 0.0
        self._lock = threading.Lock()
        self._items: dict[Hashable, tuple[float, Any]] = {}

    def configure(self, ttl_seconds: float) -> None:
        with self._lock:
            self._ttl = max(0.0, float(ttl_seconds))
            self._items.clear()

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def get_or_load(self, key: Hashable, loader: Callable[[], T]) -> T:
        if self._ttl <= 0:
            return loader()
        now = self._clock()
        with self._lock:
            found = self._items.get(key, _MISSING)
        if found is not _MISSING and now < found[0]:
            value: T = found[1]
            return value
        value = loader()  # 읽는 동안 잠금을 쥐지 않는다. 겹쳐 읽어도 결과는 같다. 실패는 담지 않는다
        with self._lock:
            if len(self._items) >= MAX_ENTRIES:
                self._items.clear()
            self._items[key] = (now + self._ttl, value)
        return value


CACHE = TtlCache()
