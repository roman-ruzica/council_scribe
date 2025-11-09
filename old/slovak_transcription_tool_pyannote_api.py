
"""
Slovak Video/Audio Transcription Tool with Speaker Diarization
Updated to use pyannoteAI API service instead of local models
Designed for AWS Lambda deployment with open-source Whisper + cloud diarization
"""

import os
import tempfile
import yt_dlp
import whisper
import torch
import requests
import time
import json
import dotenv
from typing import List, Dict, Tuple, Optional
import logging
from urllib.parse import urljoin
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dotenv = dotenv.load_dotenv('../.env')
print(dotenv)
print(os.getenv('PYANNOTE_API_KEY'))

class SlovakTranscriptionTool:
    def __init__(self, 
                 whisper_model_name: str = "large-v3", 
                 use_fine_tuned_slovak: bool = True,
                 pyannote_api_key: Optional[str] = None,
                 s3_bucket: Optional[str] = None):
        """
        Initialize the Slovak Transcription Tool with pyannoteAI API

        Args:
            whisper_model_name: Whisper model size ('small', 'medium', 'large-v3', 'turbo')
            use_fine_tuned_slovak: Whether to use Slovak fine-tuned models from SloPalSpeech
            pyannote_api_key: pyannoteAI API key
            s3_bucket: S3 bucket for temporary file storage (required for pyannoteAI)
        """
        self.whisper_model_name = whisper_model_name
        self.use_fine_tuned_slovak = use_fine_tuned_slovak
        self.pyannote_api_key = os.getenv('PYANNOTE_API_KEY')
        self.s3_bucket = s3_bucket or os.getenv('S3_BUCKET_NAME')

        # Initialize models and services
        self.whisper_model = None
        self.s3_client = None
        self._initialize_services()

    def _initialize_services(self):
        """Initialize Whisper model and AWS S3 client"""
        try:
            # Load Whisper model (fine-tuned Slovak if available)
            if self.use_fine_tuned_slovak:
                # These would be the fine-tuned models from SloPalSpeech research
                model_mapping = {
                    'small': 'ebozik/whisper-small-sk',
                    'medium': 'ebozik/whisper-medium-sk', 
                    'large-v3': 'ebozik/whisper-large-v3-sk',
                    'turbo': 'ebozik/whisper-large-v3-turbo-sk'
                }
                model_name = model_mapping.get(self.whisper_model_name, 'large-v3')
                logger.info(f"Loading fine-tuned Slovak Whisper model: {model_name}")
                # Note: These models may need to be loaded via HuggingFace transformers
                # self.whisper_model = whisper.load_model(model_name)
            else:
                logger.info(f"Loading standard Whisper model: {self.whisper_model_name}")

            # For now, use standard whisper as fine-tuned may not be directly available
            self.whisper_model = whisper.load_model(self.whisper_model_name)

            # Initialize S3 client for file uploads
            if self.s3_bucket:
                self.s3_client = boto3.client('s3')
                logger.info(f"S3 client initialized for bucket: {self.s3_bucket}")

            logger.info("Services initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing services: {e}")
            raise

    def download_audio(self, url: str, output_path: str) -> str:
        """
        Download audio from URL using yt-dlp

        Args:
            url: Video/Audio URL
            output_path: Directory to save audio file

        Returns:
            Path to downloaded audio file
        """
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                    'preferredquality': '192',
                }],
                'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first to get the title
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'audio')

                # Download the audio
                ydl.download([url])

                # Return the path to the downloaded file
                audio_file = os.path.join(output_path, f"{title}.wav")
                logger.info(f"Audio downloaded: {audio_file}")
                return audio_file

        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            raise

    def upload_to_s3(self, local_file_path: str, s3_key: str) -> str:
        """
        Upload file to S3 and return a presigned URL

        Args:
            local_file_path: Path to local file
            s3_key: S3 object key

        Returns:
            Presigned URL for the uploaded file
        """
        try:
            if not self.s3_client or not self.s3_bucket:
                raise ValueError("S3 client not initialized or bucket not specified")

            # Upload file to S3
            self.s3_client.upload_file(local_file_path, self.s3_bucket, s3_key)
            logger.info(f"File uploaded to S3: s3://{self.s3_bucket}/{s3_key}")

            # Generate presigned URL (valid for 1 hour)
            presigned_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.s3_bucket, 'Key': s3_key},
                ExpiresIn=3600  # 1 hour
            )

            logger.info(f"Presigned URL generated: {presigned_url[:50]}...")
            return presigned_url

        except Exception as e:
            logger.error(f"Error uploading to S3: {e}")
            raise

    def transcribe_audio(self, audio_path: str) -> Dict:
        """
        Transcribe audio using Whisper

        Args:
            audio_path: Path to audio file

        Returns:
            Whisper transcription result
        """
        try:
            logger.info("Starting Whisper transcription")
            result = self.whisper_model.transcribe(
                audio_path, 
                language='sk',  # Slovak language code
                task='transcribe'
            )
            logger.info(f"Transcription completed. Found {len(result['segments'])} segments")
            return result
        except Exception as e:
            logger.error(f"Error in transcription: {e}")
            raise

    def create_diarization_job(self, audio_file_url: str, webhook_url: Optional[str] = None) -> Dict:
        """
        Create a diarization job using pyannoteAI API

        Args:
            audio_file_url: Public URL to the audio file
            webhook_url: Optional webhook URL for async results

        Returns:
            Job creation response from pyannoteAI API
        """
        try:
            if not self.pyannote_api_key:
                raise ValueError("pyannoteAI API key not provided")

            url = "https://api.pyannote.ai/v1/diarize"

            headers = {
                "Authorization": f"Bearer {self.pyannote_api_key}",
                "Content-Type": "application/json"
            }

            data = {
                'url': audio_file_url
            }

            # Add webhook URL if provided
            if webhook_url:
                data['webhook'] = webhook_url

            logger.info(f"Creating diarization job for URL: {audio_file_url[:50]}...")
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Diarization job created: {result.get('jobId')}")
            return result

        except Exception as e:
            logger.error(f"Error creating diarization job: {e}")
            raise

    def poll_diarization_job(self, job_id: str, max_wait_time: int = 600, poll_interval: int = 10) -> Dict:
        """
        Poll for diarization job completion

        Args:
            job_id: Job ID from create_diarization_job
            max_wait_time: Maximum time to wait in seconds (default: 10 minutes)
            poll_interval: How often to poll in seconds (default: 10 seconds)

        Returns:
            Diarization result when job is complete
        """
        try:
            if not self.pyannote_api_key:
                raise ValueError("pyannoteAI API key not provided")

            url = f"https://api.pyannote.ai/v1/jobs/{job_id}"

            headers = {
                "Authorization": f"Bearer {self.pyannote_api_key}"
            }

            start_time = time.time()

            logger.info(f"Polling for job completion: {job_id}")

            while time.time() - start_time < max_wait_time:
                response = requests.get(url, headers=headers)
                response.raise_for_status()

                result = response.json()
                status = result.get('status')

                logger.info(f"Job status: {status}")

                if status == 'succeeded':
                    logger.info("Diarization job completed successfully")
                    return result
                elif status == 'failed':
                    error_msg = result.get('error', 'Unknown error')
                    raise RuntimeError(f"Diarization job failed: {error_msg}")
                elif status in ['pending', 'running']:
                    # Job still processing, wait and poll again
                    time.sleep(poll_interval)
                else:
                    logger.warning(f"Unknown job status: {status}")
                    time.sleep(poll_interval)

            raise TimeoutError(f"Diarization job did not complete within {max_wait_time} seconds")

        except Exception as e:
            logger.error(f"Error polling diarization job: {e}")
            raise

    def perform_diarization_sync(self, audio_path: str) -> List[Dict]:
        """
        Perform synchronous speaker diarization using pyannoteAI API

        Args:
            audio_path: Path to local audio file

        Returns:
            List of speaker segments
        """
        try:
            # Generate a unique S3 key
            import uuid
            s3_key = f"temp-audio/{uuid.uuid4()}.wav"

            # Upload audio file to S3
            audio_file_url = self.upload_to_s3(audio_path, s3_key)

            # Create diarization job
            job_response = self.create_diarization_job(audio_file_url)
            job_id = job_response.get('jobId')

            if not job_id:
                raise ValueError("No job ID returned from diarization API")

            # Poll for job completion
            result = self.poll_diarization_job(job_id)

            # Extract diarization segments
            diarization_data = result.get('output', {}).get('diarization', [])

            # Clean up S3 file
            try:
                self.s3_client.delete_object(Bucket=self.s3_bucket, Key=s3_key)
                logger.info(f"Cleaned up temporary S3 file: {s3_key}")
            except Exception as e:
                logger.warning(f"Failed to clean up S3 file: {e}")

            logger.info(f"Diarization completed. Found {len(diarization_data)} segments")
            return diarization_data

        except Exception as e:
            logger.error(f"Error in synchronous diarization: {e}")
            raise

    def align_transcription_with_speakers(self, transcription: Dict, diarization: List[Dict]) -> List[Dict]:
        """
        Align Whisper transcription with pyannoteAI diarization results

        Args:
            transcription: Whisper transcription result
            diarization: pyannoteAI diarization result (list of segments)

        Returns:
            List of aligned segments with speaker labels
        """
        try:
            logger.info("Aligning transcription with speaker diarization")
            aligned_segments = []

            for segment in transcription['segments']:
                segment_start = segment['start']
                segment_end = segment['end']
                segment_text = segment['text'].strip()

                # Find the best matching speaker segment
                best_speaker = None
                best_overlap = 0

                for diar_seg in diarization:
                    diar_start = diar_seg['start']
                    diar_end = diar_seg['end']

                    # Calculate overlap between transcription segment and diarization segment
                    overlap_start = max(segment_start, diar_start)
                    overlap_end = min(segment_end, diar_end)
                    overlap_duration = max(0, overlap_end - overlap_start)

                    if overlap_duration > best_overlap:
                        best_overlap = overlap_duration
                        best_speaker = diar_seg['speaker']

                aligned_segments.append({
                    'start': segment_start,
                    'end': segment_end,
                    'speaker': best_speaker or 'UNKNOWN',
                    'text': segment_text,
                    'confidence': segment.get('avg_logprob', 0)
                })

            logger.info(f"Alignment completed. Created {len(aligned_segments)} aligned segments")
            return aligned_segments

        except Exception as e:
            logger.error(f"Error in alignment: {e}")
            raise

    def merge_consecutive_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        Merge consecutive segments from the same speaker

        Args:
            segments: List of aligned segments

        Returns:
            List of merged segments
        """
        if not segments:
            return segments

        merged = []
        current_segment = segments[0].copy()

        for segment in segments[1:]:
            # If same speaker and segments are close (within 1 second gap)
            if (segment['speaker'] == current_segment['speaker'] and 
                segment['start'] - current_segment['end'] <= 1.0):

                # Merge segments
                current_segment['end'] = segment['end']
                current_segment['text'] += ' ' + segment['text']
                # Average the confidence scores
                current_segment['confidence'] = (
                    current_segment['confidence'] + segment['confidence']
                ) / 2
            else:
                # Different speaker or gap too large, start new segment
                merged.append(current_segment)
                current_segment = segment.copy()

        # Add the last segment
        merged.append(current_segment)

        logger.info(f"Merged {len(segments)} segments into {len(merged)} segments")
        return merged

    def process_url(self, url: str) -> List[Dict]:
        """
        Complete processing pipeline: download, transcribe, diarize, and align

        Args:
            url: Video/Audio URL to process

        Returns:
            List of segments with speaker labels and text
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Step 1: Download audio
                logger.info(f"Processing URL: {url}")
                audio_path = self.download_audio(url, temp_dir)

                # Step 2: Transcribe audio
                transcription = self.transcribe_audio(audio_path)

                # Step 3: Perform speaker diarization using pyannoteAI API
                diarization = self.perform_diarization_sync(audio_path)

                # Step 4: Align transcription with speakers
                aligned_segments = self.align_transcription_with_speakers(
                    transcription, diarization
                )

                # Step 5: Merge consecutive segments from same speaker
                final_segments = self.merge_consecutive_segments(aligned_segments)

                logger.info("Processing completed successfully")
                return final_segments

            except Exception as e:
                logger.error(f"Error in processing pipeline: {e}")
                raise

