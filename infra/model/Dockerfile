FROM ubuntu:24.04@sha256:24737cef17f4e22b1977df7d9a05e77c4e28b7da5b8911f8d8ccda136bf3573c AS download
ARG TARGETARCH
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
# Legacy Docker builders do not populate BuildKit's automatic TARGETARCH arg.
# dpkg reports the architecture of this stage, including under emulation.
RUN runtime_arch="${TARGETARCH:-$(dpkg --print-architecture)}" \
    && case "$runtime_arch" in \
      amd64) arch=x64; sha=b0bba21f5673f80f242c1a8f7c1380800f08b6eff6f32fd55eae9fe220690fdc ;; \
      arm64) arch=arm64; sha=f5a52789342647d39768efd14fed9fed2b4a826f5430d812c6778f6a8fd37e93 ;; \
      *) echo "Unsupported model architecture: $runtime_arch" >&2; exit 1 ;; \
    esac \
    && curl -fL --retry 3 -o /tmp/runtime.tar.gz "https://github.com/ggml-org/llama.cpp/releases/download/b11853/llama-b11853-bin-ubuntu-${arch}.tar.gz" \
    && echo "$sha  /tmp/runtime.tar.gz" | sha256sum -c - \
    && mkdir /runtime && tar -xzf /tmp/runtime.tar.gz -C /runtime --strip-components=1

FROM ubuntu:24.04@sha256:24737cef17f4e22b1977df7d9a05e77c4e28b7da5b8911f8d8ccda136bf3573c
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates python3 libgomp1 libcurl4t64 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 model && useradd -u 10001 -g model -m model \
    && mkdir -p /models /startup && chown model:model /models /startup
WORKDIR /runtime
COPY --from=download /runtime /runtime
ARG MODEL_LOCK=docs/docker-runtime.json
COPY ${MODEL_LOCK} /runtime/model-lock.json
COPY infra/model/start.py /runtime/start.py
ENV LD_LIBRARY_PATH=/runtime
USER model
EXPOSE 8082
CMD ["python3", "/runtime/start.py"]
