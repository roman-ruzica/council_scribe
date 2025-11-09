# Slovak Video/Audio Transcription Tool with Speaker Diarization

A comprehensive solution for transcribing Slovak audio and video content with automatic speaker identification, designed for deployment on AWS Lambda or ECS using open-source models.

## Features

- **Multi-source Download**: Support for thousands of websites via yt-dlp
- **Slovak Speech Recognition**: Uses OpenAI Whisper with optional fine-tuned Slovak models
- **Speaker Diarization**: Identifies and labels different speakers using pyannote.audio
- **Temporal Alignment**: Precisely aligns transcription with speaker segments
- **AWS Integration**: Ready for Lambda or ECS deployment
- **Scalable Architecture**: Optional Step Functions orchestration for complex workflows

## Performance

Based on SloPalSpeech research (2024), fine-tuned Slovak models show significant improvements:

| Model | Base WER (CV21) | Fine-tuned WER | Improvement |
|-------|----------------|----------------|-------------|
| Whisper Small | 58.4% | 25.7% | 65-70% |
| Whisper Medium | 38.0% | 18.0% | Substantial |
| Whisper Large-v3 | 20.8% | 11.6% | Best accuracy |

## Architecture

The system processes audio/video through the following pipeline:

1. **Download**: yt-dlp extracts audio from provided URLs
2. **Transcription**: Whisper converts speech to text in Slovak
3. **Diarization**: pyannote.audio identifies speaker segments
4. **Alignment**: Custom algorithm matches text to speakers
5. **Output**: JSON with timestamped, speaker-labeled transcription

## Deployment Options

### Option 1: AWS Lambda (Recommended for sporadic use)

**Pros:**
- Pay-per-execution pricing
- No infrastructure management
- Automatic scaling
- Up to 10GB container image support

**Cons:**
- 15-minute timeout limit
- Cold start latency
- Memory limit (10GB)

**Best for:** Infrequent transcription jobs, event-driven processing

### Option 2: AWS ECS (Recommended for continuous use)

**Pros:**
- No time limits
- Full control over resources
- Better for long-running tasks
- Consistent performance

**Cons:**
- Always-on costs
- More complex setup
- Manual scaling configuration

**Best for:** High-volume processing, continuous availability

### Option 3: AWS Step Functions (Recommended for complex workflows)

**Pros:**
- Orchestrates multi-step processes
- Better error handling
- Visual workflow management
- Can combine Lambda and ECS

**Cons:**
- Additional service complexity
- Higher cost for simple tasks

**Best for:** Complex processing pipelines, error recovery requirements

## Quick Start

### Prerequisites