def lambda_handler(event, context):
    """
    AWS Lambda handler function

    Args:
        event: Lambda event containing URL and optional parameters
        context: Lambda context

    Returns:
        Processing result
    """
    try:
        # Extract parameters from event
        url = event.get('url')
        if not url:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'URL parameter is required'})
            }

        whisper_model = event.get('whisper_model', 'large-v3')
        use_fine_tuned = event.get('use_fine_tuned_slovak', True)

        # Initialize the transcription tool
        tool = SlovakTranscriptionTool(
            whisper_model_name=whisper_model,
            use_fine_tuned_slovak=use_fine_tuned
        )

        # Process the URL
        result = tool.process_url(url)

        # Format the response
        response = {
            'url': url,
            'segments': result,
            'summary': {
                'total_segments': len(result),
                'speakers': list(set(seg['speaker'] for seg in result)),
                'duration': result[-1]['end'] if result else 0
            }
        }

        return {
            'statusCode': 200,
            'body': json.dumps(response, ensure_ascii=False, indent=2)
        }

    except Exception as e:
        logger.error(f"Lambda handler error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

# Example usage for local testing
if __name__ == "__main__":
    # Example usage
    tool = SlovakTranscriptionTool(
        whisper_model_name='large-v3',
        use_fine_tuned_slovak=False  # Set to True when fine-tuned models are available
    )

    # Example URL (replace with actual URL)
    # result = tool.process_url("https://www.youtube.com/watch?v=example")
    # print(json.dumps(result, ensure_ascii=False, indent=2))
