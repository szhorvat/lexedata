# -*- coding: utf-8 -*-
import re
import unicodedata
from abc import ABC, abstractmethod
from typing import Tuple, Optional

from lexedata.importer.exceptions import *

# functions for bracket checking, becoming obsolete with new cellparser
comment_bracket = lambda str: str.count("(") == str.count(")")

# TODO: ask Gereon about escaping
comment_escapes = re.compile(r"&[</\[{].+?(?:\s|.$)")

phonemic_pattern = re.compile(r"""(?:^| # start of the line or
        (.*?(?<=[^&]))) #capture anything before phonemic, phonemic must not follow a &, i.e. & escapes
        (/[^/]+? #first phonemic element, not greedy, 
                 # special for phonemic: use [^/] instead of . to ensure correct escaping
        (?<=[^&])/  # applies only to phonemic: closer must not follow &, otherwise &/a/ texttext &/b/ will render / texttext &/
        (?:\s*[~%]\s*/[^/]+?/)*  #non capturing pattern for any repetition of [%~]/..../
        )  #capture whole group
        (.*)$ #capture the rest""", re.VERBOSE)
phonetic_pattern = re.compile(r"(?:^|(.*?(?<=[^&])))(\[.+?](?:\s*[~%]\s*\[.+?])*)(.*)$")
ortho_pattern = re.compile(r"(?:^|(.*?(?<=[^&])))(<.+?>(?:\s*[~%]\s*<.+?>)*)(.*)$")

source_pattern = re.compile(r"(?:^|(.*?(?<=[^&])))({.+?})(.*)$")  # just one source per form, must not be empty

my_form_pattern = [(phonemic_pattern, "phonemic"),
                    (phonetic_pattern, "phonetic"),
                    (ortho_pattern, "orthographic"),
                    (source_pattern, "source")]

lexical_parser_default_settings = {
    "illegal_symbols_description": re.compile(r"[</[{]"),
    "illegal_symbols_transcription": re.compile(r"[;]"),
    "form_pattern": my_form_pattern,
    "description_pattern": re.compile(r"^(.*?)(\(.+\))(.*)$"),
    "separator_pattern": re.compile(r"""
                 (?<=[}\)>/\]])    # The end of an element of transcription, not consumed
                 \s*               # Any amount of spaces
                 [,;]              # Some separator
                 \s*               # Any amount of spaces
                 (?=[</\[])        # Followed by the beginning of any transcription, but don't consume that bit""",
                                    re.VERBOSE),
    "ignore_pattern": re.compile(r"^(.+)#.+?#(.*)$")  # anything between # # is replaced by an empty string
}


class CellParser(ABC):

    def __init__(self, illegal_symbols_description, illegal_symbols_transcription, form_pattern, description_pattern,
                separator_pattern, ignore_pattern, **kwargs):
        self.separator_pattern = separator_pattern
        self.illegal_symbols_description = illegal_symbols_description
        self.illegal_symbols_transcription = illegal_symbols_transcription
        self.form_pattern = form_pattern
        self.description_pattern = description_pattern
        self.ignore_pattern = ignore_pattern

    def separate(self, values):
        values = unicodedata.normalize('NFKC', values)
        if self.separator_pattern:
            elements = self.separator_pattern.split(values)
            # clean elements list
            elements = [e.strip() for e in elements]  # no tailing white spaces
            # remove possible line break and ending commas
            elements[-1] = elements[-1].rstrip("\n").rstrip(",").rstrip(";")
            return elements
        else:
            return values

    @classmethod
    def bracket_checker(cls, opening, closing, string):
        if not string:
            return False
        else:
            return string.count(opening) == string.count(closing)

    @abstractmethod
    def parse_value(self, values, coordinate):
        pass

    @abstractmethod
    def parse(self, values, coordinate):
        self.coordinate = coordinate
        # replace ignore pattern with empty string
        while self.ignore_pattern.match(values):
            values = self.ignore_pattern.sub(r"\1\2", values)

        self.values = self.separate(values)
        for element in self.values:
            try:
                element = self.parse_value(element, coordinate)
                # assert no empty element
                if all(ele == "" for ele in element):
                    raise CellParsingError("empty values ''", self.coordinate)
                yield element
            # error handling
            except CellParsingError as err:
                print("CellParsingError: " + err.message)
                # input()
                continue

            except FormCellError as err:
                print(err)
                # input()
                continue

            except IgnoreCellError as err:
                print(err)
                # input()
                continue

            except SeparatorCellError as err:
                print(err)
                # input()
                continue


