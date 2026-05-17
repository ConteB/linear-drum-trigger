# Base image with CUDA 12.1 and cuDNN 8 for PyTorch
FROM --platform=linux/amd64 nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# Set non-interactive mode for apt-get
ENV DEBIAN_FRONTEND=noninteractive

# Install basic dependencies and audio/video libraries needed for DSP/scraping
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    git \
    bzip2 \
    ca-certificates \
    libglib2.0-0 \
    libxext6 \
    libsm6 \
    libxrender1 \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Miniconda
ENV CONDA_DIR=/opt/conda
RUN arch=$(uname -m) && \
    if [ "$arch" = "x86_64" ]; then \
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"; \
    elif [ "$arch" = "aarch64" ]; then \
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh"; \
    else \
        echo "Unsupported architecture: $arch"; \
        exit 1; \
    fi && \
    wget --quiet $MINICONDA_URL -O ~/miniconda.sh && \
    /bin/bash ~/miniconda.sh -b -p /opt/conda && \
    rm ~/miniconda.sh

# Put conda in path so we can use conda activate
ENV PATH=$CONDA_DIR/bin:$PATH

# Copy environment file
COPY environment.yml /tmp/environment.yml

# Create conda environment
RUN conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r && \
    conda env create -f /tmp/environment.yml && \
    conda clean -afy

# Set default python environment path
ENV PATH=/opt/conda/envs/linear-drum-trigger/bin:$PATH

# Set working directory
WORKDIR /app

# Default command
CMD ["/bin/bash"]
