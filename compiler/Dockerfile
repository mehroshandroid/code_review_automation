FROM eclipse-temurin:17-jdk-jammy

ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV PATH="${PATH}:${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin:${ANDROID_SDK_ROOT}/platform-tools"
# Belt-and-suspenders alongside the explicit flush=True calls in lint_runner.py --
# guarantees any stray print()/log line still streams immediately rather than
# sitting in a buffer until the process exits.
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl unzip python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Android command-line tools.
RUN mkdir -p ${ANDROID_SDK_ROOT}/cmdline-tools \
    && curl -sSL -o /tmp/cmdline-tools.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip \
    && unzip -q /tmp/cmdline-tools.zip -d ${ANDROID_SDK_ROOT}/cmdline-tools \
    && mv ${ANDROID_SDK_ROOT}/cmdline-tools/cmdline-tools ${ANDROID_SDK_ROOT}/cmdline-tools/latest \
    && rm /tmp/cmdline-tools.zip

RUN yes | sdkmanager --licenses --sdk_root=${ANDROID_SDK_ROOT} \
    && sdkmanager --sdk_root=${ANDROID_SDK_ROOT} "platform-tools" "platforms;android-34" "build-tools;34.0.0"

# Fallback Gradle, used only for uploaded projects with no gradlew wrapper.
RUN curl -sSL -o /tmp/gradle.zip https://services.gradle.org/distributions/gradle-8.5-bin.zip \
    && unzip -q /tmp/gradle.zip -d /opt \
    && ln -s /opt/gradle-8.5/bin/gradle /usr/local/bin/gradle \
    && rm /tmp/gradle.zip

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