class CellParserLexical(CellParser):

    def __init__(self, illegal_symbols_description=None, illegal_symbols_transcription=None, form_pattern=None,
                 description_pattern=None, separator_pattern=None, ignore_pattern=None, **kwargs):
        # personalized used if arguments not None
        if any(kwargs.values()):
            super().__init__(illegal_symbols_description,
                             illegal_symbols_transcription, form_pattern,
                             description_pattern, separator_pattern, ignore_pattern)
        else: # use with default settings
            super().__init__(**lexical_parser_default_settings)

    def parse(self, values, coordinate):
        for element in super().parse(values, coordinate):
            yield element

    def parse_value(self, values, coordinate):
        return self.parsecell(values, coordinate)

    def parsecell(self, ele, coordinates) -> Tuple[
        Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        :param ele: is a form string; form string referring to a possibly (semicolon or)comma separated string of a form cell
        :return: list of cellsize containing parsed data of form string
        """
        if ele == "...":
            return [None] * 6

        else:
            mymatch = self.parse_form(ele, coordinates)

        mymatch = [e or '' for e in mymatch]
        phonemic, phonetic, ortho, description, source = mymatch

        variants = []
        if phonemic:
            phonemic = self.variants_separator(variants, phonemic, coordinates)
        if phonetic:
            phonetic = self.variants_separator(variants, phonetic, coordinates)
        if ortho:
            ortho = self.variants_separator(variants, ortho, coordinates)
        variants = ",".join(variants)

        if phonemic == phonetic == ortho == "":
            ele_dummy = (ele + " ")[:-1]
            while " " in ele_dummy:
                ele_dummy = ele.replace(" ", "")
            if not ele_dummy:
                raise FormCellError((phonemic + phonetic + ortho), "Empty Excel Cell", coordinates)
            else:
                raise FormCellError(ele, "Empty Form Cell", coordinates)

        if description:
            if not self.bracket_checker("(", ")", description):
                raise FormCellError(description, "description", coordinates)

        return [phonemic, phonetic, ortho, description, source, variants]

    def parse_form(self, formele, coordinates):
        """checks if values of cells not in expected order, extract each value"""
        ele = (formele + ".")[:-1]  # force python to hard copy string
        # parse transcriptions and fill dictionary d
        d = dict()
        for pat, lable in self.form_pattern:

            mymatch = pat.match(ele)
            if mymatch:
                # delete match in cell
                d[lable] = mymatch.group(2)
                ele = pat.sub(r"\1\3", ele)
            else:
                d[lable] = None

        mydescription = ""
        # get all that is left of the string in () and add it to the comment
        while self.description_pattern.match(ele):
            description_candidate = self.description_pattern.match(ele).group(2)
            # no transcription symbols in comment
            if not self.illegal_symbols_description.search(description_candidate):
                mydescription += description_candidate
                ele = self.description_pattern.sub(r"\1\3", ele)
            else:  # check if comment is escaped correctly, if not, raise error

                # replace escaped elements and check for illegal content, if all good, add original_form
                escapes = comment_escapes.findall(description_candidate)
                original_form = description_candidate
                for e in escapes:
                    description_candidate = description_candidate.replace(e, "")
                if not self.illegal_symbols_description.search(description_candidate):
                    mydescription += original_form
                    ele = self.description_pattern.sub(r"\1\3", ele)
                else:  # illegal comment
                    raise FormCellError(description_candidate, "description", coordinates)

        # check that ele was parsed entirely, if not raise parsing error
        ele = ele.strip(" ")
        if not ele == "":
            # if just text left and no comment given, put text in comment
            # more than one token
            if len(ele) >= 1 and (not self.illegal_symbols_description.search(ele)):

                if not mydescription:
                    mydescription = ele
                else:
                    mydescription += ele

            else:
                errmessage = "after parsing {}  -  {} was left unparsed".format(formele, ele)
                raise FormCellError(errmessage, "IncompleteParsingError; probably illegal content", coordinates)

        # enclose comment if not properly enclosed
        if not self.bracket_checker("(", ")", mydescription):
            mydescription = "(" + mydescription + ")"
        d["description"] = mydescription
        form_cell = [d["phonemic"], d["phonetic"], d["orthographic"], d["description"], d["source"]]
        return form_cell

    @staticmethod
    def variants_scanner(string, symbol):
        """copies string, inserting closing brackets after symbol if necessary"""
        is_open = False
        closers = {"<": ">", "[": "]", "/": "/"}
        collector = ""
        starter = ""

        for char in string:

            if char in closers and not is_open:
                collector += char
                is_open = True
                starter = char

            elif char == symbol:
                if is_open:
                    collector += (closers[starter] + char + starter)
                else:
                    collector += char

            elif char in closers.values():
                collector += char
                is_open = False
                starter = ""

            elif is_open:
                collector += char

        return collector

    def variants_separator(self, variants_list, string, coordinate):
        if self.illegal_symbols_transcription.search(string):
            raise SeparatorCellError(string, coordinate)
        # force python to copy string
        text = (string + "&")[:-1]
        while " " in text:
            text = text.replace(" ", "")
        if "~" in string:
            values = self.variants_scanner(text, "~")
            values = values.split("~")
            first = values.pop(0)

            # add rest to variants prefixed with ~
            values = [("~" + e) for e in values]
            variants_list += values
            return first

        # inconsistent variants
        elif "%" in string:
            values = self.variants_scanner(text, "%")
            values = values.split("%")
            first = values.pop(0)

            # add rest to variants prefixed with ~
            values = [("%" + e) for e in values]
            variants_list += values
            return first
        else:
            return string



class CellParserLD():
    """class over all form elements contained in a form cell.

    Parse the content of a cell with one or more transcriptions sparated by ';'.
    """
    phonemic_pattern = re.compile(r"""(?:^| # start of the line or
    (.*?(?<=[^&]))) #capture anything before phonemic, phonemic must not follow a &, i.e. & escapes
    (/[^/]+? #first phonemic element, not greedy, 
             # special for phonemic: use [^/] instead of . to ensure correct escaping
    (?<=[^&])/  # applies only to phonemic: closer must not follow &, otherwise &/a/ texttext &/b/ will render / texttext &/
    (?:\s*[~%]\s*/[^/]+?/)*  #non capturing pattern for any repetition of [%~]/..../
    )  #capture whole group
    (.*)$ #capture the rest""", re.VERBOSE)
    phonetic_pattern = re.compile(r"(?:^|(.*?(?<=[^&])))(\[.+?](?:\s*[~%]\s*\[.+?])*)(.*)$")
    ortho_pattern = re.compile(r"(?:^|(.*?(?<=[^&])))(<.+?>(?:\s*[~%]\s*<.+?>)*)(.*)$")

    source_pattern = re.compile(r"(?:^|(.*?(?<=[^&])))({.+?})(.*)$")  # just one source per form, must not be empty
    _comment_pattern = re.compile(r"^(.*?)(\(.+\))(.*)$")  # all in brackets, greedy

    _form_pattern = [(phonemic_pattern, "phonemic"),
                     (phonetic_pattern, "phonetic"),
                     (ortho_pattern, "orthographic"),
                     (source_pattern, "source")]

    illegal_symbols_description = re.compile(r"[</[{]")  # for checking with re.search
    # all escaped transcriptions in comment, followed by white space or if not one character and EOL
    _comment_escapes = re.compile(r"&[</\[{].+?(?:\s|.$)")
    illegal_symbols_transcription = re.compile(r"[;]")  # for checking with re.search

    # will clean everything between ## using re.sub
    _cleaner = re.compile(r"^(.+)#.+?#(.*)$")

    # pattern for splitting form cell into various form elements
    form_separator = re.compile(r"""
    (?<=[}\)>/\]])    # The end of an element of transcription, not consumed
    \s*               # Any amount of spaces
    [,;]              # Some separator
    \s*               # Any amount of spaces
    (?=[</\[])        # Followed by the beginning of any transcription, but don't consume that bit""",
                                re.VERBOSE)

    def __init__(self):
        pass

    def parse(self, cell):  # , on_error: Literal["except", "guess", "ignore"] = "except"
        """Parse the entire cell content

        """
        # FIXME: Avoid side-effects to the parser class

        # In the process of writing to SQLite, unicode normalization happens at
        # some point, which makes some comparisons fail. If we manually
        # pre-normalize here, we reduce pain later.
        values = unicodedata.normalize('NFKC', cell.value)

        self.coordinate = cell.coordinate
        if not values:  # capture None values
            raise CellParsingError(values, self.coordinates)
        self.set_elements(values)
        while True:
            # Ewwwww. FIXME: This whole class needs an overhaul.
            try:
                yield next(self)
            except StopIteration:
                break

    def set_elements(self, values):
        # remove #
        while self._cleaner.match(values):
            values = self._cleaner.sub(r"\1\2", values)
        elements = self.separate(values)

        if len(elements) == 0:  # check that not empty
            raise CellParsingError(values, self.coordinate)

        # clean elements list
        elements = [e.strip() for e in elements]  # no tailing white spaces
        elements[-1] = elements[-1].rstrip("\n").rstrip(",").rstrip(";")  # remove possible line break and ending commas

        self._elements = iter(elements)

    def separate(self, values):
        """Splits the content of a form cell into single form descriptions

        >>> parser = CellParser()
        >>> parser.separate("<jaoca> (apartar-se, separar-se){2}")
        ['<jaoca> (apartar-se, separar-se){2}']
        >>> parser.separate("<eruguasu> (adj); <eniãcũpũ> (good-tasting (sweet honey, hard candy, chocolate candy, water){2}; <beyiruubu tuti> (tasty (re: meat with salt, honey, all good things)){2}; <eniacõ> (tasty (re: eggnog with flavoring)){2}; <eracũpũ> (tasty, good re: taste of honey, smell of flowers)){2}; <eribia tuti> (very tasty){2}; <ericute~ecute> (tasty, good (boiled foods)){2}; <eriya sui tuti> (very tasty, re: fermented fruit){2}; <erochĩpu> (good, tasty (re: tembe, pig meat)){2}; <ichẽẽ> (tasty (taste of roasted meat)){2}")[1]
        '<eniãcũpũ> (good-tasting (sweet honey, hard candy, chocolate candy, water){2}'
        >>> parser.separate("<form> (Example; has a semicolon in the comment); <otherform>")
        ['<form> (Example; has a semicolon in the comment)', '<otherform>']

        Returns
        =======
        list of form strings
        """
        return re.split(self.form_separator, values)

    @classmethod
    def parsecell(cls, ele, coordinates) -> Tuple[
        Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        :param ele: is a form string; form string referring to a possibly (semicolon or)comma separated string of a form cell
        :return: list of cellsize containing parsed data of form string
        """
        if ele == "...":
            return [None] * 6

        else:
            mymatch = cls.parse_form(ele, coordinates)

        mymatch = [e or '' for e in mymatch]
        phonemic, phonetic, ortho, comment, source = mymatch

        variants = []
        if phonemic:
            phonemic = cls.variants_separator(variants, phonemic, coordinates)
        if phonetic:
            phonetic = cls.variants_separator(variants, phonetic, coordinates)
        if ortho:
            ortho = cls.variants_separator(variants, ortho, coordinates)
        variants = ",".join(variants)

        if phonemic == phonetic == ortho == "":
            ele_dummy = (ele + " ")[:-1]
            while " " in ele_dummy:
                ele_dummy = ele.replace(" ", "")
            if not ele_dummy:
                raise FormCellError((phonemic + phonetic + ortho), "Empty Excel Cell", coordinates)
            else:
                raise FormCellError(ele, "Empty Form Cell", coordinates)

        if comment != "" and comment != "No value":
            if not comment_bracket(comment):
                raise FormCellError(comment, "comment", coordinates)

        return [phonemic, phonetic, ortho, comment, source, variants]

    @classmethod
    def parse_form(cls, formele, coordinates):
        """checks if values of cells not in expected order, extract each value"""
        ele = (formele + ".")[:-1]  # force python to hard copy string
        # parse transcriptions and fill dictionary d
        d = {"phonemic": None, "phonetic": None, "orthographic": None, "comment": None, "source": None}
        for pat, lable in cls._form_pattern:

            mymatch = pat.match(ele)
            if mymatch:
                # delete match in cell
                d[lable] = mymatch.group(2)
                ele = pat.sub(r"\1\3", ele)

        mycomment = ""
        # get all that is left of the string in () and add it to the comment
        while cls._comment_pattern.match(ele):
            comment_candidate = cls._comment_pattern.match(ele).group(2)
            # no transcription symbols in comment
            if not cls.illegal_symbols_description.search(comment_candidate):
                mycomment += comment_candidate
                ele = cls._comment_pattern.sub(r"\1\3", ele)
            else:  # check if comment is escaped correctly, if not, raise error

                # replace escaped elements and check for illegal content, if all good, add original_form
                escapes = cls._comment_escapes.findall(comment_candidate)
                original_form = comment_candidate
                for e in escapes:
                    comment_candidate = comment_candidate.replace(e, "")
                if not cls.illegal_symbols_description.search(comment_candidate):
                    mycomment += original_form
                    ele = cls._comment_pattern.sub(r"\1\3", ele)
                else:  # illegal comment
                    raise FormCellError(comment_candidate, "comment", coordinates)

        # check that ele was parsed entirely, if not raise parsing error
        ele = ele.strip(" ")
        if not ele == "":
            # if just text left and no comment given, put text in comment
            # more than one token
            if len(ele) >= 1 and (not cls.illegal_symbols_description.search(ele)):

                if not mycomment:
                    mycomment = ele
                else:
                    mycomment += ele

            else:
                errmessage = "after parsing {}  -  {} was left unparsed".format(formele, ele)
                raise FormCellError(errmessage, "IncompleteParsingError; probably illegal content", coordinates)

        # enclose comment if not properly enclosed
        if mycomment != "" and (not mycomment.startswith("(") or not mycomment.endswith(")")):
            mycomment = "(" + mycomment + ")"
        d["comment"] = mycomment
        form_cell = [d["phonemic"], d["phonetic"], d["orthographic"], d["comment"], d["source"]]
        return form_cell

    @staticmethod
    def variants_scanner(string, symbol):
        """copies string, inserting closing brackets after symbol if necessary"""
        is_open = False
        closers = {"<": ">", "[": "]", "/": "/"}
        collector = ""
        starter = ""

        for char in string:

            if char in closers and not is_open:
                collector += char
                is_open = True
                starter = char

            elif char == symbol:
                if is_open:
                    collector += (closers[starter] + char + starter)
                else:
                    collector += char

            elif char in closers.values():
                collector += char
                is_open = False
                starter = ""

            elif is_open:
                collector += char

        return collector

    @classmethod
    def variants_separator(cls, variants_list, string, coordinate):
        if cls.illegal_symbols_transcription.search(string):
            raise SeparatorCellError(string, coordinate)
        # force python to copy string
        text = (string + "&")[:-1]
        while " " in text:
            text = text.replace(" ", "")
        if "~" in string:
            values = cls.variants_scanner(text, "~")
            values = values.split("~")
            first = values.pop(0)

            # add rest to variants prefixed with ~
            values = [("~" + e) for e in values]
            variants_list += values
            return first

        # inconsistent variants
        elif "%" in string:
            values = cls.variants_scanner(text, "%")
            values = values.split("%")
            first = values.pop(0)

            # add rest to variants prefixed with ~
            values = [("%" + e) for e in values]
            variants_list += values
            return first
        else:
            return string

    def __next__(self):
        try:
            ele = next(self._elements)
            ele = CellParser.parsecell(ele, self.coordinate)
            # check core values not empty
            phonemic, phonetic, ortho = ele[0], ele[1], ele[2]
            if phonemic == phonetic == ortho == "":
                raise CellParsingError("empty values ''", self.coordinate)
            return ele

        # error handling
        except CellParsingError as err:
            print("CellParsingError: " + err.message)
            # input()
            return self.__next__()

        except FormCellError as err:
            print(err)
            # input()
            return self.__next__()

        except IgnoreCellError as err:
            print(err)
            # input()
            return self.__next__()

        except SeparatorCellError as err:
            print(err)
            # input()
            return self.__next__()


class CogCellParser(CellParser):
    "Like CellParser, but ignores cells in capital letters"

    def __init__(self, cell):
        values = cell.value
        self.coordinate = cell.coordinate
        ele = next(self._elements)
        return CellParser.parsecell(ele)

        if values.isupper():
            print(IgnoreCellError(values, self.coordinate))

        self.set_elements(values)


class Tester():

    def __init__(self, string, coordinate="asf"):
        self.value = string
        self.coordinate = coordinate

    def __hash__(self):
        return self


if __name__ == "__main__":

    c1 = Tester(
        "<tatatĩ>(humo){Guasch1962:717}, <timbo>(vapor, vaho, humareda, humo){Guasch1962:729};<tĩ> (humo, vapor de agua)$LDM:deleted 'nariz, pico, hocico, punta, and ápica' meanings; source incorrectly merges 'point' and 'smoke' meanings ${Guasch1962:729}")
    c2 = Tester(
        "/pãlĩ/ (de froment = wheat) (NCP: loan from french farine), /pɨlatɨ/ (de mais cru), /kuʔi/ (de mais grillé)")
    c3 = Tester(
        "/pãlĩ/ (de froment = wheat(NCP: loan from french farine), &<dummy>), /pɨlatɨ/ (de mais cru), /kuʔi/ (de mais grillé)")
    c4 = Tester("/popɨãpat/ 'back of elbow' {4}")
    c5 = Tester("<ayu> (nominalized &/afaaa/ version of &/ete/ 'about') {2}")
    for ele in [c1, c2, c3, c4, c5]:
        print(ele.value)
        print("is represented as: ")
        for f in CogCellParser(ele):
            print(f)
        input()
