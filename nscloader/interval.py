"""interval.py

API for TextGrid intervals. Mainly useful for tokenizing the interval text.
"""

from collections import namedtuple
from enum import Enum
import re
from typing import List, Optional, Pattern, Tuple


IntervalTuple = namedtuple('Interval', 'xmin, xmax, text, index, textgrid, raw')

class Tag(Enum):
    # Paralinguistic
    PPB = '(ppb)'  # breath
    PPC = '(ppc)'  # cough
    PPL = '(ppl)'  # laugh
    PPO = '(ppo)'  # other
    FIL = '<FIL/>' # *filler, generic

    # Tags indicating data not fit for use
    INV = '**'     # *invalid data
    Z   = '<Z>'    # invalid data
    S   = '<S>'    # short pause, >1000ms
    UNK = '<UNK>'  # unclear
    SPK = '<SPK/>' # *speaker noise, basically generic (pp*)
    STA = '<STA/>' # *stable background noise
    NON = '<NON/>' # *non-human, intermittent noise
    NPS = '<NPS/>' # *non-primary-speaker, i.e. SPK from nearby interlocutor
    NEN = '<NEN>'  # not-english

    # "Clitics" that belong within a token's boundaries
    MW  = '-'      # links multiword nouns
    IN  = '_'      # links initialisms
    IC  = '~'      # incomplete word

    # Particles
    DD  = '[ ]'    # Surrounds discourse particle
    FF  = '( )'    # Surrounds fillers
    HH  = '# #'    # Surrounds non-English tokens
    II  = '! !'    # Surrounds interjections

    # Structural indicators
    SEN = '</s>'   # end of sentence (sentence boundary)
    C   = '</c>'   # comma (clause boundary)


    @classmethod
    def pairs(cls, lowercase=False) -> List[Tuple[str, Optional[str]]]:
        out = []
        for tag in cls:
            left, *right = tag.value.split()
            right = right[0] if right else None

            if lowercase:
                left, right = left.lower(), right.lower()

            out.append((left, right))
        return out


    @classmethod
    def balancedpairs(cls, lowercase=False) -> List[Tuple[str, Optional[str]]]:
        out = []
        for (left, right) in cls.pairs(lowercase):
            if not right:
                continue
            out.append((left, right))
        return out


# Tags that don't describe content
TAGS_NONCONTENT = [
    Tag.FIL
    ,Tag.SPK
    ,Tag.STA
    ,Tag.NON
    ,Tag.NPS
    ,Tag.SEN
    ,Tag.C
    ,Tag.S
    ,Tag.Z
    ,Tag.UNK
    ,Tag.NEN
    ,Tag.PPB
    ,Tag.PPC
    ,Tag.PPL
    ,Tag.PPO
    ,Tag.INV
]

# Tags that are counted to be "part of" a token
TAGS_CLITIC = [
    Tag.MW
    ,Tag.IC
    ,Tag.IN
]

# Tags that wrap tokens
TAGS_BALANCED = [
    Tag.DD
    ,Tag.FF
    ,Tag.HH
    ,Tag.II
]


def truncated(s, maxlen=30):
    if len(s) > maxlen:
        s = s[:maxlen - 3] + '...'
    return s


def make_regex_pattern(*token_patterns) -> Pattern:
    """Compiles regex pattern from tokens; tokens will not be escaped"""
    s = '({})'.format('|'.join(token_patterns))
    return re.compile(s)


class IntervalError(ValueError):
    def __init__(self, interval, detail=''):
        if detail:
            detail = ' (%s)' % detail

        tg = f' in {interval.textgrid}' if interval.textgrid else ''

        errmsg = 'Failed to process interval {}{}'.format(
            interval.index, interval.textgrid, detail)

        super().__init__(errmsg)


class TranscriptionError(IntervalError):
    def __init__(self, interval, detail=''):
        detail = detail or 'Invalid transcription'
        super().__init__(interval, detail)


