import datetime
import json
import math
import shutil
import string
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import deepl
import genanki
import googletrans
from gtts import gTTS
from tqdm import tqdm

# These are the only ones I'm interested for now, but both Deepl and
# Google Translate offer many options.
LANGUAGE_NAMES = {
    "EL": "Greek",
    "EN": "English",
    "ES": "Spanish",
    "NL": "Dutch",
    "PT": "Portuguese",
}


def load_vocab(filepath: Path) -> tuple[dict[int, str], dict[int, list[str]]]:
    """Loads the vocabulary entries and tags from the provided CSV filepath."""
    input_vocab = filepath.read_text().strip().splitlines()

    vocab_dict, tag_dict = {}, {}
    for line in input_vocab:
        # Allow for comments
        if line.startswith("#"):
            continue
        index, phrase, *tags = line.strip().split("\t")
        vocab_dict[int(index)] = phrase
        tag_dict[int(index)] = tags

    return vocab_dict, tag_dict


def translate_deepl(
    input_vocab: dict[int, str],
    target_language: str,
    source_language: str = "EN",
    verification_language: str = "EN",
) -> dict[int, tuple[str, str]]:
    """Translates the input vocabulary to the target language and verification
    language using Deepl.
    Uses a Deepl API key that should be stored at `.deepl_auth`.
    """
    output_vocab = {}

    # Separate function to translate a single phrase so we can multithread
    def translate_phrase(args):
        id, phrase = args

        deepl_translator = deepl.Translator(
            auth_key=Path(".deepl_auth").read_text().strip()
        )

        deepl_result = deepl_translator.translate_text(
            phrase,
            source_lang=source_language,
            target_lang=target_language,
            split_sentences=0,
        )

        verification_result = deepl_translator.translate_text(
            deepl_result.text,
            source_lang=target_language,
            target_lang=verification_language,
            split_sentences=0,
        )

        output_vocab[id] = (deepl_result.text, verification_result.text)

    with ThreadPoolExecutor() as executor:
        for _ in tqdm(
            executor.map(translate_phrase, input_vocab.items()),
            desc="Obtaining Deepl translations...",
            total=len(input_vocab),
        ):
            # We only loop to get a nice progress bar
            pass

    return output_vocab


def translate_google(
    input_vocab: dict[int, str], target_language: str, source_language: str = "EN"
) -> dict[int, str]:
    """Batch-translates the entire input vocabulary to the target language using
    Google Translate."""
    google_translator = googletrans.Translator()
    values = list(input_vocab.values())
    batch_size = 20
    start_idx = 0
    translations = []

    # Translate in batches of 20 phrases and add outputs to translations list
    for start_idx in tqdm(
        range(0, len(values), batch_size),
        desc="Obtaining batch Google translations...",
        total=math.ceil(len(values) / batch_size),
    ):
        batch_translations = google_translator.translate(
            values[start_idx : start_idx + batch_size],
            source=source_language.lower(),
            dest=target_language.lower(),
        )
        translations.extend(batch_translations)
        start_idx += batch_size

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
    vocab: dict[int, str], language: str, output_dir: Path
) -> dict[int, dict]:
    """Use gTTS to obtain TTS samples for the entire vocabulary. Downloads MP3 files to
    the specified folder and returns the vocab with references to those files."""
    lang = language.lower()

    vocab_with_prounciations = vocab.copy()
    for id, value in tqdm(
        vocab.items(), desc="Obtaining pronunciations...", total=len(vocab)
    ):
        speak = gTTS(text=value[language], lang=lang, slow=False)
        path = str(output_dir.joinpath(f"{id}.mp3"))
        speak.save(path)
        vocab_with_prounciations[id]["pronunciation_file"] = path

    return vocab_with_prounciations


