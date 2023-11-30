import datetime
import json
import math
import shutil
import string
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Optional
from zipfile import ZipFile

import deepl
import genanki
import googletrans
import typer
from gtts import gTTS
from tqdm import tqdm

app = typer.Typer()


@lru_cache()
def get_language_names() -> dict:
    """Get dictionary mapping of language codes to full language names."""
    deepl_translator = deepl.Translator(
        auth_key=Path(".deepl_auth").read_text().strip()
    )

    language_names = {}
    for language in deepl_translator.get_source_languages():
        language_names[language.code.lower()] = language.name

    for language in deepl_translator.get_target_languages():
        language_names[language.code.lower()] = language.name

    return language_names


def check_languages(
    source_language: str,
    target_language: str,
    verification_language: Optional[str] = None,
):
    """Verifies that all configured languages are correct and turns them to lowercase."""
    source_language = source_language.lower()
    target_language = target_language.lower()
    verification_language = (
        verification_language.lower()
        if verification_language is not None
        else source_language
    )

    deepl_translator = deepl.Translator(
        auth_key=Path(".deepl_auth").read_text().strip()
    )
    deepl_source_languages = {
        l.code.lower(): l.name for l in deepl_translator.get_source_languages()
    }
    deepl_target_languages = {
        l.code.lower(): l.name for l in deepl_translator.get_target_languages()
    }

    if source_language not in deepl_source_languages:
        raise ValueError(
            f"'{source_language}' is not a valid Deepl source language! Available options:\n"
            + json.dumps(deepl_source_languages, indent=4, sort_keys=True)
        )
    if target_language not in deepl_target_languages:
        raise ValueError(
            f"'{target_language}' is not a valid Deepl target language! Available options:\n"
            + json.dumps(deepl_target_languages, indent=4, sort_keys=True)
        )
    if verification_language not in deepl_target_languages:
        raise ValueError(
            f"Verification language '{verification_language}' is not a valid Deepl target language!"
            " Available options:\n"
            + json.dumps(deepl_target_languages, indent=4, sort_keys=True)
        )

    if source_language not in googletrans.LANGUAGES:
        raise ValueError(
            f"Source language '{source_language}' is not supported by Google Translate! "
            "Available options:\n"
            + json.dumps(googletrans.LANGUAGES, indent=4, sort_keys=True)
        )
    if target_language.split("-")[0] not in googletrans.LANGUAGES:
        raise ValueError(
            f"Target language '{target_language}' is not supported by Google Translate! "
            "Available options:\n"
            + json.dumps(googletrans.LANGUAGES, indent=4, sort_keys=True)
        )
    if verification_language.split("-")[0] not in googletrans.LANGUAGES:
        raise ValueError(
            f"Verification language '{verification_language}' is not supported by Google Translate!"
            " Available options:\n"
            + json.dumps(googletrans.LANGUAGES, indent=4, sort_keys=True)
        )

    return source_language, target_language, verification_language


def load_vocab(filepath: Path) -> tuple[dict[int, str], dict[int, list[str]]]:
    """Loads the vocabulary entries and tags from the provided CSV filepath."""
    input_vocab = filepath.read_text().strip().splitlines()

    vocab_dict, tag_dict = {}, {}
    for line in input_vocab:
        # Allow for comments
        if line.startswith("#"):
            continue
        index, phrase, *tags = line.strip().split("\t")
        index = int(index)
        if index in vocab_dict:
            raise ValueError(
                f"ID {index} of '{line}' is used twice! "
                f"First occurrence:\n'{index}\t{vocab_dict[index]}'"
            )
        vocab_dict[index] = phrase

        for tag in tags:
            if " " in tag:
                raise ValueError(
                    f"Tag '{tag}' of phrase with ID {index} contains a space!"
                    " Anki does not support this."
                )
        tag_dict[index] = tags

    return vocab_dict, tag_dict


