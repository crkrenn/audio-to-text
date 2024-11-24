import speech_recognition as r
from pydub import AudioSegment
import os
import sys
import subprocess
import platform

def check_ffmpeg():
    """
    Check if FFmpeg is installed and accessible.
    Returns bool and string message.
    """
    try:
        # Different command syntax for Windows vs Unix-like systems
        if platform.system() == 'Windows':
            result = subprocess.run(['where', 'ffmpeg'], capture_output=True, text=True)
        else:  # macOS and Linux
            result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
        
        if result.returncode == 0:
            return True, "FFmpeg is installed and accessible"
        
        # Prepare OS-specific installation instructions
        if platform.system() == 'Windows':
            install_msg = (
                "FFmpeg not found. Please install it using one of these methods:\n"
                "1. Using Chocolatey: choco install ffmpeg\n"
                "2. Download from https://ffmpeg.org/download.html\n"
                "3. Or use Windows Subsystem for Linux (WSL)"
            )
        elif platform.system() == 'Darwin':  # macOS
            install_msg = (
                "FFmpeg not found. Please install it using one of these methods:\n"
                "1. Using Homebrew: brew install ffmpeg\n"
                "2. Using MacPorts: sudo port install ffmpeg"
            )
        else:
            install_msg = (
                "FFmpeg not found. Please install it using your package manager:\n"
                "Ubuntu/Debian: sudo apt-get install ffmpeg\n"
                "Fedora: sudo dnf install ffmpeg"
            )
        return False, install_msg
    
    except Exception as e:
        return False, f"Error checking FFmpeg: {str(e)}"

def transcribe_audio(file_path):
    """
    Transcribe audio from MP3 or M4A files to text.
    
    Args:
        file_path (str): Path to the audio file
        
    Returns:
        str: Transcribed text or error message
    """
    # Get file extension
    file_extension = os.path.splitext(file_path)[1].lower()
    
    # Create a temporary WAV file name
    temp_wav = "temp_audio_file.wav"
    
    try:
        # Convert to WAV based on file type
        if file_extension == '.mp3':
            audio = AudioSegment.from_mp3(file_path)
        elif file_extension == '.m4a':
            audio = AudioSegment.from_file(file_path, format='m4a')
        else:
            raise ValueError(f"Unsupported file format: {file_extension}")
        
        # Export as WAV (required for speech recognition)
        audio.export(temp_wav, format="wav")
        
        # Initialize recognizer
        recognizer = r.Recognizer()
        
        # Perform the transcription
        with r.AudioFile(temp_wav) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            return text
            
    except Exception as e:
        return f"Error processing file: {str(e)}"
        
    finally:
        # Clean up temporary file
        if os.path.exists(temp_wav):
            os.remove(temp_wav)

def save_transcription(text, output_path):
    """
    Save transcribed text to a file.
    
    Args:
        text (str): Transcribed text
        output_path (str): Path to save the text file
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Transcription saved to: {output_path}")
    except Exception as e:
        print(f"Error saving transcription: {str(e)}")

def main():
    # Check if FFmpeg is installed
    ffmpeg_ok, ffmpeg_msg = check_ffmpeg()
    if not ffmpeg_ok:
        print(ffmpeg_msg)
        sys.exit(1)
    
    # Check if files were provided as arguments
    if len(sys.argv) < 2:
        print("Usage: python audio2text.py file1.mp3 file2.m4a ...")
        sys.exit(1)
    
    # Process each file provided in command line arguments
    for file_path in sys.argv[1:]:
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            continue
            
        print(f"\nProcessing: {file_path}")
        
        # Generate output filename by replacing the extension with .txt
        output_path = os.path.splitext(file_path)[0] + '.txt'
        
        # Perform transcription
        text = transcribe_audio(file_path)
        
        # Save the transcription
        save_transcription(text, output_path)

if __name__ == "__main__":
    main()
