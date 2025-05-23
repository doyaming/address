FROM ubuntu:20.04
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 安裝系統與 Python 依賴
RUN apt-get update && apt-get install -y \
    software-properties-common \
    curl \
    gnupg \
    build-essential \
    python3.9 \
    python3.9-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*


# 安裝 Microsoft ODBC Driver 18 for SQL Server
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
    msodbcsql18 \
    mssql-tools18 \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Python 軟連結設定
RUN ln -sf /usr/bin/python3.9 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip

WORKDIR /app
# 複製並安裝 Python 依賴
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt

# 複製應用程式碼
COPY . .
ENV PATH="$PATH:/opt/mssql-tools18/bin"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
EXPOSE 6001
# 啟動 Gunicorn
CMD ["gunicorn", \
     "--bind", "0.0.0.0:6001", \
     "--workers", "2", \
     "--timeout", "120", \
     "--log-level", "debug", \
     "--keep-alive", "65", \
     "--worker-connections", "1000", \
     "--backlog", "2048", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
