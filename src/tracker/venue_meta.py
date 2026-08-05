"""venue 元数据：显示名、CCF 等级、备注，以及开放 PDF 链接推导。"""

import re


VENUE_INFO = {
    # ---------- 人工智能（会议） ----------
    "AAAI": ("AAAI", "A", None),
    "NeurIPS": ("NeurIPS", "A", None),
    "ICML": ("ICML", "A", None),
    "ICLR": ("ICLR", "A", "第七版新晋A"),
    "IJCAI": ("IJCAI", "B", "第七版由A降B"),
    "CVPR": ("CVPR", "A", None),
    "ICCV": ("ICCV", "A", None),
    "ECCV": ("ECCV", "B", None),
    "ACL": ("ACL", "A", None),
    "EMNLP": ("EMNLP", "B", None),
    "NAACL-HLT": ("NAACL", "B", "第七版新晋B"),
    "COLING": ("COLING", "B", None),
    "AISTATS": ("AISTATS", "C", None),
    "COLT": ("COLT", "B", None),
    "ALT": ("ALT", "C", None),
    "UAI": ("UAI", "B", None),
    "MLSys": ("MLSys", None, "未入CCF目录"),
    # ---------- 数据挖掘 / 数据库 / 信息检索 ----------
    "KDD": ("KDD", "A", None),
    "WSDM": ("WSDM", "B", None),
    "ICDE": ("ICDE", "A", None),
    "SIGIR": ("SIGIR", "A", None),
    "SIGMOD Conference": ("SIGMOD", "A", None),
    "Proc. VLDB Endow.": ("VLDB", "A", None),
    "Proc. ACM Manag. Data": ("SIGMOD (PACMMOD)", "A", None),
    "WWW": ("WWW", "A", None),
    # ---------- 网络与系统 ----------
    "INFOCOM": ("INFOCOM", "A", None),
    "SIGCOMM": ("SIGCOMM", "A", None),
    "MobiCom": ("MobiCom", "A", None),
    "NSDI": ("NSDI", "A", None),
    "EuroSys": ("EuroSys", "A", "第七版由B升A"),
    "OSDI": ("OSDI", "A", None),
    "SOSP": ("SOSP", "A", None),
    "ISCA": ("ISCA", "A", None),
    # ---------- 安全 ----------
    "CCS": ("CCS", "A", None),
    "SP": ("IEEE S&P", "A", None),
    "S&amp;P": ("IEEE S&P", "A", None),
    "IEEE Symposium on Security and Privacy": ("IEEE S&P", "A", None),
    "USENIX Security Symposium": ("USENIX Security", "A", None),
    "NDSS": ("NDSS", "A", None),
    # ---------- 软件工程 / 体系结构 / 设计自动化 ----------
    "ICSE": ("ICSE", "A", None),
    "DAC": ("DAC", "A", None),
    "STOC": ("STOC", "A", None),
    "ACM Multimedia": ("ACM MM", "A", None),
    "ICDAR": ("ICDAR", "C", None),
    # ---------- 期刊 ----------
    "IEEE Trans. Pattern Anal. Mach. Intell.": ("IEEE TPAMI", "A", "IF 20.8(2023)"),
    "Int. J. Comput. Vis.": ("IJCV", "A", "IF 10.3(2025)"),
    "J. Mach. Learn. Res.": ("JMLR", "A", "IF 6.8(2025)"),
    "Artif. Intell.": ("Artificial Intelligence", "A", "IF 4.7(2025)"),
    "Mach. Learn.": ("Machine Learning", "B", "IF 4.9(2025)"),
    "IEEE Trans. Parallel Distributed Syst.": ("IEEE TPDS", "A", "IF 5.9(2025)"),
    "IEEE Trans. Computers": ("IEEE TC", "A", "IF 4.9(2025)"),
    "IEEE Trans. Comput. Aided Des. Integr. Circuits Syst.": ("IEEE TCAD", "A", "IF 3.6(2025)"),
    "ACM Trans. Storage": ("ACM TOS", "A", "IF 3.6(2025)"),
    "ACM Trans. Comput. Syst.": ("ACM TOCS", "A", "IF 1.9(2025)"),
    # ---------- Workshop / Companion ----------
    "EuroMLSys@EuroSys": ("EuroMLSys@EuroSys", None, "Workshop"),
    "EdgeSys@EuroSys": ("EdgeSys@EuroSys", None, "Workshop"),
    "CrossCloud@EuroSys": ("CrossCloud@EuroSys", None, "Workshop"),
    "SP Workshops": ("IEEE S&P Workshops", None, "Workshop"),
    "IEEE Symposium on Security and Privacy Workshops": ("IEEE S&P Workshops", None, "Workshop"),
    "CSET @ USENIX Security Symposium": ("CSET@USENIX Sec", None, "Workshop"),
    "BiDEDE@SIGMOD": ("BiDEDE@SIGMOD", None, "Workshop"),
    "aiDM@SIGMOD": ("aiDM@SIGMOD", None, "Workshop"),
    "DanaC@SIGMOD": ("DanaC@SIGMOD", None, "Workshop"),
    "DEEM@SIGMOD": ("DEEM@SIGMOD", None, "Workshop"),
    "SEAMS@ICSE": ("SEAMS@ICSE", None, "Workshop"),
    "S-Cube@ICSE": ("S-Cube@ICSE", None, "Workshop"),
    "ICSE Companion": ("ICSE Companion", None, "Workshop"),
    "SVM@ICSE": ("SVM@ICSE", None, "Workshop"),
    "SEiGS@ICSE": ("SEiGS@ICSE", None, "Workshop"),
    "ICSE Workshop on SE-HCI": ("ICSE SE-HCI Workshop", None, "Workshop"),
}


