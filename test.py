import json
from pathlib import Path

from gtts import gTTS

vocab = json.loads(Path("greek.json").read_bytes())

print(vocab)

for i, v in enumerate(vocab.values()):
    print(v["full"])
    speak = gTTS(text=v["greek"], lang="el", slow=False)
    speak.save(f"{i}.mp3")
