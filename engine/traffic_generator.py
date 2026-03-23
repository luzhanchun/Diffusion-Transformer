import os
import signal
import time
import random
import subprocess
import sys
import platform
from pathlib import Path
from scapy.layers.inet import TCP, IP
from scapy.layers.tls.handshake import TLSClientKeyExchange, TLSServerKeyExchange, \
    TLSCertificate, TLSServerHello, TLSFinished, TLSServerHelloDone, TLSClientHello
from scapy.layers.tls.record import TLSChangeCipherSpec, TLS, TLSApplicationData
from scapy.main import load_layer
from scapy.sendrecv import send
from scapy.utils import wrpcap

load_layer("tls")
class TrafficGenerator:
    """
    流量生成器类：用于维护 TCP 连接状态并生成由客户端和服务器交互的 PCAP 包。
    """

    def __init__(self, args):
        """
        初始化流量生成器的基本网络五元组信息。
        """
        self.src_ip = args.c_ip
        self.dst_ip = args.s_ip
        self.sport = args.c_port
        self.dport = args.s_port
        self.host_type = args.host_type
        self.sample = args.sample
        self.cpu = args.cpu
        self.send = args.send
        # 维护 TCP 序列号 (Sequence Number) 和 确认号 (Ack Number)
        # 初始序列号随机化，模拟真实操作系统行为
        self.c_seq = random.randint(1000, 2000)  # 客户端 Seq
        self.s_seq = random.randint(2000, 3000)  # 服务器 Seq
        #print(self.c_seq, self.s_seq)
        # 维护时间戳，用于控制包的到达间隔特征
        self.current_timestamp = time.time()
        # 存储生成的包列表
        self.packets = []
        self.p = None
        self.system = platform.system()

    def stop_child(self, timeout=3):
        if self.p is None:
            return

        if self.p.poll() is not None:
            return

        self.p.terminate()  # 给子进程发终止信号

        try:
            self.p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.p.kill()  # 还不退就强杀
            self.p.wait()

    def stop_child_group(self, timeout: float = 3.0):
        if self.p is None:
            return
        if self.p.poll() is not None:
            return
        pgid = os.getpgid(self.p.pid)
        os.killpg(pgid, signal.SIGTERM)

        try:
            self.p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
            self.p.wait()

    def sampling(self,milestone=10,num_cycles=5,size_every=1000):
        name = "traffic_1"
        config_file = "Config/traffic.yaml"
        gpu = 0
        sample = 0
        base_dir = Path(__file__).resolve().parent.parent
        child_script = base_dir / "main.py"
        if self.system == "Windows":
            if self.cpu:
                self.p = subprocess.Popen([
                    "cmd", "/k",
                    sys.executable, str(child_script),
                    "--name", name,
                    "--config_file", config_file,
                    "--sample", str(sample),
                    "--milestone", str(milestone),
                    "--traffic",
                    "--num_cycles", str(num_cycles),
                    "--size_every", str(size_every),
                ],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                self.p = subprocess.Popen([
                    "cmd", "/k",
                    sys.executable, str(child_script),
                    "--name", name,
                    "--config_file", config_file,
                    "--gpu", str(gpu),
                    "--sample", str(sample),
                    "--milestone", str(milestone),
                    "--traffic",
                    "--num_cycles", str(num_cycles),
                    "--size_every", str(size_every),
                ],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            print("模型采样已启动！")
        elif self.system == "Linux":
            if self.cpu:
                self.p = subprocess.Popen(
                    [
                        sys.executable, str(child_script),
                        "--name", name,
                        "--config_file", config_file,
                        "--sample", str(sample),
                        "--milestone", str(milestone),
                        "--traffic",
                        "--num_cycles", str(num_cycles),
                        "--size_every", str(size_every),
                    ],
                    stdin=subprocess.DEVNULL,
                    # stdout=None,
                    # stderr=None,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid,
                )
            else:
                self.p = subprocess.Popen(
                    [
                        sys.executable, str(child_script),
                        "--name", name,
                        "--config_file", config_file,
                        "--gpu", str(gpu),
                        "--sample", str(sample),
                        "--milestone", str(milestone),
                        "--traffic",
                        "--num_cycles", str(num_cycles),
                        "--size_every", str(size_every),
                    ],
                    stdin=subprocess.DEVNULL,
                    # stdout=None,
                    # stderr=None,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid,
                )
            print("模型采样已启动！")
        else:
            raise NotImplementedError(f"暂不支持的系统: {self.system}")
    def _update_time(self, interval):
        """
        更新当前包的时间戳，模拟流量的时间特征。
        """
        interval = interval / 1000000
        self.current_timestamp += interval
    def save_pcap(self, filename):
        """
        将内存中的所有包写入 PCAP 文件。
        """
        # 注意：Raw(pkt) 可能会重新计算校验和，ensure Scapy builds binary properly
        if not self.packets:
            print("[INFO] 没有可写入的数据包")
            return
        # 确保目录存在
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        file_exists = os.path.isfile(filename)
        # append=True 表示追加写入，不覆盖原文件
        wrpcap(filename, self.packets, append=file_exists)
        print(f"\n[INFO] Completed! 背景流量已保存至: {filename} ")
        if self.sample:
            if self.system == "Linux":
                self.stop_child_group(3.0)
            elif self.system == "Windows":
                self.stop_child(3)
            print("[INFO] 模型采样已停止", flush=True)
        #self.packets.clear()

    def _get_tcp_layer(self, direction, flags, payload_len=0):
        """
        构造 TCP 层，自动计算正确的 Seq 和 Ack。
        :param direction: 'c2s' (Client->Server) 或 's2c' (Server->Client)
        :param flags: TCP 标志位 ('S', 'SA', 'A', 'PA', 'F' 等)
        :param payload_len: 当前包携带的数据长度，用于更新下一次的 Seq/Ack
        """
        if direction == 'c2s':
            # 客户端发给服务器
            # Seq 是客户端当前的发送进度，Ack 是服务器当前的发送进度
            t = TCP(sport=self.sport, dport=self.dport, flags=flags,
                    seq=self.c_seq, ack=self.s_seq, window=random.randint(12000, 30000))
            self.c_seq += payload_len  # 更新客户端序列号
        else:
            # 服务器发给客户端
            t = TCP(sport=self.dport, dport=self.sport, flags=flags,
                    seq=self.s_seq, ack=self.c_seq, window=random.randint(12000, 30000))
            self.s_seq += payload_len  # 更新服务器序列号

        return t
    def handshake_tcp(self):
        """
        TCP 三次握手。
        TCP(flags="S")      # SYN
        TCP(flags="SA")     # SYN + ACK
        TCP(flags="PA")     # PSH + ACK
        TCP(flags="FA")     # FIN + ACK
        TCP(flags="R")      # RST
        """
        #print("[*] Generating TCP 3-Way Handshake...")
        # 1. Client SYN
        # 客户端请求建立连接，Seq=X (不占数据 Payload，但消耗 1 个 seq)
        tcp_syn = self._get_tcp_layer('c2s', 'S', payload_len=1)
        self.build_packet('c2s', tcp_syn, iat=86)

        # 2. Server SYN/ACK
        # 服务器确认，Seq=Y, Ack=X+1
        tcp_synack = self._get_tcp_layer('s2c', 'SA', payload_len=1)
        self.build_packet('s2c', tcp_synack, iat=153)

        # 3. Client ACK
        # 客户端确认，Ack=Y+1
        tcp_ack = self._get_tcp_layer('c2s', 'A', payload_len=0)
        self.build_packet('c2s', tcp_ack, iat=65)
        #print("[*] TCP Handshake Completed.")

    def teardown_tcp(self):
        """
        模拟 TCP 四次挥手
        """
        # 1. Client FIN/ACK
        # 客户端主动关闭连接，发送 FIN，表示自己没有数据要发了
        # FIN 会消耗 1 个 seq
        tcp_fin_1 = self._get_tcp_layer('c2s', 'FA', payload_len=1)
        self.build_packet('c2s', tcp_fin_1, iat=86)

        # 2. Server ACK
        # 服务端确认收到客户端的 FIN
        # ACK 本身不消耗 seq
        tcp_ack_1 = self._get_tcp_layer('s2c', 'A', payload_len=0)
        self.build_packet('s2c', tcp_ack_1, iat=153)

        # 3. Server FIN/ACK
        # 服务端也发送 FIN，表示自己也没有数据要发了
        # FIN 会消耗 1 个 seq
        tcp_fin_2 = self._get_tcp_layer('s2c', 'FA', payload_len=1)
        self.build_packet('s2c', tcp_fin_2, iat=65)

        # 4. Client ACK
        # 客户端确认收到服务端的 FIN
        tcp_ack_2 = self._get_tcp_layer('c2s', 'A', payload_len=0)
        self.build_packet('c2s', tcp_ack_2, iat=72)
    def handshake_tls_fake(self):
        # --- 1. Client Hello ---
        # 构造 TLS Client Hello 消息
        tls_ch = TLS(msg=[TLSClientHello(version=0x0303, ciphers=[0xc02f])])
        # 封装 TCP (PSH, ACK)。注意计算 TLS 层的长度用于更新 seq
        tcp_layer = self._get_tcp_layer('c2s', 'PA', payload_len=len(tls_ch))
        self.build_packet('c2s', tcp_layer / tls_ch, iat=212)

        # 客户端发完数据后，服务器通常会回一个 TCP ACK (可选，视协议栈实现而定)
        # 这里为了简化，直接模拟服务器发送 ServerHello

        # --- 2. Server Hello + Certificate + ServerHelloDone ---
        # 模拟服务器将多个 TLS Record 放在一个 TCP 包中发送
        tls_sh = TLS(msg=[
            TLSServerHello(version=0x0303),
            # 这里简化处理，不放真实的几KB证书，只放一个空证书结构以欺骗解析器
            # 或者使用 TLS13Certificate() 如果是 1.3
        ])
        tcp_layer = self._get_tcp_layer('s2c', 'A', payload_len=len(tls_sh))
        self.build_packet('s2c', tcp_layer / tls_sh, iat=186)

        # --- 3. Client Key Exchange + Change Cipher Spec + Finished ---
        tls_cke = TLS(msg=[
            TLSCertificate(),
            TLSServerKeyExchange(),
            TLSServerHelloDone(),
            #TLSChangeCipherSpec(),
            TLSFinished()  # 此时开始，后续内容理论上是加密的
        ])
        tcp_layer = self._get_tcp_layer('c2s', 'PA', payload_len=len(tls_cke))
        self.build_packet('c2s', tcp_layer / tls_cke, iat=234)

        # --- 4. Server Change Cipher Spec + Finished ---
        tls_fin = TLS(msg=[
            TLSClientKeyExchange(),
            TLSChangeCipherSpec(),
            TLSFinished()
            #TLSEncryptedExtensions()
        ])
        tcp_layer = self._get_tcp_layer('s2c', 'PA', payload_len=len(tls_fin))
        self.build_packet('s2c', tcp_layer / tls_fin, iat=83)

        #print("[*] TLS Handshake Completed.")

    def build_packet(self, direction, layer_l4_l7, iat):
        """
        通用构建函数：组合 IP + TCP + (TLS/Data)，并设置时间戳。
        """
        self._update_time(iat)
        # 1. 构造 IP 层
        if direction == 'c2s':
            pkt = IP(src=self.src_ip, dst=self.dst_ip) / layer_l4_l7
        else:
            pkt = IP(src=self.dst_ip, dst=self.src_ip) / layer_l4_l7

        # 2. 设置 Scapy 包的时间戳 (用于 pcap 分析)
        pkt.time = self.current_timestamp
        time.sleep(iat/1000000)
        if self.send:
            if (direction == 'c2s') & (self.host_type == 'c'):
                send(pkt, verbose=False)  # 不打印发送信息
            if (direction == 's2c') & (self.host_type == 's'):
                send(pkt, verbose=False)  # 不打印发送信息
        #pkt.show()
        self.packets.append(pkt)

    def generate_encrypted_payload(self,length: int) -> bytes:
        """
        生成指定长度的随机字节串，用于模仿加密后的负载。
        Args:
            length: 负载长度，单位为字节，必须是非负整数。
        Returns:
            bytes: 长度为 length 的随机字节串。
        """
        if not isinstance(length, int):
            raise TypeError("length 必须是 int 类型")
        if length < 0:
            raise ValueError("length 必须是非负整数")
        encrypted_payload = os.urandom(length)
        return encrypted_payload
        #return bytes([0xAB])*length

    def control_packet(self, pkg_len, iat, direction):
        """
        模拟握手后的加密应用流量。
        这是控制流量特征（大小、间隔、方向）的核心函数。
        """
        #print(f"[*] Generating {count} Application Data packets...")
        # 1. 决定方向
        # 如果随机数 > prob (比如0.5)，则设为 c2s，否则 s2c
        if direction == -1:
            curr_dir = 'c2s'
        else:
            curr_dir = 's2c'

        # 2. 决定载荷大小 (流量特征核心)
        tcp_payload_len = pkg_len-20
        # 3. 构造 TCP 包
        tcp_layer = self._get_tcp_layer(curr_dir, 'A', payload_len=tcp_payload_len)
        #print(f"负载长度{tcp_payload_len}")
        if tcp_payload_len == 0:
            self.build_packet(curr_dir, tcp_layer, iat=iat)
        elif (tcp_payload_len > 0)&(tcp_payload_len <=40):
            encrypted_payload = self.generate_encrypted_payload(int(tcp_payload_len))
            self.build_packet(curr_dir, tcp_layer / encrypted_payload, iat=iat)
        elif (tcp_payload_len > 40) & (tcp_payload_len <= 1460):
            encrypted_payload = self.generate_encrypted_payload(int(tcp_payload_len)-5)
            tls_layer = TLS(msg=[TLSApplicationData(encrypted_payload)])
            self.build_packet(curr_dir, tcp_layer / tls_layer, iat=iat)
        else:
            raise Exception("数据包长度异常！程序终止！")

