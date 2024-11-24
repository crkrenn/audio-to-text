import pytest
import os
import json
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
from google.cloud import storage, speech_v1

# Import the script (assuming it's named audio_to_text.py)
import audio_to_text


@pytest.fixture
def test_file():
    """Fixture to ensure test audio file exists."""
    file_path = Path(__file__).parent / "this-is-a-test.m4a"
    if not file_path.exists():
        pytest.skip(f"Test file {file_path} not found")
    return str(file_path)


@pytest.fixture
def test_output():
    """Fixture to manage test output file."""
    output_path = Path(__file__).parent / "this-is-a-test.txt"
    # Clean up any existing output file
    if output_path.exists():
        output_path.unlink()
    yield str(output_path)
    # Clean up after test
    if output_path.exists():
        output_path.unlink()


@pytest.fixture
def gcp_credentials():
    """Fixture to check GCP credentials."""
    cred_path = Path(__file__).parent / "gcp-service-account-key.json"
    if not cred_path.exists():
        pytest.skip("GCP credentials file not found")
    return str(cred_path)


@pytest.fixture
def temp_wav_cleanup():
    """Fixture to clean up temporary WAV files."""
    yield
    temp_wav = Path(__file__).parent / "temp_audio_file.wav"
    if temp_wav.exists():
        temp_wav.unlink()


@pytest.fixture
def mock_args():
    """Fixture to mock command line arguments."""
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        yield mock_args


class TestAudioTranscription:
    def test_check_gcp_setup(self, gcp_credentials):
        """Test GCP credentials setup."""
        success, message = audio_to_text.check_gcp_setup()
        assert success, f"GCP setup failed: {message}"
        assert "verified successfully" in message

    def test_free_api_transcription(
        self, test_file, test_output, temp_wav_cleanup, mock_args
    ):
        """Test transcription using the free API."""
        # Set up mock arguments
        args = Mock()
        args.api = "free"
        args.files = [test_file]
        mock_args.return_value = args

        # Mock tqdm to avoid progress bar in tests
        with patch("tqdm.tqdm") as mock_progress:
            mock_progress.return_value.__enter__.return_value = Mock()

            # Run transcription
            audio_to_text.main()

            # Check output file exists and contains text
            assert os.path.exists(test_output), "Output file was not created"
            with open(test_output, "r", encoding="utf-8") as f:
                content = f.read()
            assert content.strip(), "Output file is empty"

    def test_gcp_api_transcription(
        self, test_file, test_output, gcp_credentials, mock_args
    ):
        """Test transcription using the GCP API."""
        # Set up mock arguments with all required attributes
        args = Mock()
        args.api = "gcp"
        args.files = [test_file]
        args.timestamps = False  # Add the timestamps parameter
        args.estimate_only = False  # Add estimate_only parameter
        mock_args.return_value = args

        # Add logging to help debug issues
        print(f"\nDebug: Test file path: {test_file}")
        print(f"Debug: Expected output path: {test_output}")

        # Mock tqdm to avoid progress bar in tests
        with patch("tqdm.tqdm") as mock_progress:
            mock_progress.return_value.__enter__.return_value = Mock()

            # Add error capture
            try:
                # Run transcription
                audio_to_text.main()

                # Check output file exists and contains text
                assert os.path.exists(test_output), "Output file was not created"

                # Verify file content
                with open(test_output, "r", encoding="utf-8") as f:
                    content = f.read()
                    print(f"Debug: Output file content length: {len(content)}")
                    assert content.strip(), "Output file is empty"

            except Exception as e:
                print(f"Debug: Exception occurred during test: {str(e)}")
                print(f"Debug: Current working directory: {os.getcwd()}")
                # List files in current directory
                print("Debug: Files in current directory:", os.listdir("."))
                raise

    # def test_gcp_api_transcription(
    #     self, test_file, test_output, gcp_credentials, mock_args
    # ):
    #     """Test transcription using the GCP API."""
    #     # Set up mock arguments
    #     args = Mock()
    #     args.api = "gcp"
    #     args.files = [test_file]
    #     mock_args.return_value = args

    #     # Mock tqdm to avoid progress bar in tests
    #     with patch("tqdm.tqdm") as mock_progress:
    #         mock_progress.return_value.__enter__.return_value = Mock()

    #         # Run transcription
    #         audio_to_text.main()

    #         # Check output file exists and contains text
    #         assert os.path.exists(test_output), "Output file was not created"
    #         with open(test_output, "r", encoding="utf-8") as f:
    #             content = f.read()
    #         assert content.strip(), "Output file is empty"

    def test_unsupported_file_format(self):
        """Test handling of unsupported file formats."""
        with pytest.raises(ValueError) as exc_info:
            with patch("tqdm.tqdm") as mock_progress:
                mock_progress.return_value.__enter__.return_value = Mock()
                audio_to_text.transcribe_with_free_api("test.xyz", Mock())
        assert "Unsupported file format" in str(exc_info.value)

    def test_file_not_found(self, mock_args):
        """Test handling of non-existent files."""
        non_existent_file = "non_existent_file.m4a"
        args = Mock()
        args.api = "free"
        args.files = [non_existent_file]
        mock_args.return_value = args

        with patch("builtins.print") as mock_print:
            audio_to_text.main()
            mock_print.assert_any_call(f"File not found: {non_existent_file}")

    # def test_gcp_bucket_lifecycle(self, gcp_credentials):
    #     """Test GCP bucket creation and deletion."""
    #     # Create a bucket
    #     bucket_name = audio_to_text.create_gcp_bucket()
    #     assert bucket_name.startswith("audio-transcribe-")

    #     # Verify bucket exists
    #     storage_client = storage.Client()
    #     bucket = storage_client.get_bucket(bucket_name)
    #     assert bucket.name == bucket_name

    #     # Delete bucket
    #     audio_to_text.delete_gcp_bucket(bucket_name)

    #     # Verify bucket is deleted
    #     with pytest.raises(Exception):
    #         storage_client.get_bucket(bucket_name)

    def test_gcp_bucket_lifecycle(self, gcp_credentials):
        """Test GCP bucket creation and deletion."""
        storage_client = None
        bucket_name = None
        try:
            # Create a bucket
            bucket_name = audio_to_text.create_gcp_bucket()
            assert bucket_name.startswith("audio-transcribe-")
            print(f"bucket_name: {bucket_name}")

            # Verify bucket exists
            storage_client = storage.Client()
            bucket = storage_client.get_bucket(bucket_name)
            print(f"bucket: {bucket}")
            assert bucket.name == bucket_name

            # Delete bucket
            audio_to_text.delete_gcp_bucket(bucket_name)

            # Verify bucket is deleted
            with pytest.raises(Exception):
                storage_client.get_bucket(bucket_name)

        except Exception as e:
            pytest.fail(f"Test failed: {str(e)}")

        finally:
            # Cleanup in case test fails midway
            if bucket_name and storage_client:
                try:
                    bucket = storage_client.get_bucket(bucket_name)
                    # Delete all objects in the bucket
                    blobs = bucket.list_blobs()
                    for blob in blobs:
                        blob.delete()
                    # Delete the bucket
                    bucket.delete()
                except Exception:
                    pass  # Bucket might already be deleted


