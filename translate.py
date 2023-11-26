import json
from pathlib import Path

import deepl
import googletrans
from gtts import gTTS
from tqdm import tqdm

# These are the only ones I'm interested for now, but both Deepl and
# Google Translate offer many options.
LANGUAGE_NAMES = {
    "EL": "Greek",
    "ES": "Spanish",
    "PT-PT": "Portuguese",
    "PT": "Portuguese",
    "NL": "Dutch",
    "EN": "English",
}


def load_vocab(filepath: Path) -> tuple[dict[int, str], dict[int, list[str]]]:
    """Loads the vocabulary entries and tags from the provided CSV filepath."""
    input_vocab = filepath.read_text().strip().splitlines()

    vocab_dict, tag_dict = {}, {}
    for line in input_vocab[:5]:
        index, phrase, *tags = line.strip().split("\t")
        vocab_dict[int(index)] = phrase
        tag_dict[int(index)] = tags

    return vocab_dict, tag_dict


def translate_deepl(
    input_vocab: dict[int, str],
    target_language: str,
    verification_language: str = "EN",
) -> dict[int, tuple[str, str]]:
    """Translates the input vocabulary to the target language and verification
    language using Deepl.
    Uses a Deepl API key that should be stored at `.deepl_auth`.
    """
    deepl_translator = deepl.Translator(
        auth_key=Path(".deepl_auth").read_text().strip()
    )

    output_vocab = {}
    for id, phrase in tqdm(input_vocab.items(), desc="Obtaining Deepl translations..."):
        deepl_result = deepl_translator.translate_text(
            phrase,
            source_lang="EN",
            target_lang=target_language,
            split_sentences=0,
            # formality="prefer_more", # or "prefer_less"
        )

        verification_result = deepl_translator.translate_text(
            deepl_result.text,
            source_lang=target_language,
            target_lang=verification_language,
            split_sentences=0,
        )

        output_vocab[id] = (deepl_result.text, verification_result.text)

    return output_vocab


def translate_google(
    input_vocab: dict[int, str], target_language: str
) -> dict[int, str]:
    """Batch-translates the entire input vocabulary to the target language using
    Google Translate. Probably risky for large vocabularies, as you might get
    throttled or IP-banned."""
    google_translator = googletrans.Translator()
    print("Obtaining Google translations...")
    translations = google_translator.translate(
        list(input_vocab.values()), source="en", dest=target_language.lower()
    )

    return {
        id: translation.text
        for id, translation in zip(input_vocab.keys(), translations, strict=True)
    }


def process_translations(deepl: str, google: str, verification: str) -> tuple[str, str]:
    """Postprocess the translation results for a given phrase to remove duplicates."""
    unique_phrases = {}

    for part in deepl.split(" / "):
        if (p := part.lower()) not in unique_phrases:
            unique_phrases[p] = part

    for part in google.split(" / "):
        if (p := part.lower()) not in unique_phrases:
            unique_phrases[p] = part

    verification_phrases = {}
    for part in verification.split(" / "):
        if (p := part.lower()) not in verification_phrases:
            verification_phrases[p] = part

    return " / ".join(unique_phrases.values()), " / ".join(
        verification_phrases.values()
    )


def get_pronunciations(
    vocab: dict[int, str], language: str, output_dir: Path = Path("Sounds")
) -> dict[int, str]:
    """Use gTTS to obtain TTS samples for the entire vocabulary. Downloads MP3 files to
    the specified folder and returns references to those files."""
    output_dir = output_dir.joinpath(LANGUAGE_NAMES[language])
    output_dir.mkdir(exist_ok=True, parents=True)
    lang = language.lower()

    mp3_paths = {}
    # TODO: add timeout to prevent rate-limit and IP block?
    for id, phrase in tqdm(vocab.items(), desc="Obtaining pronunciations..."):
        speak = gTTS(text=phrase, lang=lang, slow=False)
        path = str(output_dir.joinpath(f"{id}.mp3"))
        speak.save(path)
        mp3_paths[id] = path

    return mp3_paths


def main():
    # Change these according to your needs
    target_language = "EL"
    verification_language = "NL"
    input_vocab, tags = load_vocab(Path("Vocabs", "english.csv"))

    # Do the translation work
    deepl_output = translate_deepl(
        input_vocab,
        target_language=target_language,
        verification_language=verification_language,
    )
    google_output = translate_google(input_vocab, target_language=target_language)

    results = {}
    assert len(deepl_output) == len(google_output)
    for id, (deepl_translation, deepl_verification) in deepl_output.items():
        google_translation = google_output[id]

        translation, verification = process_translations(
            deepl_translation, google_translation, deepl_verification
        )

        results[id] = {
            target_language: translation,
            verification_language: verification,
        }

    pronunciations = get_pronunciations(
        {k: v[target_language] for k, v in results.items()}, language=target_language
    )

    for id, p_file in pronunciations.items():
        results[id]["pronunciation_file"] = p_file

    print(results)


if __name__ == "__main__":
    # main()

    results = {
        0: {
            "EL": "Είναι / πρόκειται για",
            "NL": "Het is / gaat over",
            "pronunciation_file": "Sounds\\Greek\\0.mp3",
        },
        1: {
            "EL": "Συγχαρητήρια",
            "NL": "Gefeliciteerd",
            "pronunciation_file": "Sounds\\Greek\\1.mp3",
        },
        2: {
            "EL": "... μυρίζει σαν ...",
            "NL": "ruikt naar...",
            "pronunciation_file": "Sounds\\Greek\\2.mp3",
        },
        3: {
            "EL": "Εκτός από το / Εκτός",
            "NL": "Afgezien van de",
            "pronunciation_file": "Sounds\\Greek\\3.mp3",
        },
        4: {"EL": "Προς", "NL": "Naar", "pronunciation_file": "Sounds\\Greek\\4.mp3"},
    }

    # TODO: Generate Anki Deck!
