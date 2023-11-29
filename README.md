# Translated vocabulary Anki deck generator
A set of Python scripts to automatically generate an Anki deck for quickly learning foreign languages.
No longer are you stuck with learning words and phrases that are outdated and irrelevant!
These scripts take a personal (tagged) English vocabulary as input, and will use Deepl, Google Translate and Google TTS to translate and pronounce each entry. You therefore have 100% control over the words and phrases you want to learn and can maximize learning efficiency.

To make it easier to spot any mistakes, the output translation is translated back into a verification language of choice (your mother tongue is easiest). From the combined inputs and outputs, a bidirectional Anki deck is then created that shows the input entry, the translations, the TTS pronunciation, and the back-translation into the verification language.

So far, I have only tested these scripts to create a Greek vocabulary deck.

# Instructions
Create a file `.deepl_auth` and paste your Deepl API authentication token in there.
Create a `vocab.csv`, or use mine (though the point is using the words you use in your daily life, which will not 100% overlap with mine).
Then run `translate.py` and get the output deck.

Happy learning!


# Future improvements
- At some point I'll need to update my deck as I add more words to my vocabulary. This would currently require re-translating the entire existing vocabulary, which is a waste of time and compute. I want to add an update function that only obtains translations for newly added vocabulary entries.
- Google Translate supports many more languages than Deepl does, so depending on the language you're trying to learn the current code may not work for you. It'd be nice to make Deepl translation optional, so that more people can benefit from just the Google Translate functionality.
- It would be amazing to add support for verb conjugations, but manually adding those is an absolute pain.
Depending on the language of interest, it may be possible to use some conjugation website to automatically get all conjugations for a given verb.
