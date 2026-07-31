# The .NET SDK image already bundles the dotnet CLI/MSBuild -- no manual
# toolchain provisioning needed the way Android's cmdline-tools/SDK
# components are (see compiler/Dockerfile). Pinned to 8.0 to match
# compare_dotnet_versions' own "net8.0 is latest" baseline.
FROM mcr.microsoft.com/dotnet/sdk:8.0

# Belt-and-suspenders alongside the explicit flush=True calls in
# dotnet_build_runner.py -- guarantees any stray print()/log line still
# streams immediately rather than sitting in a buffer until the process exits.
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
