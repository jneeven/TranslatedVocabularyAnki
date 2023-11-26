import json
import string
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
    source_language: str = "EN",
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
            source_lang=source_language,
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
    input_vocab: dict[int, str], target_language: str, source_language: str = "EN"
) -> dict[int, str]:
    """Batch-translates the entire input vocabulary to the target language using
    Google Translate. Probably risky for large vocabularies, as you might get
    throttled or IP-banned."""
    google_translator = googletrans.Translator()
    print("Obtaining Google translations...")
    translations = google_translator.translate(
        list(input_vocab.values()),
        source=source_language.lower(),
        dest=target_language.lower(),
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
    source_language = "EN"
    input_vocab, tags = load_vocab(Path("Vocabs", "english.csv"))

    output_dir = Path("Output")
    output_dir.mkdir(exist_ok=True)

    # # Do the translation work
    # deepl_output = translate_deepl(
    #     input_vocab,
    #     target_language=target_language,
    #     source_language=source_language,
    #     verification_language=verification_language,
    # )
    # google_output = translate_google(
    #     input_vocab, target_language=target_language, source_language=source_language
    # )

    # # Postprocess results
    # results = {}
    # assert len(deepl_output) == len(google_output)
    # for id, (deepl_translation, deepl_verification) in deepl_output.items():
    #     translation, verification = process_translations(
    #         deepl_translation, google_output[id], deepl_verification
    #     )

    #     results[id] = {
    #         source_language: input_vocab[id],
    #         target_language: translation,
    #         verification_language: verification,
    #         "tags": tags[id],
    #     }

    # # Save JSON output before moving on to pronunciations, since the translations are the bottleneck.
    # output_dir.joinpath("output.json").write_text(json.dumps(results, indent="\t"))
    # print(f"Intermediate outputs saved in {(str(output_dir))}.")

    # # Obtain pronunciation sound files and add them to results dict.
    # pronunciations = get_pronunciations(
    #     {k: v[target_language] for k, v in results.items()}, language=target_language
    # )
    # for id, p_file in pronunciations.items():
    #     results[id]["pronunciation_file"] = p_file

    # # Update JSON with the newly added pronunciation files before moving on to Anki deck creation.
    # # The JSON is easier to inspect and could be useful for non-Anki users as well.
    # output_dir.joinpath("output.json").write_text(json.dumps(results, indent="\t"))

    results = json.loads(output_dir.joinpath("output.json").read_text())

    # Finally, create the actual Anki deck and save it to the output folder as well.
    create_anki_deck(
        results,
        target_language=target_language,
        source_language=source_language,
        verification_language=verification_language,
        output_dir=output_dir,
    )

    print(f"Done! JSON and Anki deck saved to {str(output_dir)}.")


def create_anki_deck(
    translated_vocab: dict[int, dict],
    target_language: str,
    source_language: str = "EN",
    verification_language: str = "EN",
    output_dir: Path = Path("Output"),
):
    language_name = LANGUAGE_NAMES[target_language]
    source_language_name = LANGUAGE_NAMES[source_language]
    verification_language_name = LANGUAGE_NAMES[verification_language]

    # TODO: Make font bigger and center text on the card!! Check existing decks for specs.
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
            {
                "name": "Card 1",
                "qfmt": string.Template(
                    "{{$source}}<br/>({{$verification}})"
                ).substitute(
                    source=source_language_name,
                    verification=verification_language_name,
                ),
                "afmt": string.Template(
                    '{{FrontSide}}<hr id="answer">{{$language_name}}<br/>{{SoundFile}}'
                ).substitute(language_name=language_name),
            },
        ],
    )

    deck = genanki.Deck(
        deck_id=180347320,
        name=f"{language_name} vocabulary",
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
    package.write_to_file(output_dir.joinpath("output.apkg"))


if __name__ == "__main__":
    main()
