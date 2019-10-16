"""
Quick 'n' dirty loader & tokenizer for Part 3 of IMDA's National Speech Corpus
(conversational data).

The National Speech Corpus is...

Example:

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

for iv in conv.linearize():
    # Print out intervals containing discourse particles, bracketed as []
    discourse_particle = Tag.DD
    for t in iv.tokens:
        if t.tag != discourse_particle:
            continue
        particle = t.text.upper()
        print(f'{iv.textgrid}  {iv.xmin:>.03f}  {particle:<4} {iv.text}')
"""


from collections import defaultdict
import os
import re
import warnings

from .interval import Interval


# Aliases for type annotation
Directory = str


def recursive_get_files(path):
    """Yields all files in the given path, including in subdirs"""
    _join = os.path.join
    for dirpath, _, filenames in os.walk(path):
        for file in filenames:
            yield _join(dirpath, file)


class CorpusLoader:
    """Helper for loading files from the National Speech Corpus"""
    CORPUS_STRUCTURE = {
        # 'LEXICON': {},
        # 'PART1': {
        #     'DATA': {},
        #     'DOC': {},
        # },
        # 'PART2': {
        #     'DATA': {},
        #     'DOC': {},
        # },
        'PART3': {
            'Audio Same BoundaryMic': {},
            'Audio Same CloseMic': {},
            'Audio Separate IVR': {},
            'Audio Separate StandingMic': {},
            'Scripts Same': {},
            'Scripts Separate': {},
        },
    }

    file_pattern_sameroom = re.compile(r'(\d{4})-[12]')
    file_pattern_seproom = re.compile(r'(conf_\d{4}_\d{4})_\d{8}')

    def __init__(self, rootdir: Directory):
        self.CORPUS_DIRECTORY = None
        self.file_cache = {}
        self.convos_cache = {}

        self.set_corpus_directory(rootdir)


    @classmethod
    def check_directory(cls, rootdir: Directory, expected_structure: dict):
        """FileNotFoundError if rootdir doesn't contain expected_structure"""
        _exists = os.path.exists
        _join = os.path.join

        for subdir_name, subdir_contents in expected_structure.items():
            here = _join(rootdir, subdir_name)
            if not _exists(here):
                raise FileNotFoundError(here)
            cls.check_directory(here, subdir_contents)


    def get_corpus_dir(self):
        if not self.CORPUS_DIRECTORY:
            self.set_corpus_directory(os.getcwd())
        return self.CORPUS_DIRECTORY


    def set_corpus_directory(self, path: Directory):
        try:
            self.check_directory(path, self.CORPUS_STRUCTURE)
            self.CORPUS_DIRECTORY = path
        except FileNotFoundError as e:
            err = (f'Failed to set corpus directory as {path} as it does not '
                   f'have the expected folder structure (missing folder "{e}")')
            raise FileNotFoundError(err)


    def _init_file_cache(self, extensions):
        """Inits the file cache, with one dict per file extension

        It is useful to use separate cache dicts for each extension due to
        naming conventions in the data files. For example, the transcription
        for XXXX.wav is named XXXX.TextGrid. We want to look up these two files
        using XXXX, so it is good to one dict each for WAV and TextGrid, sharing
        the same key for each audio-transcription pair.

        Arguments:
        extensions: list of str - Extensions among the data files that we want.
                                  Do not include the leading . of the extension.
        """
        self.file_cache = {ext: dict() for ext in extensions}


    def _push_file_cache(self, extension, filekey, filepath, raise_error=False):
        """Maps the given key to path in the cache dict for the extension

        Raises ValueError if filekey already has a record in the extension's
        cache, and if raise_error is True.

        Arguments:
        extension: str - Indicates which extension's cache this file belongs to.
                         This extension must be in the list provided to
                         _init_file_cache(). See that method for explanation.

        filekey: str - The name of the file, without the extension.

        filepath: str - Full, absolute path to the file.

        raise_error: bool - Whether errors when adding to the cache should be
                            raised or given as warnings.
        """
        if not self.file_cache:
            raise RuntimeError('must initialize file_cache first; see '
                               '_init_file_cache()')

        if extension not in self.file_cache:
            raise ValueError(f'invalid extension "{extension}"; cache only '
                             f'expects: {", ".join(self.file_cache)}')

        cache_ext = self.file_cache[extension]
        if filekey in cache_ext:
            err = ValueError(f'Duplicated file {filepath}; already exists at '
                             f'{cache_ext[filekey]})')
            err.filekey = filekey
            err.filepath = filepath
            if raise_error:
                raise err
            warnings.warn(err)

        else:
            cache_ext[filekey] = filepath

        return None


    def _cache_files(self, path: str, extensions: list):
        """Initializes and caches the location of data files

        See __init_file_cache() and _push_file_cache() for explanation of
        implementation.

        Arguments:
        path: str - Root directory containing the corpus data files.

        extensions: list of str - Extensions among the data files that we want.
                                  Do not include the leading . of the extension.
                                  See _init_file_cache() for details.
        """
        self._init_file_cache(extensions)

        _basename = os.path.basename

        for filepath in recursive_get_files(path):
            filename = _basename(filepath)
            *name_no_ext, ext = filename.lower().rsplit('.', 1)

            if not (name_no_ext and ext):
                continue
            elif ext not in self.file_cache:
                continue
            else:
                name_no_ext = name_no_ext[0]

            self._push_file_cache(extension=ext,
                                  filekey=name_no_ext,
                                  filepath=filepath)
        return self.file_cache


    def find_matches_textgrid_to_wav(self, raise_unmatched):
        """Gets paired audio-transcript files, and those that couldn't be paired

        This builds the cache of corpus data files grouped by file extension
        using _init_file_cache(). Pairs of audio (.wav) and transcription
        (.TextGrid) files are located by taking an intersection between the sets
        of keys within each extension's cache.

        See _init_file_cache() for an explanation of segregating the cache
        according to file extension.

        Arguments:
        raise_error: bool - Whether errors when building the file cache should
                            be raised or given as warnings.
        """
        cache = self._cache_files(self.CORPUS_DIRECTORY, ['wav', 'textgrid'])

        wav_keys = set(cache['wav'].keys())
        tg_keys = set(cache['textgrid'].keys())

        try:
            assert wav_keys == tg_keys

        except AssertionError:
            msg = ('failed to match some TextGrid files to WAV files or vice '
                   'versa')
            if raise_unmatched:
                raise AssertionError(msg)
            warnings.warn(msg)

        matches = {}
        for filename_no_ext in wav_keys.intersection(tg_keys):
            wavpath = cache['wav'][filename_no_ext]
            tgpath = cache['textgrid'][filename_no_ext]
            matches[filename_no_ext] = (wavpath, tgpath)

        diff = wav_keys.symmetric_difference(tg_keys)
        unmatched = dict(wav=[], textgrid=[])

        for ext, other_ext_keys in [('wav', tg_keys), ('textgrid', wav_keys)]:
            unmatched[ext] = [f'{file}.{ext.replace("textgrid", "TextGrid")}'
                              for file in diff
                              if file not in other_ext_keys]

        return matches, unmatched


    def find_convo_pairs(self, raise_unmatched=False):
        """Finds sets of 4 files that make up a conversation

        There are 2 speakers per conversation. When loading a conversation, we
        require one TextGrid file and one WAV file per speaker, or 4 files for
        each conversation.

        Each group of 4 files are assigned to a conversation ID, which is a
        substring common among each of the four files. This substring is
        located using regex: file_pattern_sameroom and file_pattern_seproom.

        The resulting mapping between each conversation ID and the 4 files
        associated with it is cached and returned by this function.

        Arguments:
        raise_error: bool - Whether errors when building the file cache should
                            be raised or given as warnings.
        """
        if self.convos_cache:
            return self.convos_cache

        matches, unmatched = self.find_matches_textgrid_to_wav(raise_unmatched)

        convos = defaultdict(list)

        # Create a conversation ID ("convokey") and collect files with names
        # beginning with the ID into a list.
        for filename_no_ext, (wavpath, tgpath) in matches.items():
            match = self.file_pattern_sameroom.match(filename_no_ext)
            if not match:
                match = self.file_pattern_seproom.match(filename_no_ext)
            if not match:
                err = f'unrecognized filename format: {filename_no_ext}'
                raise ValueError(err)

            # Extract convo ID from the regex match; push into list
            convokey = match.groups()[0]
            convos[convokey].append((wavpath, tgpath))

        # Combine the lists in the defaultdict[list] into a Map[str, tuple] for
        # immutability and to save RAM
        convos_dict = {}
        for convokey, speakerfiles in convos.items():
            num_speakers = len(speakerfiles)
            if num_speakers != 2:
                raise ValueError(f'expected two pairs of files per convo but '
                                 f'found {num_speakers} pairs for {convokey}')

            # [(wav1, tg1), (wav2, tg2)] -> (wav1, tg1, wav2, tg2)
            speaker1, speaker2 = speakerfiles
            convos_dict[convokey] = (*speaker1, *speaker2)

        # Cache the str-tuple map before returning it
        self.convos_cache = convos_dict
        return convos_dict


    def __repr__(self):
        return f'<CorpusLoader at {self.CORPUS_DIRECTORY}>'