1. **AWS Account** with appropriate permissions
2. **Docker** installed locally
3. **AWS CLI** configured
4. **HuggingFace Token** for pyannote models ([Get token here](https://huggingface.co/settings/tokens))
5. **AWS SAM CLI** for deployment

### Installation

1. **Clone or download the project files**

2. **Set environment variables:**
   ```bash
   export HUGGINGFACE_TOKEN=your_token_here
   export AWS_REGION=eu-west-1  # or your preferred region
   ```

3. **Accept HuggingFace model terms:**
   - Visit [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
   - Visit [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
   - Accept the terms of use for both models

4. **Deploy to AWS Lambda:**
   ```bash
   ./build.sh
   ```

### Local Testing

Test the system locally with Docker:

```bash
# Build the container
docker build -t slovak-transcription .

# Run locally
docker run -p 8080:8080 \
  -e HUGGINGFACE_TOKEN=your_token \
  slovak-transcription
```

### API Usage

Send POST requests to the deployed endpoint:

```bash
curl -X POST https://your-api-gateway-url/transcribe \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=example",
    "whisper_model": "large-v3",
    "use_fine_tuned_slovak": true
  }'
```

Response format:
```json
{
  "url": "https://www.youtube.com/watch?v=example",
  "segments": [
    {
      "start": 0.0,
      "end": 5.2,
      "speaker": "SPEAKER_00",
      "text": "Dobrý deň, vítam vás na našej prezentácii.",
      "confidence": -0.23
    }
  ],
  "summary": {
    "total_segments": 45,
    "speakers": ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"],
    "duration": 180.5
  }
}
```

## Configuration Options

### Whisper Models

| Model | Size | Memory | Speed | Accuracy |
|-------|------|---------|-------|----------|
| small | ~244 MB | ~1 GB | Fast | Good |
| medium | ~769 MB | ~2 GB | Medium | Better |
| large-v3 | ~1550 MB | ~4 GB | Slow | Best |
| turbo | ~809 MB | ~2 GB | Fast | Very Good |

### Environment Variables

- `HUGGINGFACE_TOKEN`: Required for pyannote models
- `WHISPER_MODEL`: Default model size (default: "large-v3")
- `USE_FINE_TUNED_SLOVAK`: Use Slovak-optimized models (default: true)
- `MAX_SPEAKERS`: Maximum expected speakers (default: auto-detect)
- `LOG_LEVEL`: Logging verbosity (default: "INFO")

## AWS Lambda Limitations & Workarounds

### Timeout Limitation (15 minutes)

For videos longer than ~10 minutes, consider:

1. **Pre-processing**: Split long videos before processing
2. **Step Functions**: Use state machine for multi-step processing
3. **ECS Alternative**: Deploy on ECS for unlimited runtime

### Memory Limitations (10GB)

Large models may require memory optimization:

1. **Model Selection**: Use smaller models for memory-constrained environments
2. **Lazy Loading**: Load models only when needed
3. **Quantization**: Use 8-bit model variants

### Cold Start Mitigation

1. **Provisioned Concurrency**: Pre-warm Lambda functions
2. **Container Optimization**: Minimize Docker image size
3. **Model Caching**: Pre-download models in container

## Alternative Deployment: ECS

For unlimited processing time, deploy on ECS:

```yaml
# ecs-task-definition.json
{
  "family": "slovak-transcription-ecs",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "8192",
  "executionRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskRole",
  "containerDefinitions": [
    {
      "name": "slovak-transcription",
      "image": "ACCOUNT.dkr.ecr.REGION.amazonaws.com/slovak-transcription:latest",
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "HUGGINGFACE_TOKEN",
          "value": "your_token_here"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/slovak-transcription",
          "awslogs-region": "eu-west-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

## Step Functions Workflow

For complex processing pipelines, use the included Step Functions state machine:

1. **Parallel Processing**: Run transcription and diarization simultaneously
2. **Error Handling**: Automatic retries and failure management
3. **Result Storage**: Automatic S3 storage of results
4. **Monitoring**: CloudWatch integration for observability

## Troubleshooting

### Common Issues

1. **HuggingFace Token Error**
   - Ensure token is valid and has access to pyannote models
   - Accept model license terms on HuggingFace

2. **Memory Errors**
   - Reduce Whisper model size
   - Increase Lambda memory allocation
   - Consider ECS deployment

3. **Timeout Errors**
   - Use smaller audio chunks
   - Consider Step Functions for orchestration
   - Switch to ECS for long-running tasks

4. **Download Failures**
   - Verify URL accessibility
   - Check yt-dlp support for the website
   - Ensure network connectivity

### Performance Optimization

1. **Model Optimization**
   - Use quantized models for faster inference
   - Enable GPU acceleration when available
   - Cache models between invocations

2. **Audio Processing**
   - Reduce audio quality if acceptable
   - Pre-process audio to remove silence
   - Use streaming for real-time processing

3. **Infrastructure**
   - Use provisioned concurrency for Lambda
   - Enable VPC endpoints for S3 access
   - Optimize container image size

## Fine-tuned Slovak Models

The system supports fine-tuned Slovak models from the SloPalSpeech research:

- **whisper-small-sk**: 65-70% improvement over base model
- **whisper-medium-sk**: Substantial accuracy improvements
- **whisper-large-v3-sk**: Best accuracy for Slovak speech
- **whisper-turbo-sk**: Best performance-to-size ratio

To use fine-tuned models, ensure `use_fine_tuned_slovak: true` in your requests.

## Contributing

Contributions are welcome! Please consider:

1. **Model Improvements**: Integration of newer Slovak models
2. **Performance Optimization**: Better alignment algorithms
3. **Language Support**: Extension to other languages
4. **Deployment Options**: Additional cloud providers

## License

This project uses open-source models and libraries:

- **Whisper**: MIT License (OpenAI)
- **pyannote.audio**: MIT License
- **yt-dlp**: Unlicense
- **PyTorch**: BSD License

Please ensure compliance with all model licenses and terms of use.

## References

1. SloPalSpeech: A 2,800-Hour Slovak Speech Corpus (2024)
2. OpenAI Whisper: Robust Speech Recognition (2022)
3. pyannote.audio: Speaker Diarization Toolkit (2023)
4. AWS Lambda Container Image Support Documentation

## Support

For issues and questions:

1. Check the troubleshooting section
2. Review AWS CloudWatch logs
3. Verify model licensing and access
4. Test locally before deploying

Remember to monitor AWS costs, especially for high-volume usage or always-on ECS deployments.