def create_anki_deck(
    translated_vocab: dict[int, dict],
    target_language: str,
    source_language: str = "EN",
    verification_language: str = "EN",
    add_reverse_cards: bool = True,
    output_file: Path = Path("Output", "output.apkg"),
    deck_id: int = 180347320,
):
    language_name = LANGUAGE_NAMES[target_language]
    source_language_name = LANGUAGE_NAMES[source_language]
    verification_language_name = LANGUAGE_NAMES[verification_language]

    model = genanki.Model(
        model_id=1607392319,
        name="Translated Vocab Flashcards",
        fields=[
            {"name": source_language_name},
            {"name": language_name},
            {"name": verification_language_name},
            {"name": "SoundFile"},
        ],
        templates=[
            # One card from source language to target language
            {
                "name": f"{source_language_name} -> {language_name}",
                "qfmt": string.Template(
                    "{{$source}}<br/>({{$verification}})"
                ).substitute(
                    source=source_language_name,
                    verification=verification_language_name,
                ),
                "afmt": string.Template(
                    '{{FrontSide}}<hr id="answer">{{$language_name}}<br/>{{SoundFile}}'
                ).substitute(language_name=language_name),
            }
        ],
        css=".card { font-family: arial; font-size: 24px; text-align: center; color: black; background-color: white;}",
    )

    # And another card from target language to source language
    if add_reverse_cards:
        model.templates.append(
            {
                "name": f"{language_name} -> {source_language_name}",
                "qfmt": string.Template(
                    "{{$language_name}}<br/>{{SoundFile}}"
                ).substitute(language_name=language_name),
                "afmt": string.Template(
                    '{{FrontSide}}<hr id="answer">{{$source}}<br/>({{$verification}})'
                ).substitute(
                    source=source_language_name,
                    verification=verification_language_name,
                ),
            }
        )

    deck = genanki.Deck(
        deck_id=deck_id,
        name=f"Translated {language_name} vocabulary",
        description=(
            f"Automatically translated English <-> {language_name} vocabulary "
            "using Deepl and Google Translate."
        ),
    )

    for id, entry in translated_vocab.items():
        note = genanki.Note(
            model=model,
            fields=[
                entry[source_language],
                entry[target_language],
                entry[verification_language],
                f'[sound:{Path(entry["pronunciation_file"]).name}]',
            ],
            tags=entry["tags"],
            guid=id,
        )
        deck.add_note(note)

    package = genanki.Package(deck)
    package.media_files = [v["pronunciation_file"] for v in translated_vocab.values()]
    package.write_to_file(output_file)

    return deck_id


def main():
    # Change these according to your needs. TODO: make CLI
    target_language = "EL"
    verification_language = "NL"
    source_language = "EN"
    vocab_file = Path("Examples", "vocab.csv")

    output_name = (
        f"{source_language}_{target_language}"
        + f"_{datetime.datetime.now().strftime('%y_%m_%d_%H_%M_%S')}"
    )
    output_dir = Path("Output")
    temp_dir = output_dir.joinpath(output_name)
    temp_dir.mkdir(exist_ok=True, parents=True)

    input_vocab, tags = load_vocab(vocab_file)

    # Do the translation work
    google_output = translate_google(
        input_vocab, target_language=target_language, source_language=source_language
    )
    deepl_output = translate_deepl(
        input_vocab,
        target_language=target_language,
        source_language=source_language,
        verification_language=verification_language,
    )

    # Postprocess results
    results = {}
    assert len(deepl_output) == len(google_output)
    for id, (deepl_translation, deepl_verification) in deepl_output.items():
        translation, verification = process_translations(
            deepl_translation, google_output[id], deepl_verification
        )

        results[id] = {
            source_language: input_vocab[id],
            target_language: translation,
            verification_language: verification,
            "tags": tags[id],
        }

    # Save JSON output before moving on to pronunciations, since the translations are the bottleneck.
    # If something goes wrong, at least the translations will be saved.
    temp_dir.joinpath("info.json").write_text(json.dumps(results, indent="\t"))
    print(f"Intermediate outputs saved in {(str(temp_dir))}.")

    # Obtain pronunciation sound files and add them to results dict.
    results = get_pronunciations(results, language=target_language, output_dir=temp_dir)

    # Update JSON with the newly added pronunciation files before moving on to Anki deck creation.
    # The JSON is easier to inspect and could be useful for non-Anki users as well.
    temp_dir.joinpath("info.json").write_text(json.dumps(results, indent="\t"))

    # Finally, create the actual Anki deck and save it to the output folder.
    deck_id = create_anki_deck(
        results,
        target_language=target_language,
        source_language=source_language,
        verification_language=verification_language,
        add_reverse_cards=True,
        output_file=output_dir.joinpath(f"{output_name}.apkg"),
    )

    # To clean things up, zip the JSON and all the sounds files together, and delete the temporary
    # directory.
    shutil.copy(vocab_file, temp_dir.joinpath("vocab.csv"))
    with open(temp_dir.joinpath("deck_id"), "w") as deck_id_file:
        deck_id_file.write(str(deck_id))
    shutil.make_archive(
        str(output_dir.joinpath(output_name)),
        format="zip",
        root_dir=temp_dir,
    )
    shutil.rmtree(temp_dir)
    print(f"Done! Anki deck saved to {str(output_dir)}.")


if __name__ == "__main__":
    main()
