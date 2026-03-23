import os
import re
import sys
import time
import threading
from pathlib import Path
import pandas as pd
from tqdm import tqdm
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from engine.traffic_generator import TrafficGenerator


FILE_PATTERN = re.compile(r"^data_(\d+)\.csv$")

# def is_file_stable(file_path: Path, interval: float = 0.2, checks: int = 3) -> bool:
#     """
#     判断文件是否已经写稳定。
#     连续 checks 次检查文件大小都不变，则认为文件已写完。
#     """
#     if not file_path.exists() or not file_path.is_file():
#         return False
#
#     try:
#         last_size = file_path.stat().st_size
#     except OSError:
#         return False
#
#     for _ in range(checks):
#         time.sleep(interval)
#         try:
#             current_size = file_path.stat().st_size
#         except OSError:
#             return False
#
#         if current_size != last_size:
#             return False
#
#         last_size = current_size
#
#     return True

class SequentialCSVConsumer:
    def __init__(
        self,
        generator: TrafficGenerator,
        folder_path: str,
        start_index: int = 1,
        count: int = 1000,
        # stable_interval: float = 0.2,
        # stable_checks: int = 3,
    ):
        self.generator = generator
        self.stop_event = threading.Event()
        #已经释放released_pkt个数据包
        self.released_pkt = 0
        self.count = count

        self.folder = Path(folder_path).resolve()
        self.next_index = start_index
        # self.stable_interval = stable_interval
        # self.stable_checks = stable_checks
        self.lock = threading.Lock()
        self.cv = threading.Condition(self.lock)
        self.stop_event = threading.Event()

        # 记录收到事件、值得尝试处理的编号
        self.ready_indices = set()

        # 避免多个线程同时处理
        self.processing = False

        if not self.folder.exists():
            raise FileNotFoundError(f"目录不存在: {self.folder}")
        if not self.folder.is_dir():
            raise NotADirectoryError(f"不是目录: {self.folder}")

    def loading(self):
        dots = ["", ".", "..", "...", "....", ".....", "......"]
        while not self.stop_event.is_set():
            for d in dots:
                if self.stop_event.is_set():
                    break
                sys.stdout.write(f"\r[WORK] 背景流量保存中{d}   ")
                sys.stdout.flush()
                time.sleep(0.5)

    def work(self, df: pd.DataFrame, file_path: Path):
        """
        这里写你的实际任务逻辑
        """
        print(f"[WORK] 正在处理 {file_path.name}, shape={df.shape}")
        # 删除第一列
        df.drop(df.columns[0], axis=1, inplace=True)
        data = df.values
        if self.count<0:
            count = data.shape[0]
        else:
            count = self.count
        pkt_len = data[:, 0]
        iat = data[:, 1]
        direction = data[:, 2]

        # 1. TCP握手
        self.generator.handshake_tcp()
        # 2. TLS 1.2 握手
        self.generator.handshake_tls_fake()

        pbar = tqdm(
            range(count),
            desc="[WORK] 背景流量释放中",
            leave=True,
            colour="green",
            ncols=150, #linux:150
            unit="pkt"
        )
        for idx in pbar:
            pbar.set_postfix_str(f"released packets: {idx+1+self.released_pkt}")
            self.generator.control_packet(pkt_len[idx], iat[idx], direction[idx])
        # 4. TCP挥手
        self.generator.teardown_tcp()
        self.released_pkt = self.released_pkt+count

        # self.stop_event.clear()
        # t = threading.Thread(target=self.loading)
        # t.start()
        # #保存后清除self.generator.packets[]
        # self.generator.save_pcap(os.path.join("OUTPUT", "pcap", "background_traffic.pcap"))
        # self.stop_event.set()
        # t.join()

    def _extract_index(self, path: Path):
        match = FILE_PATTERN.match(path.name)
        if match:
            return int(match.group(1))
        return None

    def notify_file_event(self, path_str: str):
        path = Path(path_str)
        index = self._extract_index(path)
        if index is None:
            return

        with self.cv:
            self.ready_indices.add(index)
            self.cv.notify_all()

    def try_process_in_order(self):
        """
        尝试从 next_index 开始，连续处理所有“已经可用且稳定”的文件。
        """
        while True:
            file_path = self.folder / f"data_{self.next_index}.csv"

            if not file_path.exists():
                return

            # if not is_file_stable(
            #     file_path,
            #     interval=self.stable_interval,
            #     checks=self.stable_checks
            # ):
            #     return

            try:
                df = pd.read_csv(file_path, header=0)
                print(f"[INFO] 已读取 {file_path.name}")
                self.work(df, file_path)
                self.next_index += 1
            except Exception as e:
                print(f"[ERROR] 处理 {file_path.name} 失败: {e}")
                return

    def processing_loop(self):
        """
        后台顺序处理线程：
        - 初始时尝试处理目录中已经存在的连续文件
        - 没有可处理文件时阻塞等待新事件
        - 一旦收到事件，再尝试继续顺序处理
        """
        waiting_logged = False
        while not self.stop_event.is_set():
            with self.cv:
                self.processing = True

            # 每次被唤醒后，尽可能往后连续处理
            old_index = self.next_index
            self.try_process_in_order()

            with self.cv:
                self.processing = False

                # 如果处理过新文件，说明已经脱离等待状态
                if self.next_index != old_index:
                    waiting_logged = False
                # 如果下一个文件已经被事件通知过，或者已经存在，继续下一轮，不阻塞
                next_file = self.folder / f"data_{self.next_index}.csv"
                if next_file.exists() or self.next_index in self.ready_indices:
                    self.ready_indices.discard(self.next_index)
                    continue
                # 只有真正进入等待状态时打印一次
                if not waiting_logged:
                    print("[INFO] 等待模型采样中······")
                    waiting_logged = True

                self.cv.wait(timeout=1.0)

    def start(self):
        handler = CSVEventHandler(self)
        observer = Observer()
        observer.schedule(handler, str(self.folder), recursive=False)

        process_thread = threading.Thread(target=self.processing_loop, daemon=True)

        # 先启动观察者和处理线程
        observer.start()
        process_thread.start()

        print(f"[INFO] 正在监听目录: {self.folder}")
        print(f"[INFO] 从 data_{self.next_index}.csv 开始按顺序处理")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:

            self.stop_event.clear()
            t = threading.Thread(target=self.loading)
            t.start()
            # 保存后清除self.generator.packets[]
            self.generator.save_pcap(os.path.join("OUTPUT", "pcap", "background_traffic.pcap"))
            self.stop_event.set()
            t.join()

            print("[INFO] 收到退出信号，正在停止...")
            #杀死子程序
            self.generator.kill_child()

            self.stop_event.set()
            with self.cv:
                self.cv.notify_all()
            observer.stop()
            observer.join()
            process_thread.join(timeout=2)


class CSVEventHandler(FileSystemEventHandler):
    def __init__(self, consumer: SequentialCSVConsumer):
        super().__init__()
        self.consumer = consumer

    def on_created(self, event):
        if not event.is_directory:
            self.consumer.notify_file_event(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.consumer.notify_file_event(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.consumer.notify_file_event(event.dest_path)


