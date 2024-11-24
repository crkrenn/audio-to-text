import speech_recognition as r
from pydub import AudioSegment
import os
import sys
import subprocess
import platform
from tqdm import tqdm
import time
import argparse
from google.cloud import speech_v1
from google.cloud import storage
import uuid
import requests.exceptions
import urllib3.exceptions
from socket import timeout
from google.api_core import exceptions as google_exceptions

# GCP Speech-to-Text pricing constants (as of 2024)
PRICE_PER_15_SECONDS = 0.006  # $0.006 per 15 seconds
MINIMUM_BILLABLE_DURATION = 15  # seconds


def calculate_gcp_cost(duration_seconds):
    """
    Calculate estimated GCP Speech-to-Text API cost.

    Args:
        duration_seconds (float): Duration of audio in seconds

    Returns:
        tuple: (cost in USD, billable duration in seconds)
    """
    # Round up to nearest 15 seconds (minimum billable duration)
    billable_duration = max(
        MINIMUM_BILLABLE_DURATION,
        ((duration_seconds + 14) // 15) * 15,  # Round up to nearest 15 seconds
    )

    # Calculate cost
    segments = billable_duration / 15
    cost = segments * PRICE_PER_15_SECONDS

    return cost, billable_duration


# def parse_arguments():
#     """Parse command line arguments."""
#     parser = argparse.ArgumentParser(description='Convert audio files to text using either free or GCP API.')
#     parser.add_argument('files', nargs='+', help='Audio files to transcribe')
#     parser.add_argument('--api', choices=['free', 'gcp'], default='free',
#                        help='API to use (free or gcp)')
#     parser.add_argument('--estimate-only', action='store_true',
#                        help='Only estimate GCP costs without performing transcription')
#     return parser.parse_args()


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert audio files to text using either free or GCP API."
    )
    parser.add_argument("files", nargs="+", help="Audio files to transcribe")
    parser.add_argument(
        "--api",
        choices=["free", "gcp"],
        default="free",
        help="API to use (free or gcp)",
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        default=False,
        help="Only estimate GCP costs without performing transcription",
    )
    parser.add_argument(
        "--timestamps",
        action="store_true",
        default=False,
        help="Include word-level timestamps in the output (GCP API only)",
    )
    return parser.parse_args()


def check_gcp_setup():
    """Check if GCP credentials are properly set up."""
    try:
        # Define the path to the service account key file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(script_dir, "gcp-service-account-key.json")

        # Check if the key file exists
        if not os.path.exists(key_path):
            return False, (f"GCP service account key file not found at: {key_path}")

        # Set the environment variable to point to the key file
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path

        # Try to create a client to verify credentials
        storage.Client()
        return True, "GCP credentials verified successfully"
    except Exception as e:
        return False, f"GCP setup error: {str(e)}"


def get_audio_duration(file_path):
    """
    Get duration of audio file in seconds.

    Args:
        file_path (str): Path to audio file

    Returns:
        float: Duration in seconds
    """
    try:
        audio = AudioSegment.from_file(file_path)
        return len(audio) / 1000.0  # Convert milliseconds to seconds
    except Exception as e:
        print(f"Error getting audio duration: {str(e)}")
        return 0


def estimate_gcp_costs(files):
    """
    Estimate GCP costs for transcribing audio files.

    Args:
        files (list): List of file paths

    Returns:
        list: List of tuples containing (filename, duration, cost)
    """
    estimates = []
    total_cost = 0
    total_duration = 0

    print("\nGCP Speech-to-Text Cost Estimates:")
    print("-" * 80)
    print(f"{'File':<40} {'Duration':<15} {'Cost (USD)':<15}")
    print("-" * 80)

    for file_path in files:
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            continue

        duration = get_audio_duration(file_path)
        cost, billable_duration = calculate_gcp_cost(duration)

        filename = os.path.basename(file_path)
        print(
            f"{filename:<40} {duration:>6.1f}s ({billable_duration:>3.0f}s) ${cost:>8.3f}"
        )

        estimates.append((filename, duration, cost))
        total_cost += cost
        total_duration += duration

    print("-" * 80)
    print(f"{'Total:':<40} {total_duration:>6.1f}s         ${total_cost:>8.3f}")
    print("-" * 80)

    return estimates


def create_gcp_bucket():
    """Create a new GCP bucket with a UUID name."""
    storage_client = storage.Client()
    bucket_name = f"audio-transcribe-{uuid.uuid4()}"

    try:
        bucket = storage_client.create_bucket(bucket_name, location="US")
        print(f"Created bucket: {bucket_name}")
        return bucket_name
    except google_exceptions.Conflict:
        # In the unlikely event of a UUID collision, try again
        return create_gcp_bucket()
    except Exception as e:
        print(f"Error creating bucket: {str(e)}")
        sys.exit(1)


