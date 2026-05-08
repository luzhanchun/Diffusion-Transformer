FROM continuumio/miniconda3:latest

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN conda create -n diff-ts python=3.10 -y && \
    conda run --no-capture-output -n diff-ts python -m pip install --no-cache-dir -r requirements.txt && \
    conda clean -afy
#不是“激活 conda 环境”,这行只是把环境里的可执行文件目录放到 PATH 前面：让 python/pip 默认指向 diff-ts 环境

RUN conda config --system --set auto_activate_base false
#让交互式 bash 进入 diff-ts
RUN echo "source /opt/conda/etc/profile.d/conda.sh" >> /root/.bashrc && \
    echo "conda activate diff-ts" >> /root/.bashrc
#作用于ENTRYPOINT入口
ENV PATH=/opt/conda/envs/diff-ts/bin:$PATH

COPY . .

EXPOSE 50000
# 默认使用该 conda 环境执行命令
#SHELL ["conda", "run", "-n", "diff-ts", "/bin/bash", "-c"]

#固定执行的程序
#ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "diff-ts", "python", "generator.py"]
ENTRYPOINT ["/opt/conda/envs/diff-ts/bin/python", "generator.py"]
#默认参数或命令
CMD ["--host_type", "s", "--send", "--syn", "--count", "100"]