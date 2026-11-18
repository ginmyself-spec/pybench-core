#!/usr/bin/env python3
"""
PyBench-Pro Core Engine v1.1 (Global i18n Edition)
Features / 特性:
1. Producer-Consumer Dual-Thread Decoupling / 雙執行緒防掉包解耦
2. Auto-Rollover & Disk Quota Guard / 自動分檔與磁碟配額守衛
3. Auto OS Language Detection (EN / ZH) / 自動偵測作業系統預設語言切換中英文輸出
"""
import os
import sys
import csv
import time
import queue
import locale
import threading
from datetime import datetime
from pathlib import Path


def detect_os_lang() -> str:
    """
    Auto-detect OS default language.
    Returns 'zh' if OS is Traditional/Simplified Chinese, otherwise defaults to 'en' for global users.
    Can also be forced via environment variable: PYBENCH_LANG=en or PYBENCH_LANG=zh
    """
    env_override = os.getenv("PYBENCH_LANG", "").strip().lower()
    if env_override in ("en", "zh"):
        return env_override

    if sys.platform == "win32":
        try:
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            # Primary language 0x04 = Chinese (0x0404 zh-TW, 0x0804 zh-CN, 0x0C04 zh-HK)
            if (lang_id & 0xFF) == 0x04:
                return "zh"
            return "en"
        except Exception:
            pass

    try:
        loc = os.getenv("LANG", "") or os.getenv("LC_ALL", "") or (locale.getlocale()[0] or "")
        if str(loc).lower().startswith("zh"):
            return "zh"
    except Exception:
        pass

    return "en"


CLI_I18N = {
    "en": {
        "disk_clean": "[DiskGuard] Auto-purged oldest log file: {name}",
        "engine_start": "[Engine] Starting dual-thread high-speed stress test (Duration: {sec}s)...",
        "report_done": "[Report] Test Complete! Total Samples: {seq:,} | Dropped Packets: {drops:,}",
        "report_path": "[Report] CSV logs safely written to: {path}",
    },
    "zh": {
        "disk_clean": "[DiskGuard] 自動清理最舊歷史檔案: {name}",
        "engine_start": "[Engine] 啟動雙執行緒高速壓測引擎 (預計執行 {sec} 秒)...",
        "report_done": "[Report] 測試完成！總採集筆數: {seq:,} | 掉包數: {drops:,}",
        "report_path": "[Report] 測試檔案已安全寫入至: {path}",
    }
}

CURRENT_LANG = detect_os_lang()


def _t(key: str, **kwargs) -> str:
    lang_dict = CLI_I18N.get(CURRENT_LANG, CLI_I18N["en"])
    return lang_dict.get(key, key).format(**kwargs)


class DiskQuotaLogger:
    def __init__(self, log_dir="./logs", max_file_mb=10, max_total_mb=500):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_bytes = max_file_mb * 1024 * 1024
        self.max_total_bytes = max_total_mb * 1024 * 1024
        self.current_file = None
        self.csv_writer = None
        self.file_handle = None
        self._rotate_file()

    def _enforce_quota(self):
        files = sorted(self.log_dir.glob("bench_*.csv"), key=os.path.getmtime)
        total_size = sum(f.stat().st_size for f in files)
        while total_size > self.max_total_bytes and len(files) > 1:
            oldest = files.pop(0)
            total_size -= oldest.stat().st_size
            oldest.unlink()
            print(_t("disk_clean", name=oldest.name))

    def _rotate_file(self):
        if self.file_handle:
            self.file_handle.close()
        self._enforce_quota()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        self.current_file = self.log_dir / f"bench_{timestamp}.csv"
        self.file_handle = open(self.current_file, mode="w", newline="", encoding="utf-8")
        self.csv_writer = csv.writer(self.file_handle)
        self.csv_writer.writerow(["Timestamp_ms", "Seq_ID", "Channel_0", "Channel_1", "Status"])

    def write_batch(self, batch_rows):
        if self.current_file.stat().st_size >= self.max_file_bytes:
            self._rotate_file()
        self.csv_writer.writerows(batch_rows)
        self.file_handle.flush()

    def close(self):
        if self.file_handle:
            self.file_handle.close()


class HighSpeedAcquisitionEngine:
    def __init__(self, sample_interval_sec=0.001, buffer_size=50000):
        self.sample_interval = sample_interval_sec
        self.data_queue = queue.Queue(maxsize=buffer_size)
        self.running = False
        self.dropped_packets = 0
        self.seq_id = 0
        self.logger = DiskQuotaLogger(max_file_mb=5, max_total_mb=100)

    def _hardware_read_hook(self):
        """
        [Custom Hardware Slot / 客製化插槽]
        Replace the 3 lines below with your Serial / SocketCAN / Modbus / DAQ SDK API call.
        只需替換下方 3 行代碼，即可接入真實硬體通訊或 DAQ API。
        """
        self.seq_id += 1
        ch0_val = round(3.30 + (self.seq_id % 10) * 0.01, 4)
        ch1_val = round(1.80 - (self.seq_id % 5) * 0.02, 4)
        status = "OK" if ch0_val < 3.38 else "WARN_OVERVOLT"
        return [int(time.time() * 1000), self.seq_id, ch0_val, ch1_val, status]

    def _producer_loop(self):
        next_call = time.perf_counter()
        while self.running:
            sample = self._hardware_read_hook()
            try:
                self.data_queue.put_nowait(sample)
            except queue.Full:
                self.dropped_packets += 1
            
            next_call += self.sample_interval
            sleep_time = next_call - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _consumer_loop(self, batch_size=200):
        batch = []
        while self.running or not self.data_queue.empty():
            try:
                item = self.data_queue.get(timeout=0.1)
                batch.append(item)
                if len(batch) >= batch_size:
                    self.logger.write_batch(batch)
                    batch.clear()
            except queue.Empty:
                if batch:
                    self.logger.write_batch(batch)
                    batch.clear()

    def start(self, duration_sec=3):
        print(_t("engine_start", sec=duration_sec))
        self.running = True
        p_thread = threading.Thread(target=self._producer_loop, daemon=True)
        c_thread = threading.Thread(target=self._consumer_loop, daemon=True)
        
        p_thread.start()
        c_thread.start()
        
        time.sleep(duration_sec)
        self.running = False
        p_thread.join()
        c_thread.join()
        self.logger.close()
        
        print(_t("report_done", seq=self.seq_id, drops=self.dropped_packets))
        print(_t("report_path", path=self.logger.log_dir.resolve()))


if __name__ == "__main__":
    engine = HighSpeedAcquisitionEngine(sample_interval_sec=0.001)
    engine.start(duration_sec=3)