def translate_deepl(
    input_vocab: dict[int, str],
    target_language: str,
    source_language: str,
    verification_language: str,
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
    input_vocab: dict[int, str], target_language: str, source_language: str
) -> dict[int, str]:
    """Batch-translates the entire input vocabulary to the target language using
    Google Translate."""
    google_translator = googletrans.Translator()
    values = list(input_vocab.values())
    batch_size = 20
    start_idx = 0
    translations = []

    # Google Translate doesn't distinguish between e.g. EN-US and EN-GB
    target_language = target_language.split("-")[0].lower()
    source_language = source_language.split("-")[0].lower()

    # Translate in batches of 20 phrases and add outputs to translations list
    for start_idx in tqdm(
        range(0, len(values), batch_size),
        desc="Obtaining batch Google translations...",
        total=math.ceil(len(values) / batch_size),
    ):
        batch_translations = google_translator.translate(
            values[start_idx : start_idx + batch_size],
            source=source_language,
            dest=target_language,
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


def obtain_translations(
    vocab: dict, source_language: str, target_language: str, verification_language: str
):
    # Do the translation work
    google_output = translate_google(
        vocab, target_language=target_language, source_language=source_language
    )
    deepl_output = translate_deepl(
        vocab,
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
            source_language: vocab[id],
            target_language: translation,
            verification_language: verification,
        }

    return results


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
    *,
    target_language: str,
    source_language: str,
    verification_language: str,
    deck_id: int,
    output_file: Path,
    add_reverse_cards: bool = True,
    deck_name: Optional[str] = None,
) -> dict:
    language_name = get_language_names()[target_language]
    source_language_name = get_language_names()[source_language]
    verification_language_name = get_language_names()[verification_language]

    model = genanki.Model(
        model_id=deck_id,  # To make sure model is unique for each deck
        name=f"{source_language_name}<->{language_name} Translated Vocab Flashcards",
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

    deck_name = deck_name or f"Translated {language_name} vocabulary"
    deck = genanki.Deck(
        deck_id=deck_id,
        name=deck_name,
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
            guid=f"{deck_id}_{id}",
        )
        deck.add_note(note)

    package = genanki.Package(deck)
    package.media_files = [v["pronunciation_file"] for v in translated_vocab.values()]
    package.write_to_file(output_file)

    return {
        "deck_id": deck_id,
        "deck_name": deck_name,
        "source_language": source_language,
        "target_language": target_language,
        "verification_language": verification_language,
    }


def create_zip_and_clean(
    *,
    vocab_path: Path,
    deck_info: dict,
    output_path: Path,
    temp_dir: Path,
):
    """To clean things up, zip the JSON and all the sound files together, and delete the temporary
    directory"""
    shutil.copy(vocab_path, temp_dir.joinpath("vocab.csv"))
    temp_dir.joinpath("info.json").write_text(json.dumps(deck_info))
    shutil.make_archive(
        str(output_path),
        format="zip",
        root_dir=temp_dir,
    )
    shutil.rmtree(temp_dir)


@app.command()
def create(
    vocab_path: Path = typer.Option(
        ..., help="Path to a vocabulary CSV file, e.g. Examples/vocab.csv"
    ),
    target_language: str = typer.Option(
        ..., help="The language to translate the vocabulary to."
    ),
    verification_language: str = typer.Option(
        None,
        help="The language used to backtranslate the translations to, so you can see whether the "
        "translations make any sense. Defaults to the source language.",
    ),
    source_language: str = typer.Option(
        "en", help="The language of the provided vocabulary file."
    ),
    deck_id: int = typer.Option(
        ...,
        help="Unique identifier for this Anki deck, e.g. 123456. Whenever you want to update a deck"
        " in Anki rather than create a new one, you should use the same identifier as you did last"
        " time. If you forgot the ID you used last time, check `info.json` in the generated zip "
        "file!",
    ),
    deck_name: Optional[str] = typer.Option(
        None, help="Name of the created deck as will be shown in Anki."
    ),
    add_reverse_cards: bool = typer.Option(
        True,
        help="Whether to add a duplicate of each card, but in the other direction. For example, if"
        "my source language is English and my target is Greek, this option will not only add "
        "English->Greek cards, but also Greek->English. Enabled by default.",
    ),
    output_dir: Path = typer.Option(Path("Output")),
):
    """Translates the vocabulary provided at `--vocab-path` to the target language, obtains TTS
    pronunciations and generates an Anki deck."""

    source_language, target_language, verification_language = check_languages(
        source_language, target_language, verification_language
    )
    output_name = (
        f"{source_language}_{target_language}"
        + f"_{datetime.datetime.now().strftime('%y_%m_%d_%H_%M_%S')}"
    )
    temp_dir = output_dir.joinpath(output_name)
    temp_dir.mkdir(exist_ok=True, parents=True)

    input_vocab, tags = load_vocab(vocab_path)

    # Translate the vocabulary
    results = obtain_translations(
        input_vocab,
        source_language=source_language,
        target_language=target_language,
        verification_language=verification_language,
    )
    for id, t in tags.items():
        results[id]["tags"] = t

    # Save JSON output before moving on to pronunciations, since the translations are the bottleneck.
    # If something goes wrong, at least the translations will be saved.
    temp_dir.joinpath("data.json").write_text(json.dumps(results, indent="\t"))

    # Obtain pronunciation sound files and add them to results dict.
    results = get_pronunciations(results, language=target_language, output_dir=temp_dir)

    # Update JSON with the newly added pronunciation files before moving on to Anki deck creation.
    # The JSON is easier to inspect and could be useful for non-Anki users as well.
    temp_dir.joinpath("data.json").write_text(json.dumps(results, indent="\t"))

    # Finally, create the actual Anki deck and save it to the output folder.
    deck_info = create_anki_deck(
        results,
        target_language=target_language,
        source_language=source_language,
        verification_language=verification_language,
        add_reverse_cards=add_reverse_cards,
        output_file=output_dir.joinpath(f"{output_name}.apkg"),
        deck_id=deck_id,
        deck_name=deck_name,
    )

    create_zip_and_clean(
        vocab_path=vocab_path,
        deck_info=deck_info,
        output_path=output_dir.joinpath(output_name),
        temp_dir=temp_dir,
    )
    print(f"Done! Anki deck saved to {str(output_dir)}.")


@app.command()
def update(
    vocab_path: Path = typer.Option(
        ..., help="Path to a vocabulary CSV file, e.g. Examples/vocab.csv"
    ),
    deck_zip_path: Path = typer.Option(
        ..., help="Path to the zip file corresponding to earlier version of this deck"
    ),
    add_reverse_cards: bool = typer.Option(
        True,
        help="Whether to add a duplicate of each card, but in the other direction. For example, if"
        "my source language is English and my target is Greek, this option will not only add "
        "English->Greek cards, but also Greek->English. Enabled by default.",
    ),
    output_dir: Path = typer.Option(Path("Output")),
):
    """Compares the provided vocabulary file to the existing deck, and generates a new verson of the
    deck using the existing translations and sound files where possible."""

    extract_dir = output_dir.joinpath("extracted")
    with ZipFile(deck_zip_path, "r") as zip_file:
        zip_file.extractall(extract_dir)

    deck_info = json.loads(Path(extract_dir.joinpath("info.json")).read_text())
    source_language = deck_info["source_language"]
    target_language = deck_info["target_language"]
    verification_language = deck_info["verification_language"]

    output_name = (
        f"{source_language}_{target_language}"
        + f"_{datetime.datetime.now().strftime('%y_%m_%d_%H_%M_%S')}"
    )
    temp_dir = output_dir.joinpath(output_name)
    temp_dir.mkdir(exist_ok=True, parents=True)

    # Load both the new vocab and the previous vocab
    input_vocab, new_tags = load_vocab(vocab_path)
    old_vocab = json.loads(extract_dir.joinpath("data.json").read_text())

    # Create dictionary of only the new and changed items
    new_vocab = {}
    old_vocab_to_copy = {}
    new_id_counter = 0
    new_phrase_counter = 0
    for id, new_entry in input_vocab.items():
        str_id = str(id)
        if str_id not in old_vocab:
            new_vocab[id] = new_entry
            new_id_counter += 1
            continue

        old_entry = old_vocab[str_id]
        # If the phrase hasn't changed, we can simply copy all existing output, since the
        # translation and pronunciation won't have changed either
        if old_entry[source_language] == new_entry:
            old_vocab_to_copy[id] = old_entry
        else:
            new_vocab[id] = new_entry
            new_phrase_counter += 1

    print(
        f"Found {len(new_vocab)} changes in vocabulary that will require new translations: "
        f"{new_id_counter} new entries and {new_phrase_counter} modified entries."
    )

    # Correct sound paths because this time we're loading them from the ZIP
    for id, entry in old_vocab_to_copy.items():
        entry["pronunciation_file"] = str(
            extract_dir.joinpath(Path(entry["pronunciation_file"]).name)
        )

    # Obtain new translations & pronunciation sound files
    new_translations = obtain_translations(
        new_vocab,
        source_language=source_language,
        target_language=target_language,
        verification_language=verification_language,
    )
    new_translations = get_pronunciations(
        new_translations, language=target_language, output_dir=temp_dir
    )

    # Combine with existing outputs and add tags
    # TODO: copy sound files to temp dir so they will be zipped into the end result!
    results = old_vocab_to_copy
    results.update(new_translations)
    for id, t in new_tags.items():
        results[id]["tags"] = t

    # Save JSON before moving on to Anki deck creation.
    # The JSON is easier to inspect and could be useful for non-Anki users as well.
    temp_dir.joinpath("data.json").write_text(json.dumps(results, indent="\t"))

    # Finally, create the actual Anki deck and save it to the output folder.
    new_deck_info = create_anki_deck(
        results,
        target_language=target_language,
        source_language=source_language,
        verification_language=verification_language,
        add_reverse_cards=add_reverse_cards,
        output_file=output_dir.joinpath(f"{output_name}.apkg"),
        deck_id=deck_info["deck_id"],
        deck_name=deck_info["deck_name"],
    )

    # If everything went right, the deck info should stay the same. We've only updated.
    assert new_deck_info == deck_info

    create_zip_and_clean(
        vocab_path=vocab_path,
        deck_info=deck_info,
        output_path=output_dir.joinpath(output_name),
        temp_dir=temp_dir,
    )
    shutil.rmtree(extract_dir)
    print(f"Done! Anki deck saved to {str(output_dir)}.")


if __name__ == "__main__":
    app()
