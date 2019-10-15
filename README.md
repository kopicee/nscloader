## nscloader

A quick and dirty interface for loading and tokenizing data from IMDA's 
Singapore [National Speech Corpus][1], Part 3 (conversational speech).

The `nscloader.CorpusLoader` class tries to pair the audio files (WAV) with 
their corresponding transcription files (TextGrid). It also tries to group the 
files into conversations based on their filenames (4 files per conversation: 
2 text, 2 audio). 

There's also the `nscloader.Conversation` class which will yield TextGrid
intervals from each of the 2 speakers' transcriptions, sorted chronologically.

`interval` contains a parser and tokenizer tailored to recognize the tagging
notation described in the NSC transcription guidelines.

### Documentation

Please refer to the docstrings in the source.

### Example

```py
from nscloader import CorpusLoader, Conversation
from nscloader.interval import Tag

# Note: this directory is the one that has the LEXICON, PART1, PART2, PART3

cor = CorpusLoader(r'path/to/corpus/root/dir')

# Let the module detect the TextGrids and their corresponding WAV files.
# Here you may receive some warnings here about failing to match some files.
# This is mostly due to there being two sets of audio recordings; IVR files
# won't match to a TextGrid because their name differs from the "conf_" format
# that their corresponding TextGrid files have.
# Future changes to this module may allow choosing between IVR/StandingMic and
# BoundaryMic/CloseMic files.

convos = cor.find_convo_pairs()   # {str: (wav1, tg1, wav2, tg2)}

# Loading conversation 3085.
# There are 2 speakers per conversation. When loading a conversation, we
# provide one TextGrid file and one WAV file per speaker, so 4 files total.
# Note that the conversation IDs are given as strings.

wav1, tg1, wav2, tg2 = convos['3085']
conv = Conversation(wav1, tg1, wav2, tg2)

# You can also use the splat operator to save some typing

conv2 = Conversation(*convos['conf_2501_2501'])

# The linearize() method will yield intervals from each file in the conversation
# ordered according to their starting timestamps (xmin). The file containing the
# interval is yielded together with the interval.

for file, iv in conv.linearize():
    # Print out intervals containing discourse particles, bracketed as []
    discourse_particle = Tag.DD
    for t in iv.tokens:
        if t.tag == discourse_particle:
            print(f'{file}  {iv.xmin:>.03f}  {t.content.upper():<4} {iv.text}')
```

[1]: https://www2.imda.gov.sg/NationalSpeechCorpus