import json
from pathlib import Path

import deepl
import googletrans
from tqdm import tqdm

# Change these four according to your needs
TARGET_LANGUAGE = "EL"  # or NL, ES or PT-PT (deepl)
LANGUAGE_NAME = "Greek"
VERIFICATION_LANGUAGE = "NL"
VERIFICATION_LANGUAGE_NAME = "Dutch"

deepl_translator = deepl.Translator(
    auth_key=Path(".deepl_auth").read_text().strip()
)
google_translator = googletrans.Translator()

input_vocab = json.loads(Path("Vocabs", "combined_vocab.json").read_text())

output_vocab = {}
for key in tqdm(list(input_vocab.keys())[:1]):
    value = input_vocab[key]
    full = value.get("full", key.capitalize())

    deepl_result = deepl_translator.translate_text(
        full,
        source_lang="EN",
        target_lang=TARGET_LANGUAGE,
        split_sentences=0,
        # formality="prefer_more", # or "prefer_less"
    )

    verification_result = deepl_translator.translate_text(
        deepl_result.text,
        source_lang=TARGET_LANGUAGE,
        target_lang=VERIFICATION_LANGUAGE,
        split_sentences=0,
    )

    # TODO: replace with bulk translate!!!
    google_result = google_translator.translate(
        full, source="en", dest=TARGET_LANGUAGE.lower()
    )

    # TODO: Do some postprocessing. In cases of two words with a slash, check
    # that they are actually different. Maybe compare gtrans and deepl results.
    output_vocab[key] = {
        "full": full,
        "tags": value["tags"],
        LANGUAGE_NAME.lower(): deepl_result.text,
        f"{LANGUAGE_NAME.lower()}_google": google_result.text,
        VERIFICATION_LANGUAGE_NAME.lower(): verification_result.text,
    }

    # TODO: rethink identifiers. Just use numeric. Have to link mp3 somehow.


sorted_dict = dict(
    sorted(output_vocab.items(), key=lambda item: item[1]["tags"])
)
Path(f"{LANGUAGE_NAME}.json").write_text(json.dumps(sorted_dict, indent="\t"))