class TestIntegration:
    def test_end_to_end_free_api(
        self, test_file, test_output, temp_wav_cleanup, mock_args
    ):
        """Integration test for end-to-end free API workflow."""
        args = Mock()
        args.api = "free"
        args.files = [test_file]
        args.timestamps = False  # Add the timestamps parameter
        args.estimate_only = False  # Add estimate_only parameter
        mock_args.return_value = args

        audio_to_text.main()

        assert os.path.exists(test_output)
        with open(test_output, "r", encoding="utf-8") as f:
            content = f.read()
            assert len(content) > 0

    def test_end_to_end_gcp_api(
        self, test_file, test_output, gcp_credentials, mock_args
    ):
        """Integration test for end-to-end GCP API workflow."""
        args = Mock()
        args.api = "gcp"
        args.files = [test_file]
        args.timestamps = False  # Add the timestamps parameter
        args.estimate_only = False  # Add estimate_only parameter
        mock_args.return_value = args

        audio_to_text.main()

        assert os.path.exists(test_output)
        with open(test_output, "r", encoding="utf-8") as f:
            content = f.read()
            assert len(content) > 0


def test_environment_setup():
    """Test environment setup and required dependencies."""
    # Test required packages are installed
    import speech_recognition
    import pydub
    from google.cloud import storage
    from google.cloud import speech_v1

    # Test audio file exists
    test_file = Path(__file__).parent / "this-is-a-test.m4a"
    assert test_file.exists(), "Test audio file not found"

    # Test GCP credentials exist
    cred_file = Path(__file__).parent / "gcp-service-account-key.json"
    assert cred_file.exists(), "GCP credentials file not found"