class Interval(object):
    """API for TextGrid intervals. Main application is the tokenize() method."""
    __slots__ = ['xmin', 'xmax', 'text', 'index', 'textgrid', 'raw', '_args']

    interval_fields = r"""intervals \[(?P<index>\d+)\]\:\s+xmin\s+=\s+(?P<xmin>(\d+\.)?\d+)\s+xmax\s+=\s+(?P<xmax>(\d+\.)?\d+)\s+text\s+=\s+\"(?P<text>.*)\""""
    interval_pattern = re.compile(interval_fields)

    interval_grouped = r"""(intervals \[\d+\]\:\s+xmin\s+=\s+(\d+\.)?\d+\s+xmax\s+=\s+(\d+\.)?\d+\s+text\s+=\s+\".*\")+"""
    interval_grouped_pattern = re.compile(interval_grouped)


    def __init__(self, xmin, xmax, text, index, raw, textgrid=None):
        self.index = int(index)
        self.xmin = float(xmin)
        self.xmax = float(xmax)
        self.text = text
        self.textgrid = textgrid
        self.raw = raw
        self._args = (xmin, xmax, text, index, textgrid, raw)


    @classmethod
    def from_text(cls, raw, textgrid=None):
        match = cls.interval_pattern.match(raw.strip())

        if not match:
            raise ValueError('bad interval format')

        kwargs = match.groupdict()
        kwargs.update({'raw': raw, 'textgrid': textgrid})

        obj = cls.__new__(cls)
        obj.__init__(**kwargs)
        return obj



    @property
    def tuple(self):
        return IntervalTuple(*self._args)


    @property
    def tokens(self):
        return self.tokenize(self.text)


    @classmethod
    def make_tokens_pattern(cls) -> Pattern:
        """Make pattern to use in re.findall().

        By default, creates a lowercased pattern out of the tags defined in this
        module. To customize the tokenizer pattern, override this method. The
        returned pattern will be directly passed to re.findall().

        The default pattern will treat segments enclosed within TAGS_BALANCED
        and TAGS_CENSORED as single tokens. No further tokenizing will be
        performed for text segments within these tags.

        The default pattern assumes that the text to be searched is all in
        lowercase.
        """
        re_escape = re.escape
        tags = [re_escape(t.value.lower())
                for t in TAGS_NONCONTENT]

        # Words & phrases: cake, p_s_l_e, p-five, incomple~
        clitics = (re_escape(t.value) for t in TAGS_CLITIC)
        tags.append("[\\w%s']+" % ''.join(clitics))

        balanced_tags = [tuple(t.value.lower().split())
                         for t in TAGS_BALANCED]
        for (left, right) in balanced_tags:
            tags.append(re_escape(left) + r"[\w\-_\s']+" + re_escape(right))

        return make_regex_pattern(*tags)


    @classmethod
    def tokenize(cls,
                 text,
                 force_lowercase=True,
                 discard_fillers=True,
                 discard_noncontent=True,
                 discard_incomplete=True,
                 cleanup_token=True) -> List[str]:
        """Tokenizes interval text using Pattern from make_tokens_pattern()

        By default, the interval text is set to lowercase before it is passed to
        re.findall().
        """
        text = text.lower() if force_lowercase else text
        patt = cls.make_tokens_pattern()

        # Bind stuff to local scope
        _token = Token
        noncontent = [x.value for x in TAGS_NONCONTENT]
        if force_lowercase:
            noncontent = [x.lower() for x in noncontent]

        # The function to map
        def maketoken(word):
            _startswith = word.startswith
            _endswith = word.endswith

            if (discard_incomplete and _endswith('~')
                or discard_noncontent and word in noncontent
                or (discard_fillers
                    and _startswith('(')
                    and not _startswith('(pp'))
            ):
                return None
            return _token(word, cleanup=cleanup_token)

        # Execute the map over tokens from re.findall() and return as list
        return [x for x in map(maketoken, patt.findall(text)) if x]


    def validate(self, strict=True) -> bool:
        """Test if the transcription markup is tagged correctly.

        TODO - Possible approach:
            1. Check if balanced tags are closed
            2. Tokenize and inspect tokens, complain if they look suspicious
            3. May be possible to have linting
        """
        raise NotImplementedError


    def __str__(self):
        return self.text


    def __repr__(self):
        return '<Interval {}: {}>'.format(self.index, truncated(self.text))


class Token(object):
    __slots__ = ['tag', 'content', 'text', 'raw']

    words_pattern = re.compile(
        '[' + (''.join(re.escape(t.value) for t in TAGS_CLITIC)) + r"\w\' ]+"
    )
    balanced_pairs = [(left.lower(), right.lower())
                      for (left, right) in Tag.balancedpairs()]

    def __init__(self, string, cleanup=True):
        s = string.lower()

        self.raw = string
        self.tag = None
        self.content = None
        self.text = None

        # Parsing for self.tag
        for tagtype, repres in Tag.__members__.items():
            v = repres.value.lower().split()[0]
            if v in s:
                self.tag = Tag[tagtype]
                break

        for left, right in self.balanced_pairs:
            if (left in s) == (right in s):
                continue
            raise ValueError('unbalanced tags in ' + self.raw)

        if not cleanup:
            self.content = s
            self.text = s
            return
        
        # Strip tags to get self.content
        content = s
        if self.tag:
            if self.tag is Tag.MW:
                # content = content.replace('-', ' ')
                pass
            elif self.tag in TAGS_CLITIC:
                pass
            else:
                # For balanced tags, will erase only the opening tag
                # This is to prevent wordy tags, like <nen></nen>, from matching
                # in the regex search below
                content = content.replace(self.anchor_tag.lower(), '')
        
        # Regex search for words to get self.content
        cont = self.words_pattern.search(content)
        content = cont.group() if cont else ''
        # remove whitespace and store
        self.content = ' '.join(content.split())

        # Reapply tags using canonical form from Tag enum and store
        # The content, with 'canonical' tag forms applied is stored as self.text
        wrapwith = ('', '')
        if self.tag and (self.tag not in TAGS_CLITIC):
            left, *right = self.tag.value.split()
            right = right and right[0] or ''
            wrapwith = (left, right)
        self.text = wrapwith[0] + self.content + wrapwith[1]


    @property
    def anchor_tag(self):
        if not self.tag:
            return ''
        return self.tag.value.split()[0]


    def __repr__(self):
        return '<Token: {}>'.format(truncated(self.text or self.anchor_tag))


    def __str__(self):
        return self.text
