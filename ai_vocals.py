from pydub import AudioSegment
from pydub.playback import play
import yt_dlp
import os
import subprocess
from pathlib import Path
from rvcgui import selected_model, vc_single
import requests
from audio_separator.separator import Separator
import boto3
import zipfile
import creds

def createAIVocals(link, song_name, model_name):
    print(link, song_name, model_name)
    
    os.makedirs("split_audio", exist_ok=True)
    proposed_audio_path = f'songs/{song_name}.mp3'

    # If song already processed
    if not os.path.isfile(proposed_audio_path):
         # 1. Use youtube link to download mp3 or wav file
        audio_path = downloadSong(link, song_name)
        print(audio_path)

        # 2. Separate instrumentals from vocals using Demucs output structure
        vocals_path, instrumentals_path = seperateAudio(audio_path)

        # Log for confirmation
        print(vocals_path, instrumentals_path)
    else:
        vocals_path = f"split_audio/htdemucs/{song_name}/vocals.wav"
        instrumentals_path = f"split_audio/htdemucs/{song_name}/no_vocals.wav"


    # 3. Download model from AWS S3 bucket and save it to models/{model_name}/
    #    Also download hubert_base.pt if it doesn't exist
    ensure_model_and_hubert(creds.aws_s3_bucket_name, model_name)
        

    # 4. Use vocals and artist of choice to create AI Vocals
    path = f'models/{model_name}/'

    model_path = ''
    index_path = ''

    for file in os.listdir(path):
        if file.endswith('.pth'):
            model_path = os.path.join(path, file)
        if file.endswith('.index'):
            index_path = os.path.join(path, file)

    output_file = f'ai_vocal_output/{model_name}_{song_name}_raw_RVC.wav'

    result = createAIAudio(vocals_path, model_name, model_path, index_path, output_file)
    print(result)

    if result == "Voice converstion failed":
        return result

    # 5. Combine vocals and instrumentals back together
    path = combineVocalsAndInstrumentals(output_file, instrumentals_path, model_name, song_name)
    print(path)

    # 6. Send song to front end
    return path

def downloadSong(link, name):
    parent_dir = './songs'
    os.makedirs(parent_dir, exist_ok=True)

    # Final mp3 output path
    final_path = os.path.join(parent_dir, f"{name}.mp3")

    # Use yt_dlp to download audio
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(parent_dir, f'{name}.%(ext)s'),
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }
        ],
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([link])

    return final_path


import os
import subprocess

def seperateAudio(audio_path):
    output_dir = "split_audio"
    os.makedirs(output_dir, exist_ok=True)

    # Demucs outputs to split_audio/separated/demucs/
    subprocess.run([
        "demucs", "--two-stems", "vocals", "--out", output_dir, audio_path
    ], check=True)

    filename = os.path.splitext(os.path.basename(audio_path))[0]
    demucs_out = os.path.join(output_dir, "htdemucs", filename)

    vocals_path = os.path.join(demucs_out, "vocals.wav")
    instrumentals_path = os.path.join(demucs_out, "no_vocals.wav")

    return vocals_path, instrumentals_path


def createAIAudio(vocals_path, model_name, model_path, index_path, output_file):
    selected_model(model_name)
    input_audio = vocals_path
    f0_pitch = 0
    f0_method = 'crepe'
    file_index = index_path
    index_rate = 0.4
    crepe_hop_length = 128
    result, audio_opt = vc_single(
                0, input_audio, f0_pitch, None, f0_method, file_index, index_rate,crepe_hop_length, output_file)
    
    # It worked
    if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
        return result
    else:
        return "Voice converstion failed"


def combineVocalsAndInstrumentals(vocals_path, instrumentals_path, model_name, song_name):
    vocals = AudioSegment.from_file(vocals_path)
    instrumentals = AudioSegment.from_file(instrumentals_path)

    combined = vocals.overlay(instrumentals)

    path = f'static/output/{model_name}_{song_name}_RVC.mp3'
    combined.export(path, format='mp3')
    return path

def ensure_model_and_hubert(bucket_name, model_name):
    os.environ["AWS_ACCESS_KEY_ID"] = creds.aws_s3_access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = creds.aws_s3_secret_access_key
    s3 = boto3.client('s3')
    
    # 1. Download model zip if not already extracted
    model_dir = f'models/{model_name}'
    model_zip_path = f'models/{model_name}.zip'
    if not os.path.exists(model_dir):
        print(f"Model {model_name} not found locally. Downloading...")
        os.makedirs('models', exist_ok=True)
        s3.download_file(bucket_name, f'models/{model_name}.zip', model_zip_path)

        print("Extracting model...")
        with zipfile.ZipFile(model_zip_path, 'r') as zip_ref:
            zip_ref.extractall('models')

        os.remove(model_zip_path)
        print(f"Model {model_name} ready.")

    # 2. Download hubert_base.pt if not already in root
    hubert_path = "hubert_base.pt"
    if not os.path.exists(hubert_path):
        print("Downloading hubert_base.pt...")
        s3.download_file(bucket_name, 'models/hubert_base.pt', hubert_path)
        print("hubert_base.pt ready.")

def move_separated_files(vocals_path, instrumentals_path, output_dir="split_audio", song_name=""):
    os.makedirs(output_dir, exist_ok=True)

    # Sanitize and rename output files
    base = song_name.strip().replace("/", "_").replace(" ", " ")
    vocals_target = f"{output_dir}/{base}_(Vocals)_UVR_MDXNET_KARA_2.wav"
    instrumentals_target = f"{output_dir}/{base}_(Instrumental)_UVR_MDXNET_KARA_2.wav"

    print(f"[DEBUG] Moving vocals: {vocals_path} → {vocals_target}")
    print(f"[DEBUG] Moving instrumentals: {instrumentals_path} → {instrumentals_target}")

    Path(vocals_path).rename(vocals_target)
    Path(instrumentals_path).rename(instrumentals_target)

    return vocals_target, instrumentals_target