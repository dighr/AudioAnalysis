#!/usr/bin/python

import requests
import os
import sys
import urllib.request
from urllib.error import HTTPError
import .transcription_analysis.engine as engine

# directory name where the audio files be downloaded
dirname = os.path.join('.', 'tmp')

# downloads audio file into a directory
def download_file(url):
    filename = url.split('/')[-1]
    file_path = os.path.join(dirname, filename)

    # checks and creates the directory if not exists 
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    # checkes if the file has already been downloaded
    # if found skips downloading
    if os.path.isfile(file_path):
        print('Skipping... File already exists.')
        return 'found' 

    r = requests.get(url, stream = True)
    with open(file_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size = 1024): 
            if chunk:
                f.write(chunk)
                f.flush()
    return file_path

# checks if all the required arguments provided
if len(sys.argv) != 3:
    print('Please provide arguments. Usage: retrieve_kobo_audio.py <kpiAssetID> <apiToken>')
    sys.exit(1)

# parse asset ID and api token from CL args.
kpiAssetID = str(sys.argv[1])
apiToken = 'Token ' + str(sys.argv[2])

url = 'https://kf.kobotoolbox.org/api/v2/assets/' + kpiAssetID + '/data.json'
headers = { 'Authorization': apiToken }

try:
    response = requests.get(url, headers=headers)
    # If the response was successful, no Exception will be raised
    response.raise_for_status()
except HTTPError as http_err:
    print(f'HTTP error occurred: {http_err}')
except Exception as err:
    print(f'Other error occurred: {err}')
else:
    # converts response as JSON object
    response = response.json()
    # iterates the response body to retrieve all the download urls and
    # downloads the audio files.
    for (key, value) in response.items():
        if key == 'results':
            for item in value:
                for (key, value) in item.items():
                    if key == '_attachments':
                        for item in value:
                            for (key, value) in item.items():
                                if key == 'download_url' and (value.endswith('.mp3') or value.endswith('.wav') or value.endswith('.m4a') or value.endswith('.ogg') or value.endswith('.flac')):                                
                                    audio_url = value
                                    file = download_file(audio_url)
                                    if file == 'found':
                                        pass
                                    elif file is not None:
                                        filename = file.split('/')[-1]
                                        print(filename + " ===> Status: Download completed.")
                                        print("Starting to transcribe ...")
                                        engine.handle_audio_transcription_request(file, 'en-US')
                                    else:
                                        print("Status: Failed to download, try again.")
                                        