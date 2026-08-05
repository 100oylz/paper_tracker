"""venue 徽章、CCF 表抽样与 PDF 链接规则测试。"""

from tracker.venue_meta import VENUE_INFO, pdf_link, venue_badge


def test_badge_basic_and_journal():
    assert venue_badge("NeurIPS") == "**[NeurIPS · CCF-A]**"
    assert venue_badge("IEEE Trans. Pattern Anal. Mach. Intell.") == \
        "**[IEEE TPAMI · CCF-A · IF 20.8(2023)]**"


def test_badge_workshop_and_unknown():
    assert venue_badge("EuroMLSys@EuroSys") == "**[EuroMLSys@EuroSys · Workshop]**"
    assert venue_badge("Some Conf") == "**[Some Conf]**"
    assert venue_badge("") == ""


def test_ccf_spot_checks():
    assert VENUE_INFO["ICLR"][1] == "A"
    assert VENUE_INFO["IJCAI"][1] == "B"
    assert VENUE_INFO["EuroSys"][1] == "A"
    assert VENUE_INFO["MLSys"][1] is None


def test_pdf_link_rules():
    assert pdf_link({"ee": "https://arxiv.org/abs/2401.1"}) == "https://arxiv.org/pdf/2401.1"
    assert pdf_link({"ee": "https://openreview.net/forum?id=A1"}) == "https://openreview.net/pdf?id=A1"
    assert pdf_link({"ee": "https://aclanthology.org/2023.acl-long.1"}) == \
        "https://aclanthology.org/2023.acl-long.1.pdf"
    assert pdf_link({"ee": "https://www.ijcai.org/proceedings/2024/123/"}) == \
        "https://www.ijcai.org/proceedings/2024/123.pdf"
    assert pdf_link({"ee": "https://doi.org/10.1145/x"}) == ""
    assert pdf_link({}) == ""
