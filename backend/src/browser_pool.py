import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial

logger = logging.getLogger(__name__)

MAX_CONCURRENT_BROWSERS = int(os.getenv("MAX_CONCURRENT_BROWSERS", "3"))

MAX_QUEUE_SIZE = 10


class BrowserPoolManager:
    def __init__(
        self,
        max_concurrent: int = MAX_CONCURRENT_BROWSERS,
        max_queue_size: int = MAX_QUEUE_SIZE,
    ):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.executor = ThreadPoolExecutor(
            max_workers=max_concurrent,
            thread_name_prefix="tiktok-scraper",
        )
        self.max_queue_size = max_queue_size
        self._waiting_count = 0
        self._lock = asyncio.Lock()

    async def run_scrape(self, scrape_func, *args, **kwargs):
        async with self._lock:
            if self._waiting_count >= self.max_queue_size:
                raise TooManyRequestsError(
                    f"มีคิวรอเกิน {self.max_queue_size} รายการ กรุณาลองใหม่ภายหลัง"
                )
            self._waiting_count += 1

        try:
            async with self.semaphore:
                logger.info(
                    "เริ่ม scrape (slot ที่ใช้อยู่: %d/%d)",
                    self.max_concurrent_in_use(),
                    self.semaphore._value + self.max_concurrent_in_use(),
                )
                loop = asyncio.get_event_loop()
                func = partial(scrape_func, *args, **kwargs)
                result = await loop.run_in_executor(self.executor, func)
                return result
        finally:
            async with self._lock:
                self._waiting_count -= 1

    def max_concurrent_in_use(self) -> int:
        return MAX_CONCURRENT_BROWSERS - self.semaphore._value

    def shutdown(self):
        self.executor.shutdown(wait=True)


class TooManyRequestsError(Exception):
    pass


pool_manager = BrowserPoolManager()