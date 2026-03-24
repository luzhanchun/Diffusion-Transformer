import argparse
import socket
import json
import threading
import time
from engine.listen_file import SequentialCSVConsumer

class StartSyn:
    def __init__(self, listen:SequentialCSVConsumer, args:argparse.Namespace):
        self.listen = listen
        self.Client_IP = args.c_ip
        self.Client_Port = args.c_port
        self.Server_IP = args.s_ip
        self.Server_PORT = args.s_port

    def work(self):
        print("***********************系 统 启 动**************************")
        self.listen.start()

    def client(self):
        # 给服务端留出准备时间，建议3~5秒
        delay_sec = 10
        start_time_ts = time.time() + delay_sec
        start_time_ms = int(start_time_ts * 1000)

        msg = {
            "type": "start",
            "start_time_ms": start_time_ms
        }
        print("[INFO] 发送系统启动命令······")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.Server_IP, self.Server_PORT))
            s.sendall(json.dumps(msg).encode("utf-8"))
            ack_data = s.recv(4096)
            if ack_data:
                print("[INFO] Received ack!")
            else:
                print("[WARN] Connection closed, no ack received.")
            # ack = json.loads(ack_data.decode("utf-8"))
            # print(f"[CLIENT] ack = {ack}")

        # print(f"[CLIENT] scheduled start_time_ms = {start_time_ms}")
        # print("[CLIENT] waiting for synchronized start...")
        print(f"[INFO] 系统将在{delay_sec}s之后启动!")
        self.wait_until_timestamp(start_time_ts)
        # actual_ms = int(time.time() * 1000)
        # print(f"[CLIENT] actual start ms = {actual_ms}, diff = {actual_ms - start_time_ms} ms")
        self.work()
    def server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.Server_IP, self.Server_PORT))
            s.listen(5)
            print(f"[INFO] 等待系统启动命令(listening on {self.Server_IP}:{self.Server_PORT})······")

            while True:
                conn, addr = s.accept()
                client_ip, client_port = addr
                if client_ip == self.Client_IP:
                    threading.Thread(target=self.handle, args=(conn, addr), daemon=True).start()

    def handle(self,conn, addr):
        print(f"[INFO] Connected! addr=: {addr}")
        print("[INFO] 系统将在10s之后启动!")
        try:
            # 从当前数据里读取一次数据
            data = conn.recv(4096)
            if not data:
                return
            # 把收到的字节流解码成 UTF-8 字符串，再解析成 JSON
            msg = json.loads(data.decode("utf-8"))
            if msg.get("type") != "start":
                print("[INFO] invalid message")
                return
            # 毫秒时间戳转成整数，然后换算成秒
            start_time_ms = int(msg["start_time_ms"])
            start_time_ts = start_time_ms / 1000.0

            ack = {
                "type": "ack",
                "server_recv_time_ms": int(time.time() * 1000)
            }
            conn.sendall(json.dumps(ack).encode("utf-8"))

            # print(f"[SERVER] receive start_time_ms = {start_time_ms}")
            # print(f"[SERVER] waiting for synchronized start...")
            self.wait_until_timestamp(start_time_ts)
            # actual_ms = int(time.time() * 1000)
            # print(f"[SERVER] actual start ms = {actual_ms}, diff = {actual_ms - start_time_ms} ms")
            self.work()

        except Exception as e:
            print(f"[SERVER] error: {e}")
        finally:
            conn.close()
    def wait_until_timestamp(self,target_ts: float):
        while True:
            now = time.time()
            remain = target_ts - now
            if remain <= 0:
                break

            if remain > 0.002:
                time.sleep(remain - 0.001)
            else:
                while time.time() < target_ts:
                    pass
                break
