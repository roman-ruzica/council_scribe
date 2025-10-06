import logging

from fastapi import FastAPI
from mangum import Mangum
from dotenv import dotenv_values

config = dotenv_values("./.env")
logger = logging.getLogger()
logger.setLevel(logging.INFO)


app = FastAPI()
handler = Mangum(app)

import requests

url = "https://api.pyannote.ai/v1/diarize"
API_KEY = config['PYANNOTE_API_KEY']
file_url = config['TEST_URL_AUDIO']
webhook_url = 'https://webhook.site/3ed9f4b8-a132-48b8-b014-0bc5784b684c'
headers = {
   "Authorization": f"Bearer {API_KEY}"
}
data = {
    'webhook': webhook_url,
    'url': file_url
}
response = requests.post(url, headers=headers, json=data)

print(response.status_code)
# 200

print(response.json())


### also transcribe the thing

do

response_transcription = requests.post(url='http://localhost:5001/transcribe', )

@app.get("/")
async def root() -> str:

    return f"{response.json()}"