def delete_gcp_bucket(bucket_name):
    """Delete a GCP bucket and all its contents."""
    storage_client = storage.Client()
    try:
        bucket = storage_client.get_bucket(bucket_name)

        # Delete all objects in the bucket
        blobs = bucket.list_blobs()
        for blob in blobs:
            blob.delete()

        # Delete the bucket
        bucket.delete()
        print(f"Deleted bucket: {bucket_name}")
    except Exception as e:
        print(f"Error deleting bucket: {str(e)}")


def upload_to_gcs(bucket_name, source_file_path):
    """Upload file to Google Cloud Storage."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    blob_name = f"audio_files/{uuid.uuid4()}/{os.path.basename(source_file_path)}"
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(source_file_path)

    return f"gs://{bucket_name}/{blob_name}"


def delete_from_gcs(gcs_uri):
    """Delete file from Google Cloud Storage after processing."""
    storage_client = storage.Client()
    bucket_name = gcs_uri.split("/")[2]
    blob_name = "/".join(gcs_uri.split("/")[3:])

    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.delete()


def convert_audio_for_gcp(file_path):
    """Convert audio file to proper format for GCP Speech-to-Text API."""
    temp_wav = "temp_audio_file.wav"
    try:
        # Convert to WAV with proper specifications
        file_extension = os.path.splitext(file_path)[1].lower()
        if file_extension == ".mp3":
            audio = AudioSegment.from_mp3(file_path)
        elif file_extension == ".m4a":
            audio = AudioSegment.from_file(file_path, format="m4a")
        else:
            raise ValueError(f"Unsupported file format: {file_extension}")

        # Convert to mono and set sample rate to 16000 Hz (recommended by GCP)
        audio = audio.set_channels(1)
        audio = audio.set_frame_rate(16000)

        # Export as 16-bit PCM WAV
        audio.export(
            temp_wav,
            format="wav",
            parameters=["-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000"],
        )
        return temp_wav
    except Exception as e:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
        raise Exception(f"Audio conversion error: {str(e)}")


def format_timestamp(seconds):
    """
    Convert seconds to HH:MM:SS.mmm format.

    Args:
        seconds (float): Time in seconds

    Returns:
        str: Formatted timestamp
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds_remainder = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds_remainder:06.3f}"


def transcribe_with_gcp(file_path, bucket_name, pbar):
    """Transcribe using Google Cloud Speech-to-Text API with word timestamps."""
    temp_wav = None
    try:
        pbar.set_description("Converting audio")
        temp_wav = convert_audio_for_gcp(file_path)
        pbar.update(10)

        pbar.set_description("Uploading to GCS")
        gcs_uri = upload_to_gcs(bucket_name, temp_wav)
        pbar.update(20)

        client = speech_v1.SpeechClient()
        audio = speech_v1.RecognitionAudio(uri=gcs_uri)

        config = speech_v1.RecognitionConfig(
            encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="en-US",
            enable_automatic_punctuation=True,
            enable_word_time_offsets=True,  # Enable word-level timestamps
            audio_channel_count=1,
        )

        pbar.set_description("Transcribing")
        operation = client.long_running_recognize(config=config, audio=audio)
        pbar.update(30)

        pbar.set_description("Processing")
        result = operation.result()
        pbar.update(30)

        # Process results with timestamps
        transcript = ""
        current_line = ""
        current_line_start = None

        for result in result.results:
            alternative = result.alternatives[0]

            # Process each word in the alternative
            for word_info in alternative.words:
                word = word_info.word
                start_time = word_info.start_time.total_seconds()
                end_time = word_info.end_time.total_seconds()

                # Start a new line if this is the first word or if enough time has passed
                if current_line_start is None:
                    current_line_start = start_time
                    current_line = f"[{format_timestamp(start_time)}] {word}"
                else:
                    # Add word to current line
                    current_line += f" {word}"

                # If we hit a punctuation mark or significant pause, end the line
                if (word[-1] in ".!?") or (
                    word_info.end_time.total_seconds() - start_time > 5
                ):
                    transcript += f"{current_line} [{format_timestamp(end_time)}]\n"
                    current_line = ""
                    current_line_start = None

            # Don't forget to add the last line if it's not empty
            if current_line:
                transcript += f"{current_line} [{format_timestamp(end_time)}]\n"

        # Cleanup
        pbar.set_description("Cleaning up")
        delete_from_gcs(gcs_uri)
        pbar.update(10)

        return transcript

    except Exception as e:
        return f"GCP transcription error: {str(e)}"
    finally:
        if temp_wav and os.path.exists(temp_wav):
            os.remove(temp_wav)


