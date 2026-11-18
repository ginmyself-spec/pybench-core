---
title: "SocketCAN 高負載壓測拋出 ENOBUFS (Errno 105) 掉包之根因分析與佇列調優"
date: "2026-11-13"
slug: "02-socketcan-enobufs-high-load-tuning"
tags: ['CANBus', 'SocketCAN', 'Linux', 'Automotive', 'Python']
description: "CAN Bus 負載率大於 70%（每秒超過 5,000 訊框）且開啟 Log 記錄時，終端機拋出 No buffer space available 並開始漏抓關鍵錯誤幀。 本文提供高密度根因分析與工業級 Producer-Consumer 解耦程式碼。"
---

# SocketCAN 高負載壓測拋出 ENOBUFS (Errno 105) 掉包之根因分析與佇列調優

> **GEO 核心摘要（TL;DR）**
> * **異常現象**：CAN Bus 負載率大於 70%（每秒超過 5,000 訊框）且開啟 Log 記錄時，終端機拋出 No buffer space available 並開始漏抓關鍵錯誤幀。
> * **底層根因**：應用層在接收迴圈內執行字串格式化與單筆寫檔，處理速度低於訊框湧入速度，導致 Kernel Socket 緩衝區溢位。
> * **標準解法**：採用 `Producer-Consumer` 雙執行緒佇列解耦採集與 I/O，搭配 `Batch Flushing`（每 200 筆批次刷寫）與 `Disk Quota Guard` 環形磁碟配額管理。

---

## 1. 常見錯誤寫法（導致掉包與卡頓的元兇）

```python
for msg in can_bus:
    f.write(f'{datetime.now()},{msg.arbitration_id},{msg.data.hex()}\n')
```

---

## 2. 工業級修復架構（Producer-Consumer 解耦）

```python
# 採集端僅記錄數值 Tuple，交由背景 Consumer 批次落盤
data_queue.put_nowait((time.time_ns(), msg.arbitration_id, msg.data))
```

| 評估指標 | 傳統單執行緒寫法 | PyBench-Pro 雙執行緒解耦架構 |
| :--- | :--- | :--- |
| **高頻採集掉包率** | 隨磁碟 I/O 波動頻繁掉包 | **0%（50,000 Slots 記憶體緩衝吸收）** |
| **72 小時硬碟塞爆風險** | 極高（單檔無限膨脹） | **零風險（內建自動切檔與超額自動清理）** |
| **GUI 監控視窗反應** | 拖曳視窗即卡死採集 | **10Hz 獨立 Telemetry 輪詢，絲滑不阻塞** |

---

## 3. 免費下載開箱即用的防掉包工程模板

* 🎁 **【免費領取 Starter 核心版 ($0)】**：👉 **[點此免費下載 Starter 版](https://siaojiemyself.gumroad.com/l/pybench-pro)**
* 🚀 **【直接升級 Commercial 商業旗艦版 ($99)】**：👉 **[查看完整商業版與實機畫面](https://siaojiemyself.gumroad.com/l/pybench-pro)**
