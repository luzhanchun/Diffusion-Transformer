import json
import csv
import os


def zeek_log_to_csv(input_file: str, output_file: str):
    """
    读取 Zeek JSON Lines 日志(一行一个JSON)，提取 dir、tcp_len，
    并按“与上一条记录”的时间戳差计算 iat（微秒）。

    输出 csv
    """
    prev_ts = 0
    with open(input_file, 'r', encoding='utf-8') as fin, \
        open(output_file, 'w', newline='', encoding='utf-8') as fout:

        writer = csv.writer(fout)
        writer.writerow(["pkt_i", "len", "iat", "dir"])  # CSV表头

        for line in fin:
            line = line.strip()
            if not line:
                continue

            data = json.loads(line)

            pkt_i = data["pkt_i"]
            length = data["tcp_len"]
            ts = data["ts"]
            direction = data["dir"]

            # 计算 iat
            if pkt_i == 1:
                iat = 0
            else:
                iat = (ts - prev_ts) * 1_000_000
            prev_ts = ts

            writer.writerow([pkt_i, length, int(iat), direction])

if __name__ == "__main__":
    data_index = "data5"
    input_file = os.path.join(".",data_index,"flow_packets_pkt.log")
    out_file = os.path.join(".",data_index,"data.csv")
    print(input_file)
    print(out_file)
    zeek_log_to_csv(input_file, out_file)
    print("Saved complete! ", out_file)