def venue_badge(venue_str):
    """渲染加粗 venue 徽章；未知 venue 原样输出，workshop 类自动标注。"""
    venue = (venue_str or "").strip()
    if not venue:
        return ""
    info = VENUE_INFO.get(venue)
    if info is None:
        if "@" in venue or "workshop" in venue.lower() or "companion" in venue.lower():
            return f"**[{venue} · Workshop]**"
        return f"**[{venue}]**"
    display, ccf, note = info
    parts = [display]
    if ccf:
        parts.append(f"CCF-{ccf}")
    if note:
        parts.append(note)
    return "**[" + " · ".join(parts) + "]**"


def pdf_link(paper):
    """从 ee 纯规则推导开放 PDF 链接；推导不出返回空串。"""
    ee = (paper.get("ee") or "").strip()
    if not ee:
        return ""
    if ee.lower().endswith(".pdf"):
        return ee
    if "arxiv.org/abs/" in ee:
        return ee.replace("arxiv.org/abs/", "arxiv.org/pdf/", 1)
    if "openreview.net/forum" in ee:
        return ee.replace("openreview.net/forum", "openreview.net/pdf", 1)
    if ("papers.nips.cc" in ee or "proceedings.neurips.cc" in ee) and ee.endswith(".html"):
        return ee.replace("Abstract", "Paper")[:-len(".html")] + ".pdf"
    m = re.match(r"^(https?://proceedings\.mlr\.press/v\d+/([^/]+)/?)$", ee)
    if m:
        return m.group(1).rstrip("/") + "/" + m.group(2) + ".pdf"
    m = re.match(r"^(https?://aclanthology\.org/[^/]+)/?$", ee)
    if m:
        return m.group(1) + ".pdf"
    if "openaccess.thecvf.com" in ee and ee.endswith(".html"):
        return ee[:-len(".html")] + ".pdf"
    m = re.match(r"^(https?://www\.ijcai\.org/proceedings/\d+/\d+)/?$", ee)
    if m:
        return m.group(1) + ".pdf"
    if "jmlr.org" in ee and ee.endswith(".html"):
        return ee[:-len(".html")] + ".pdf"
    return ""
