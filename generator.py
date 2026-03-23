import os
import argparse

from engine.listen_file import SequentialCSVConsumer
from engine.start_syn import StartSyn
from engine.traffic_generator import TrafficGenerator



def parse_args():
    parser = argparse.ArgumentParser(description="Scapy custom TCP/TLS peer node")
    parser.add_argument('--iface', type=str, default=None, help='网卡名，例如 eth0 / ens33')
    parser.add_argument('--c_ip', type=str, default="192.168.159.1", help='客户端ip')
    parser.add_argument('--c_port', type=int, default=12345, help='客户端-端口')
    parser.add_argument('--s_ip', type=str, default="192.168.159.128", help='服务端ip')
    parser.add_argument('--s_port', type=int, default=443, help='服务端端口')
    parser.add_argument("--host_type", type=str, default="c", help='指示本机类型c/s')
    parser.add_argument('--sample', action='store_true', default=False, help='是否同时启动模型采样.')
    parser.add_argument('--cpu', action='store_true', default=False, help='是否在cpu上采样.')
    parser.add_argument('--send', action='store_true', default=False, help='是否发送数据包.')
    parser.add_argument('--count', type=int, default=-1, help='发包数量')
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = parse_args()
    print(args)
    #data_path = os.path.join("Data", "datasets", "traffic_data", "data1", "data.csv")
    #监听流量特征模型采样结果保存目录
    data_path = os.path.join("OUTPUT", "traffic_1","features")
    #伪装流量保存文件
    pcap_path = os.path.join("OUTPUT", "pcap", "background_traffic.pcap")
    if os.path.isfile(pcap_path):
        os.remove(pcap_path)
    generator = TrafficGenerator(args)
    #启动采样程序
    if args.sample:
        generator.sampling(milestone=10,num_cycles=1,size_every=100)
    #初始化事件监听器
    listen = SequentialCSVConsumer(
        generator=generator,    #生成器
        folder_path=data_path,  # 监听目录
        start_index=1,
        count=args.count
    )
    #初始化同步启动器
    # starter = StartSyn(listen=listen, args=args)
    # if args.host_type == "c":
    #     starter.client()
    # else:
    #     starter.server()

    listen.start()