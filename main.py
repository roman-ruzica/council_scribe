#!/usr/bin/env python3
"""
Simplified Slovak Transcription Tool for Local Docker Environment
Uses existing Whisper service + pyannoteAI API for speaker diarization
"""

import os
import requests
import json
import tempfile
import logging
import time
from typing import List, Dict, Optional
import urllib.request
from pathlib import Path
import dotenv

dotenv.load_dotenv('.')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SimpleSlovakTranscriptionTool:
    def __init__(self,
                 whisper_endpoint: str = "http://localhost:5001/transcribe",
                 pyannote_api_key: Optional[str] = None):
        """
        Initialize the simplified transcription tool

        Args:
            whisper_endpoint: URL of existing Whisper service
            pyannote_api_key: pyannoteAI API key for speaker diarization
        """
        self.whisper_endpoint = whisper_endpoint
        self.pyannote_api_key = pyannote_api_key or os.getenv('PYANNOTE_API_KEY')

        logger.info(f"Initialized with Whisper endpoint: {whisper_endpoint}")
        if self.pyannote_api_key:
            logger.info("pyannoteAI API key found for speaker diarization")
        else:
            logger.warning("No pyannoteAI API key found - will skip speaker diarization")

    def download_audio_file(self, url: str, output_path: str) -> str:
        """
        Download audio file from URL

        Args:
            url: Audio file URL
            output_path: Local path to save file

        Returns:
            Path to downloaded file
        """
        try:
            logger.info(f"Downloading audio from: {url}")

            # Get filename from URL or use default
            filename = Path(url).name
            if not filename.endswith(('.mp3', '.wav', '.m4a', '.flac')):
                filename = 'audio.mp3'

            local_path = os.path.join(output_path, filename)

            # Download the file
            urllib.request.urlretrieve(url, local_path)

            file_size = os.path.getsize(local_path) / (1024 * 1024)  # MB
            logger.info(f"Downloaded {file_size:.1f} MB to: {local_path}")

            return local_path

        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            raise

    def transcribe_with_existing_whisper(self, audio_path: str) -> Dict:
        """
        Transcribe audio using existing Whisper service

        Args:
            audio_path: Path to audio file

        Returns:
            Transcription result from Whisper service
        """
        try:
            logger.info(f"Transcribing audio with Whisper service: {self.whisper_endpoint}")

            # Prepare the file for upload
            files = {
                'file': ('audio.mp3', open(audio_path, 'rb'), 'audio/mpeg')
            }

            # Make request to Whisper service
            response = requests.post(self.whisper_endpoint, files=files)
            response.raise_for_status()

            result = response.json()

            # Close the file
            files['file'][1].close()

            logger.info(f"Transcription completed: {len(result.get('segments', []))} segments")
            return result

        except Exception as e:
            logger.error(f"Error in transcription: {e}")
            raise

    def create_diarization_job(self, audio_url: str) -> Dict:
        """
        Create speaker diarization job using pyannoteAI API

        Args:
            audio_url: Public URL to audio file

        Returns:
            Job creation response
        """
        try:
            if not self.pyannote_api_key:
                raise ValueError("pyannoteAI API key required for speaker diarization")

            url = "https://api.pyannote.ai/v1/diarize"
            headers = {
                "Authorization": f"Bearer {self.pyannote_api_key}",
                "Content-Type": "application/json"
            }

            data = {'url': audio_url}

            logger.info("Creating diarization job with pyannoteAI API")
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Diarization job created: {result.get('jobId')}")
            return result

        except Exception as e:
            logger.error(f"Error creating diarization job: {e}")
            raise

    def poll_diarization_job(self, job_id: str, max_wait_time: int = 300) -> Dict:
        """
        Poll for diarization job completion

        Args:
            job_id: Job ID from diarization API
            max_wait_time: Maximum wait time in seconds

        Returns:
            Diarization results when complete
        """
        try:
            url = f"https://api.pyannote.ai/v1/jobs/{job_id}"
            headers = {"Authorization": f"Bearer {self.pyannote_api_key}"}

            start_time = time.time()
            poll_interval = 10

            logger.info(f"Polling diarization job: {job_id}")

            while time.time() - start_time < max_wait_time:
                response = requests.get(url, headers=headers)
                response.raise_for_status()

                result = response.json()
                status = result.get('status')

                logger.info(f"Job status: {status}")

                if status == 'succeeded':
                    logger.info("Diarization completed successfully")
                    return result
                elif status == 'failed':
                    raise RuntimeError(f"Diarization failed: {result.get('error', 'Unknown error')}")
                elif status in ['pending', 'running']:
                    time.sleep(poll_interval)
                else:
                    logger.warning(f"Unknown status: {status}")
                    time.sleep(poll_interval)

            raise TimeoutError(f"Diarization did not complete within {max_wait_time} seconds")

        except Exception as e:
            logger.error(f"Error polling diarization job: {e}")
            raise

    def align_transcription_with_speakers(self, transcription: Dict, diarization: List[Dict]) -> List[Dict]:
        """
        Align transcription segments with speaker information

        Args:
            transcription: Whisper transcription result
            diarization: pyannoteAI diarization segments

        Returns:
            List of aligned segments with speaker labels
        """
        try:
            logger.info("Aligning transcription with speaker diarization")
            aligned_segments = []

            segments = transcription.get('segments', [])

            for segment in segments:
                segment_start = segment.get('start', 0)
                segment_end = segment.get('end', 0)
                segment_text = segment.get('text', '').strip()

                # Find best matching speaker
                best_speaker = 'UNKNOWN'
                best_overlap = 0

                for diar_seg in diarization:
                    diar_start = diar_seg.get('start', 0)
                    diar_end = diar_seg.get('end', 0)

                    # Calculate overlap
                    overlap_start = max(segment_start, diar_start)
                    overlap_end = min(segment_end, diar_end)
                    overlap = max(0, overlap_end - overlap_start)

                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_speaker = diar_seg.get('speaker', 'UNKNOWN')

                aligned_segments.append({
                    'start': segment_start,
                    'end': segment_end,
                    'speaker': best_speaker,
                    'text': segment_text,
                    'confidence': segment.get('avg_logprob', 0)
                })

            logger.info(f"Alignment completed: {len(aligned_segments)} segments")
            return aligned_segments

        except Exception as e:
            logger.error(f"Error in alignment: {e}")
            raise

    def process_audio_url(self, audio_url: str, enable_diarization: bool = True) -> Dict:
        """
        Complete processing pipeline for audio URL

        Args:
            audio_url: URL to audio file
            enable_diarization: Whether to perform speaker diarization

        Returns:
            Complete transcription results with speaker labels
        """
        try:
            logger.info(f"Processing audio URL: {audio_url}")

            with tempfile.TemporaryDirectory() as temp_dir:
                # Step 1: Download audio file
                audio_path = self.download_audio_file(audio_url, temp_dir)

                # Step 2: Transcribe with existing Whisper service
                transcription = self.transcribe_with_existing_whisper(audio_path)

                # Step 3: Perform speaker diarization (if enabled and API key available)
                if enable_diarization and self.pyannote_api_key:
                    try:
                        # Create diarization job
                        job_response = self.create_diarization_job(audio_url)
                        job_id = job_response.get('jobId')

                        if job_id:
                            # Poll for completion
                            diarization_result = self.poll_diarization_job(job_id)
                            diarization_segments = diarization_result.get('output', {}).get('diarization', [])

                            # Align transcription with speakers
                            final_segments = self.align_transcription_with_speakers(
                                transcription, diarization_segments
                            )
                        else:
                            logger.warning("No job ID returned from diarization API")
                            final_segments = self._transcription_to_segments(transcription)

                    except Exception as e:
                        logger.warning(f"Diarization failed, continuing with transcription only: {e}")
                        final_segments = self._transcription_to_segments(transcription)
                else:
                    logger.info("Skipping diarization (disabled or no API key)")
                    final_segments = self._transcription_to_segments(transcription)

                # Merge consecutive segments from same speaker
                merged_segments = self._merge_consecutive_segments(final_segments)

                # Prepare final result
                speakers = list(set(seg['speaker'] for seg in merged_segments))

                result = {
                    'url': audio_url,
                    'segments': merged_segments,
                    'summary': {
                        'total_segments': len(merged_segments),
                        'speakers': speakers,
                        'duration': merged_segments[-1]['end'] if merged_segments else 0,
                        'diarization_enabled': enable_diarization and bool(self.pyannote_api_key)
                    }
                }

                logger.info("Processing completed successfully")
                return result

        except Exception as e:
            logger.error(f"Error in processing pipeline: {e}")
            raise

    def _transcription_to_segments(self, transcription: Dict) -> List[Dict]:
        """Convert Whisper transcription to segment format"""
        segments = []
        for segment in transcription.get('segments', []):
            segments.append({
                'start': segment.get('start', 0),
                'end': segment.get('end', 0),
                'speaker': 'SPEAKER_00',  # Default speaker
                'text': segment.get('text', '').strip(),
                'confidence': segment.get('avg_logprob', 0)
            })
        return segments

    def _merge_consecutive_segments(self, segments: List[Dict]) -> List[Dict]:
        """Merge consecutive segments from same speaker"""
        if not segments:
            return segments

        merged = []
        current = segments[0].copy()

        for segment in segments[1:]:
            # Merge if same speaker and close timing
            if (segment['speaker'] == current['speaker'] and
                    segment['start'] - current['end'] <= 2.0):  # 2 second gap tolerance
                current['end'] = segment['end']
                current['text'] += ' ' + segment['text']
                current['confidence'] = (current['confidence'] + segment['confidence']) / 2
            else:
                merged.append(current)
                current = segment.copy()

        merged.append(current)
        return merged

def main():
    """Main function for command-line usage"""
    import argparse

    parser = argparse.ArgumentParser(description='Simplified Slovak Transcription Tool')
    parser.add_argument('--audio-url', required=True, help='URL of audio file to transcribe')
    parser.add_argument('--whisper-endpoint', default='http://localhost:5001/transcribe',
                        help='Whisper service endpoint')
    parser.add_argument('--no-diarization', action='store_true',
                        help='Skip speaker diarization')
    parser.add_argument('--output', '-o', help='Output JSON file path')

    args = parser.parse_args()

    # Initialize tool
    tool = SimpleSlovakTranscriptionTool(
        whisper_endpoint=args.whisper_endpoint
    )

    try:
        # Process audio
        result = tool.process_audio_url(
            args.audio_url,
            enable_diarization=not args.no_diarization
        )

        # Output results
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"Results saved to: {args.output}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        logger.error(f"Processing failed: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())