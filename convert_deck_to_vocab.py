import json
from pathlib import Path

# text = Path("Decks", "Spanish Vocab.txt").read_text("utf-8")
text = Path("Decks", "Portu Vocab.txt").read_text("utf-8")

# Parse existing Spanish<->English or Portuguese<->English Anki Deck
vocab_dict = {}
for i, line in enumerate(text.splitlines()[3:]):
    portuguese, english, tags = line.split("\t")
    # Dirty fix for portuguese deck
    if i >= 32:
        p = portuguese
        portuguese = english
        english = p

    tags = tags.split(" ") if len(tags) > 0 else []
    vocab_dict[english] = {"portuguese": portuguese, "tags": tags}

# Sort by tags and save as JSON
sorted_dict = dict(sorted(vocab_dict.items(), key=lambda item: item[1]["tags"]))
Path("portuguese_vocab.json").write_text(json.dumps(sorted_dict, indent=4))