class Conversation:
    """Loads and parses conversational data"""
    def __init__(self, wav1, textgrid1, wav2, textgrid2, key=None):
        self.textgrid1 = textgrid1
        self.wav1 = wav1
        self.textgrid2 = textgrid2
        self.wav2 = wav2
        self.key = key


    @property
    def files(self):
        return self.textgrid1, self.wav1, self.textgrid2, self.wav2


    @property
    def name(self):
        name = self.key
        if not name:
            name = ', '.join(map(os.path.basename, self.files))
        return name


    @classmethod
    def open_textgrid(cls, filepath, codecs=['utf-8', 'utf-8-sig']):
        """Reads the text from TextGrid file"""
        for enc in codecs:
            try:
                with open(filepath, 'r', encoding='utf-8-sig') as f:
                    rawtext = f.read()
                    break
            except UnicodeDecodeError:
                pass
        else:
            raise ValueError("couldn't open {} using codes: {}".format(
                filepath, ', '.join(codecs)))
        return rawtext


    @classmethod
    def generate_intervals(cls, filepath):
        """Opens a TextGrid file and parses it for intervals

        Yields interval.Interval objects.
        """
        rawtext = cls.open_textgrid(filepath)
        repatt = Interval.interval_grouped_pattern
        basename = os.path.basename(filepath)

        for ivtext, *_ in repatt.findall(rawtext):
            yield Interval.from_text(ivtext, textgrid=filepath)
        yield False


    def linearize(self):
        """Yield Intervals from the 2 TextGrids in chronological order"""
        gen1 = self.generate_intervals(self.textgrid1)
        gen2 = self.generate_intervals(self.textgrid2)

        iv1, iv2 = gen1.__next__(), gen2.__next__()

        while True:
            if iv1 == iv2 == False:
                raise StopIteration

            if iv1 and iv2:
                if iv1.xmin <= iv2.xmin:
                    yield iv1
                    iv1 = gen1.__next__()
                else:
                    yield iv2
                    iv2 = gen2.__next__()
                continue

            break

        # Either gen1 or gen2 depleted
        gen = gen1 if iv1 else gen2
        iv = iv1 or iv2

        # Yield the non-false item, then deplete its generator
        while iv:
            yield iv
            iv = gen.__next__()

        raise StopIteration


    def __repr__(self):
        return f'<Conversation: {self.name}>'
