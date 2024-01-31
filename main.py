import qi
import subprocess
from naoqi import ALProxy
import os
import time
import threading
import speech_recognition as sr
import json
import requests
import time
import langid
class Main:
    def __init__(self, session, audio_proxy):
        self.session = session
        self.memory = self.session.service("ALMemory")
        self.tts = self.session.service("ALTextToSpeech")
        self.audio_recorder = audio_proxy
        self.lock = threading.Lock()
        self.recording = False
        self.robot_ip = "192.168.5.30"  
        self.robot_audio_directory = "/home/nao/recordings/"
        self.local_audio_directory = "/home/cc-admin/Documents/naorecordings/"
        self.scp_password = "nao"

        self.subscriber = self.memory.subscriber("FrontTactilTouched")
        self.subscriber.signal.connect(self.onHeadButtonPressed)
        self.recognizer = sr.Recognizer()

    def perform_speech_recognition(self, wav_file):
        r = sr.Recognizer()
        with sr.WavFile(wav_file) as source:
            audio = r.record(source)

        try:
            openai_api_key = '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'
            transcribe = r.recognize(audio)
            print("User's input:", transcribe)

            weather_api_key = '545a9518e75a51e99cf13bcdccdf46ae'
            weather_url = 'http://api.openweathermap.org/data/2.5/weather?q=Amsterdam&units=metric&appid={}'.format(weather_api_key)
            response = requests.get(weather_url)
            weather_data = response.json()
            description = weather_data['weather'][0]['description']
            temperature = weather_data['main']['temp']
            humidity = weather_data['main']['humidity']
            wind_speed = weather_data['wind']['speed']

            rain_info = weather_data.get('rain', {}).get('1h', 0)
            t = time.localtime()
            current_time = time.strftime("%H:%M", t)
            system_message = "The weather in Amsterdam is currently {} with a temperature of {} degrees Celsius. " \
                            "The humidity is {}%, and the wind speed is {} m/s. There is {} mm of rain in the last hour. " \
                            "You are a robot named Poly, when you give numbers or percentages you round them off. you have 3 fingers on each hand and wear a colourful dress. Do not mention the weather unless you are asked to. You are helpful and like to joke around. give nice and clear answers. the time right now is {}. If you are asked to speak in a language you will and you wont reply with any other language.".format(
                                description, temperature, humidity, wind_speed, rain_info, current_time)

            print(system_message)
            curl_command = [
                'curl',
                'https://api.openai.com/v1/chat/completions',
                '-H', 'Content-Type: application/json',
                '-H', 'Authorization: Bearer {}'.format(openai_api_key),
                '-d', json.dumps({
                    "model": "gpt-3.5-turbo-1106",
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": transcribe},
                    ]            
                })
            ]

            detected_language = langid.classify(transcribe)
            print()
            language = "English"

            if detected_language == "nl":
                language = "Dutch"

            self.tts.setLanguage(language)
            process = subprocess.Popen(curl_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, error = process.communicate()

            if process.returncode == 0:
                json_output = json.loads(output)

                for choice in json_output.get('choices', []):
                    content = choice.get('message', {}).get('content', '')
                    self.tts.say(content)
                    print("Choice Content: {}".format(content))
                return json_output
            else:
                print("Error: {}".format(error))
                return None
            
        except sr.UnknownValueError:
            print("Could not understand audio")
            self.tts.say("Im sorry but i did not understand. Please try again!")
            return None
        except sr.RequestError as e:
            print("Error with the recognition service; {}".format(e))
            return None




    def convert_ogg_to_wav(self, ogg_file, wav_file):
        ffmpeg_command = 'ffmpeg -i {} -acodec pcm_s16le -ar 44100 -threads 0 -preset ultrafast {}'.format(ogg_file, wav_file)
        try:
            subprocess.check_output(ffmpeg_command, shell=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            print("Error during conversion:", e.output.decode(errors='ignore'))



    def onHeadButtonPressed(self, value):
        if value > 0:
            print("Head button pressed!")

            if not self.recording:
                print("Start recording...")
                self.tts.say("Yes?")
                self.audio_recorder.startMicrophonesRecording(
                    self.robot_audio_directory + "test.ogg")
                self.recording = True
            else:
                print("Stop recording...")
                self.audio_recorder.stopMicrophonesRecording()

                threading.Thread(target=self.process_audio).start()
                self.recording = False
                self.tts.say("Hmm. Let me think about that!")

    def process_audio(self):
        with self.lock:
            self.transfer_audio_file(self.robot_audio_directory + "test.ogg")

            wav_file_path = os.path.join(self.local_audio_directory, "cv_test.wav")


            threading.Thread(target=self.perform_speech_recognition, args=(wav_file_path,)).start()

            threading.Thread(target=self.convert_audio_file, args=(wav_file_path,)).start()

    def convert_audio_file(self, wav_file_path):
        ogg_file_path = os.path.join(self.local_audio_directory, "test.ogg")
        self.convert_ogg_to_wav(ogg_file_path, wav_file_path)
        print("File converted to WAV:", wav_file_path)


    def transfer_audio_file(self, file_path):
        wav_file_path = os.path.join(self.local_audio_directory, "cv_test.wav")
        ogg_file_path = os.path.join(self.local_audio_directory, "test.ogg")

        if os.path.exists(wav_file_path):
            os.remove(wav_file_path)

        if os.path.exists(ogg_file_path):
            os.remove(ogg_file_path)

        scp_command = 'sshpass -p {} scp nao@{}:{} {}'.format(
            self.scp_password, self.robot_ip, file_path, self.local_audio_directory
        )

        subprocess.check_call(scp_command, shell=True)

        self.convert_ogg_to_wav(ogg_file_path, wav_file_path)
        print("File converted to WAV:", wav_file_path)


if __name__ == "__main__":
    app = qi.Application()
    session = app.session
    session.connect("tcp://192.168.5.30:9559")

    audio_proxy = ALProxy("ALAudioDevice", "192.168.5.30", 9559)  

    head_button_example = Main(session, audio_proxy)

    try:
        app.run()
    except KeyboardInterrupt:
        head_button_example.subscriber.signal.disconnect(head_button_example.onHeadButtonPressed)
        print("Unsubscribed from FrontTactilTouched event.")
