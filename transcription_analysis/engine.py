# Imports the Google Cloud client library
import json
import io
import os
import tempfile
from pydub import AudioSegment
import speech_recognition as sr
from multiprocessing.dummy import Pool

from google.cloud import language
from google.cloud.language import enums
from google.cloud.language import types
from google.cloud import speech
from google.cloud.speech import enums as speech_enums
from google.cloud.speech import types as speech_types
from google.protobuf.json_format import MessageToJson

from transcription_analysis.beans import ErrorBean, AnalyzedAudioBean, AnalyzedTextBean


audio_directory_path = os.path.join('.', 'audio_files')
tmp_path = os.path.join('.', 'tmp')


# given a text and a method, retreive the sentiment of that text using method modal
def handle_text_analysis_request(text, method):

    global value
    if (text is not None) and (method is not None):
        if method == "google":
            try:
                resp = get_text_sentiment_values(text)
                text_bean = AnalyzedTextBean(resp)
                value = json.dumps(text_bean.__dict__)
            except Exception as e:
                print (str(e))
                value = get_error_message(str(e))
        else:
            value = get_error_message("The method specified is not supported")
    else:
        value = get_error_message("'text' and 'method' were not passed in the argument")

    return value


# given a file on instance of UploadedFile, transcribe and analyze the audio
def handle_audio_analysis_request(file_obj):
    try:
        file_name = convert_audio_to_wav(file_obj)
        if file_name is not None:
            # Get the duration of the audio file
            sound = AudioSegment.from_wav(file_name)
            duration = sound.duration_seconds
            # Based on the duration, transcribe the audio files
            if duration < 60:
                text = transcribe_short_audio(file_name)
            else:
                text = transcribe_audio_fast(file_name, name=file_obj.name)

                # Do a sentiment analysis on the transcribed text
            resp = get_text_sentiment_values(text)
            # return the answer in a JSON format
            audio_bean = AnalyzedAudioBean(audio_text=text, audio_analysis=resp)
            resp = json.dumps(audio_bean.__dict__)
            return resp
        else:
            return get_error_message("File was not provided or the provided"
                                     " file is not in the following format (WAV, MP3, OGG)")
    except Exception as e:
        return get_error_message(str(e))


# Convert the uploaded audio file to wav if they are not and store them under the audio files folder
def convert_audio_to_wav(file):
    if file is None:
        return

    file_name = file.name
    tempf, tempfn = tempfile.mkstemp()

    try:
        for chunk in file.chunks():
            os.write(tempf, chunk)
        print(type(tempf), tempf, type(tempfn), tempfn)

        file_path = os.path.join(audio_directory_path, os.path.splitext(file_name)[0] + ".wav")
        print(file_path)
        # Encoding Audio file into Wav
        if file_name.endswith('.mp3'):
            sound = AudioSegment.from_mp3(tempfn)
            sound.export(file_path, format="wav")
        elif file_name.endswith('.ogg'):
            sound = AudioSegment.from_ogg(tempfn)
            sound.export(file_path, format="wav")
        elif file_name.endswith('.wav'):
            sound = AudioSegment.from_wav(tempfn)
            sound.export(file_path, format="wav")

        return file_path
    except:
        raise Exception("Problem with the input file %s" % file.name)
    finally:
        os.close(tempf)

    return None


# trascribe audios less than one minute with wav format
def transcribe_short_audio(file_path):
    # Instantiates a client
    client = speech.SpeechClient()

    # Loads the audio into memory
    with io.open(file_path, 'rb') as audio_file:
        # encode
        content = encode_audio(audio_file)
        audio = speech_types.RecognitionAudio(content=content)

    config = speech_types.RecognitionConfig(
        encoding=speech_enums.RecognitionConfig.AudioEncoding.LINEAR16,
        language_code='en-US')

    # Detects speech in the audio file
    response = client.recognize(config, audio)

    text = ""
    for result in response.results:
        text += result.alternatives[0].transcript

    return text


# Transcribe audio with any length, the way this is done is by first, dividing the audio file into smalled chucks
# of 45 seconds, each chuck is transcribed in a separate thread and then assembled in an ordered way at the end
def transcribe_audio_fast(file_path, name="tmp"):
    # Open google APPLICATION CREDENTIALS which is stored in the enviroment variables
    with open(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]) as f:
        GOOGLE_CLOUD_SPEECH_CREDENTIALS = f.read()

    sound = AudioSegment.from_wav(file_path)

    r = sr.Recognizer()

    # initialize data
    data = []

    # Calculate the voice chucks in miliseconds in the following format (chuck_begin, chuck_end)
    # Append this into the data list
    duration = sound.duration_seconds * 1000
    interval = 45 * 1000
    begin = 0
    if interval < duration:
        end = interval
    else:
        end = duration

    while duration > 0:
        data.append((begin, end))

        # update
        duration -= interval
        begin = end
        if duration < interval:
            end = (end + duration)
        else:
            end = (end + interval)

    # This inner method will be run in a separat thread
    def transcribe(input):
        idx, value = input
        # Reteive the chunck from the audio and store it in the tmp file
        sound_interval = sound[value[0]:value[1]]
        audio_segment_path = os.path.join(tmp_path, name + str(idx) + ".wav")
        sound_interval.export(audio_segment_path, format="wav")

        with sr.AudioFile(audio_segment_path) as source:
            audio = r.record(source)

        # Transcribe audio file
        text = r.recognize_google_cloud(audio, credentials_json=GOOGLE_CLOUD_SPEECH_CREDENTIALS)
        print(text)
        # delete

        #
        return {
            "idx": idx,
            "text": text
        }

    pool = Pool(20)
    all_text = pool.map(transcribe, enumerate(data))
    pool.close()
    pool.join()

    transcript = ""
    for t in sorted(all_text, key=lambda x: x['idx']):
        # Format time as h:m:s - 30 seconds of text
        transcript += t['text'] + ","

    return transcript


def get_text_sentiment_values(text):
    # Instantiates a client
    client = language.LanguageServiceClient()

    # The text to analyze
    document = types.Document(
        content=text,
        type=enums.Document.Type.PLAIN_TEXT)

    # Detects the sentiment of the text
    features = {
        "extract_entities": True,
        "extract_document_sentiment": True,
        "extract_entity_sentiment": True,
    }

    result = client.annotate_text(document=document, features=features)

    return MessageToJson(result)


def get_error_message(error):
    error_obj = ErrorBean(error)
    return json.dumps(error_obj.__dict__)


# Encode the audio function
def encode_audio(audio):
    audio_content = audio.read()
    # return base64.b64encode(audio_content)
    return audio_content