# def transcribe_with_gcp(file_path, bucket_name, pbar):
#     """Transcribe using Google Cloud Speech-to-Text API."""
#     temp_wav = None
#     try:
#         pbar.set_description("Converting audio")
#         temp_wav = convert_audio_for_gcp(file_path)
#         pbar.update(10)

#         pbar.set_description("Uploading to GCS")
#         gcs_uri = upload_to_gcs(bucket_name, temp_wav)
#         pbar.update(20)

#         client = speech_v1.SpeechClient()
#         audio = speech_v1.RecognitionAudio(uri=gcs_uri)

#         config = speech_v1.RecognitionConfig(
#             encoding=speech_v1.RecognitionConfig.AudioEncoding.LINEAR16,
#             sample_rate_hertz=16000,
#             language_code="en-US",
#             enable_automatic_punctuation=True,
#             audio_channel_count=1,
#         )

#         pbar.set_description("Transcribing")
#         operation = client.long_running_recognize(config=config, audio=audio)
#         pbar.update(30)

#         pbar.set_description("Processing")
#         result = operation.result()
#         pbar.update(30)

#         # Combine all transcriptions
#         transcript = ""
#         for result in result.results:
#             transcript += result.alternatives[0].transcript + "\n"

#         # Cleanup
#         pbar.set_description("Cleaning up")
#         delete_from_gcs(gcs_uri)
#         pbar.update(10)

#         return transcript

#     except Exception as e:
#         return f"GCP transcription error: {str(e)}"
#     finally:
#         if temp_wav and os.path.exists(temp_wav):
#             os.remove(temp_wav)


def transcribe_with_free_api(file_path, pbar):
    """Transcribe using free Speech Recognition API."""
    temp_wav = "temp_audio_file.wav"

    try:
        # Check internet connection
        try:
            requests.get("http://www.google.com", timeout=5)
        except requests.exceptions.RequestException:
            return "Error: No internet connection"

        pbar.set_description("Converting audio")
        pbar.update(20)

        # Validate file format before conversion
        file_extension = os.path.splitext(file_path)[1].lower()
        if file_extension not in [".mp3", ".m4a"]:
            raise ValueError(f"Unsupported file format: {file_extension}")

        # Convert to WAV
        if file_extension == ".mp3":
            audio = AudioSegment.from_mp3(file_path)
        else:  # .m4a
            audio = AudioSegment.from_file(file_path, format="m4a")

        audio.export(temp_wav, format="wav", parameters=["-ac", "1", "-ar", "44100"])
        pbar.update(20)

        recognizer = r.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True

        pbar.set_description("Transcribing")
        with r.AudioFile(temp_wav) as source:
            pbar.update(20)
            audio_data = recognizer.record(source)
            pbar.update(20)

            text = recognizer.recognize_google(audio_data)
            pbar.update(20)
            return text

    except ValueError as e:
        raise e
    except Exception as e:
        return f"Free API error: {str(e)}"
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)


def save_transcription(text, output_path):
    """Save transcribed text to a file."""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Transcription saved to: {output_path}")
    except Exception as e:
        print(f"Error saving transcription: {str(e)}")


def main():
    args = parse_arguments()
    bucket_name = None

    try:
        # If using GCP, verify setup
        if args.api == "gcp":
            print("Verifying credentials file")
            gcp_ok, gcp_msg = check_gcp_setup()
            if not gcp_ok:
                print(gcp_msg)
                sys.exit(1)

            # Show cost estimate
            estimates = estimate_gcp_costs(args.files)

            if args.estimate_only:
                return

            # Create a new bucket
            print("\nCreating bucket")
            bucket_name = create_gcp_bucket()

        # Process each file
        for file_path in args.files:
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                continue

            print(f"\nProcessing: {file_path}")
            output_path = os.path.splitext(file_path)[0] + ".txt"

            with tqdm(total=100, unit="%") as pbar:
                if args.api == "gcp":
                    text = transcribe_with_gcp(file_path, bucket_name, pbar)
                else:
                    text = transcribe_with_free_api(file_path, pbar)

                save_transcription(text, output_path)

    finally:
        # Clean up GCP resources
        if args.api == "gcp" and bucket_name:
            print("\nCleaning up GCP resources...")
            delete_gcp_bucket(bucket_name)


if __name__ == "__main__":
    main()
