import os
import pandas as pd
import numpy as np


if __name__ == '__main__':
    path = os.path.join("OUTPUT","traffic_1")
    data = np.load(os.path.join(path,"ddpm_fake_traffic_1.npy"))
    print(data.shape,data.dtype)

    # data: shape (seq_len, 2)
    third_col = np.where(data[:, 0] > 0, 1, -1)
    # 第一列取绝对值
    data[:, 0] = np.abs(data[:, 0])
    # 扩展为 (seq_len, 3)
    data_3dim = np.concatenate([data, third_col.reshape(-1, 1)], axis=1)

    df = pd.DataFrame(data_3dim, columns=["pkg_len", "pkg_iat","pkt_dir"])
    df.to_csv(os.path.join(path,"traffic_feature_generated.csv"), index=False)
    print("post_process complete")
