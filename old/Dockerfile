# Dockerfile for Slovak Transcription Tool - AWS Lambda Container (pyannoteAI API)
FROM public.ecr.aws/lambda/python:3.11

# Install system dependencies
RUN yum update -y && \
    yum install -y \
        ffmpeg \
        git \
        wget \
        && yum clean all

# Set working directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy requirements first for better caching
COPY requirements.txt requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies that might not be in requirements.txt
RUN pip install --no-cache-dir \
    yt-dlp \
    openai-whisper \
    torch \
    torchaudio \
    transformers \
    boto3

# Copy the application code
COPY slovak_transcription_tool_pyannote_api.py slovak_transcription_tool.py

# Set environment variables
ENV PYTHONPATH="${LAMBDA_TASK_ROOT}"
ENV WHISPER_CACHE="${LAMBDA_TASK_ROOT}/.cache/whisper"

# Create cache directory with proper permissions
RUN mkdir -p ${WHISPER_CACHE} && chmod 755 ${WHISPER_CACHE}

# Command to run the lambda function
CMD ["slovak_transcription_tool.lambda_handler"]