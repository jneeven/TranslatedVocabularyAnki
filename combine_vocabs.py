import json
from pathlib import Path

spanish_vocab = json.loads(Path("Vocabs", "spanish_vocab.json").read_bytes())
portuguese_vocab = json.loads(
    Path("Vocabs", "portuguese_vocab.json").read_bytes()
)
untranslated_vocab = (
    Path("Vocabs", "vocab.csv").read_text().strip().splitlines()
)


# Convert all vocab words to lower case and strip article
def transform_key(key):
    lower = key.lower()
    if lower.startswith("the "):
        lower = lower[4:]

    return lower


# Start by processing Spanish vocab
combined_dict = {}
for key, value in spanish_vocab.items():
    # Store original key as "full" value
    value["full"] = key
    # Store value under transformed key
    combined_dict[transform_key(key)] = value

# Then integrate Portuguese vocab
for key, value in portuguese_vocab.items():
    new_key = transform_key(key)

    # Make sure an entry exists so we don't have to distinguish between words
    # that already existed in Spanish and those that did not.
    if new_key not in combined_dict:
        combined_dict[new_key] = {"full": key, "tags": []}

    # Portuguese vocab has no tags, so the only thing to insert is the
    # translation.
    combined_dict[new_key]["portuguese"] = value["portuguese"]

# And finally the untranslated vocab
for word in untranslated_vocab:
    key = transform_key(word)

    if key not in combined_dict:
        combined_dict[key] = {
            "full": word,
            "tags": [],
        }

# Sort by tags and save as JSON
sorted_dict = dict(
    sorted(combined_dict.items(), key=lambda item: item[1]["tags"])
)
Path("Vocabs", "combined_vocab.json").write_text(
    json.dumps(sorted_dict, indent=4)
)
