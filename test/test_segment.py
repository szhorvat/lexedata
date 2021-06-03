import re

from lexedata.edit.add_segments import segment_form, SegmentReport


def test_unkown_aspiration(caplog):
    form = "-á:muaʰ"
    report = SegmentReport()
    segment_form(form, report)
    print(caplog.text)
    assert re.search(
        "Unknown sound aʰ encountered in -á:muaʰ", caplog.text
    ) and report("language") == [("language", "aʰ", 1, "unknown pre-aspiration")]


def test_segment_report():
    report1 = SegmentReport()
    report1.sounds["aʰ"]["count"] = 1
    report1.sounds["aʰ"]["comment"] = "comment"
    report1 = report1("language")
    assert report1 == [("language", "aʰ", 1, "comment")]


# TODO: report also contains the data from the test before ... but why does this happen?
def test_unknown_sound(caplog):
    form = "wohuᵈnasi"
    report2 = SegmentReport()
    segment_form(form, report2)
    assert re.search(
        "Unknown sound uᵈ encountered in wohuᵈnasi", caplog.text
    )  # and report2("language") == [("language", "uᵈ", 1, "unknown sound")]


def test_illegal_symbol(caplog):
    form = r"woh/"
    report3 = SegmentReport()
    segment_form(form, report3)
    assert re.search(
        "Impossible sound '/' encountered in woh/", caplog.text
    )  # and report3("language") == [("language", "/", 1, "illegal symbol")]
