#!/usr/bin/env python3
"""把 cached/dblp.yaml 转换为结构化 FL-Papers.md。"""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml

from tracker.config import project_root


VENUE_MAP = {
    # Journals
    "Artif. Intell.": "AI",
    "Mach. Learn.": "Machine Learning",
    "J. Mach. Learn. Res.": "JMLR",
    "IEEE Trans. Pattern Anal. Mach. Intell.": "TPAMI",
    "Int. J. Comput. Vis.": "IJCV",
    "Proc. VLDB Endow.": "VLDB",
    "IEEE Trans. Parallel Distrib. Syst.": "TPDS",
    "ACM Trans. Comput. Syst.": "TOCS",
    "ACM Trans. Storage": "TOS",
    "IEEE Trans. Comput. Aided Des. Integr. Circuits Syst.": "TCAD",
    "IEEE Trans. Comput.": "TC",
    "IEEE Trans. Computers": "TC",
    "IEEE Trans. Parallel Distributed Syst.": "TPDS",
    "Trans. Mach. Learn. Res.": "TMLR",
    "IEEE Trans. Dependable Secur. Comput.": "TDSC",
    "IEEE Trans. Inf. Forensics Secur.": "TIFS",
    "IEEE Trans. Knowl. Data Eng.": "TKDE",
    "IEEE Big Data": "Big Data",
    "IEEE BigData": "Big Data",
    # Conferences with special names
    "IEEE Symposium on Security and Privacy": "S&P",
    "IEEE Symposium on Security and Privacy Workshops": "S&P",
    "SPW": "S&P",
    "USENIX Security Symposium": "USENIX Security",
    "SOUPS": "SOUPS",
    "SOUPS @ USENIX Security Symposium": "SOUPS",
    "SIGMOD Conference": "SIGMOD",
    "SIGMOD Conference Companion": "SIGMOD",
    "Proc. ACM Manag. Data": "SIGMOD",
    "BiDEDE@SIGMOD": "SIGMOD",
    "DEEM@SIGMOD": "SIGMOD",
    "DanaC@SIGMOD": "SIGMOD",
    "aiDM@SIGMOD": "SIGMOD",
    "NAACL-HLT": "NAACL",
    "MobiCom": "MOBICOM",
    "ACM Multimedia": "MM",
    "CSET @ USENIX Security Symposium": "USENIX Security",
    "CrossCloud@EuroSys": "EuroSys",
    "EdgeSys@EuroSys": "EuroSys",
    "EuroMLSys@EuroSys": "EuroSys",
    "ICSE Companion": "ICSE",
    "S-Cube@ICSE": "ICSE",
    "SEAMS@ICSE": "ICSE",
    "SEiGS@ICSE": "ICSE",
    "SVM@ICSE": "ICSE",
    "SP": "S&P",
    "SP Workshops": "S&P",
}

CATEGORY_MAP = {
    "IJCAI": "Artificial Intelligence",
    "AAAI": "Artificial Intelligence",
    "AISTATS": "Artificial Intelligence",
    "ALT": "Artificial Intelligence",
    "AI": "Artificial Intelligence",
    "NeurIPS": "Machine Learning",
    "ICML": "Machine Learning",
    "ICLR": "Machine Learning",
    "COLT": "Machine Learning",
    "UAI": "Machine Learning",
    "Machine Learning": "Machine Learning",
    "JMLR": "Machine Learning",
    "TPAMI": "Machine Learning",
    "TMLR": "Machine Learning",
    "KDD": "Data Mining",
    "WSDM": "Data Mining",
    "TKDE": "Data Mining",
    "Big Data": "Data Mining",
    "S&P": "Secure",
    "CCS": "Secure",
    "USENIX Security": "Secure",
    "NDSS": "Secure",
    "TIFS": "Secure",
    "TDSC": "Secure",
    "SOUPS": "Secure",
    "ICCV": "Computer Vision",
    "CVPR": "Computer Vision",
    "ECCV": "Computer Vision",
    "MM": "Computer Vision",
    "IJCV": "Computer Vision",
    "ACL": "Natural Language Processing",
    "EMNLP": "Natural Language Processing",
    "NAACL": "Natural Language Processing",
    "COLING": "Natural Language Processing",
    "SIGIR": "Information Retrieval",
    "CIKM": "Information Retrieval",
    "SIGMOD": "Database",
    "ICDE": "Database",
    "VLDB": "Database",
    "SIGCOMM": "Network",
    "INFOCOM": "Network",
    "MOBICOM": "Network",
    "NSDI": "Network",
    "WWW": "Network",
    "OSDI": "System",
    "SOSP": "System",
    "ISCA": "System",
    "MLSys": "System",
    "EuroSys": "System",
    "TPDS": "System",
    "DAC": "System",
    "TOCS": "System",
    "TOS": "System",
    "TCAD": "System",
    "TC": "System",
    "ICSE": "Others",
    "FOCS": "Others",
    "STOC": "Others",
    "ICDAR": "Others",
}

CATEGORY_ORDER = [
    "Artificial Intelligence", "Machine Learning", "Data Mining", "Secure",
    "Computer Vision", "Natural Language Processing", "Information Retrieval",
    "Database", "Network", "System", "Others",
]

VENUE_ORDER = {
    "Artificial Intelligence": ["IJCAI", "AAAI", "AISTATS", "ALT", "AI"],
    "Machine Learning": ["NeurIPS", "ICML", "ICLR", "COLT", "UAI", "Machine Learning", "JMLR", "TPAMI", "TMLR"],
    "Data Mining": ["KDD", "WSDM", "TKDE", "Big Data"],
    "Secure": ["S&P", "CCS", "USENIX Security", "NDSS", "TIFS", "TDSC", "SOUPS"],
    "Computer Vision": ["ICCV", "CVPR", "ECCV", "MM", "IJCV"],
    "Natural Language Processing": ["ACL", "EMNLP", "NAACL", "COLING"],
    "Information Retrieval": ["SIGIR", "CIKM"],
    "Database": ["SIGMOD", "ICDE", "VLDB"],
    "Network": ["SIGCOMM", "INFOCOM", "MOBICOM", "NSDI", "WWW"],
    "System": ["OSDI", "SOSP", "ISCA", "MLSys", "EuroSys", "TPDS", "DAC", "TOCS", "TOS", "TCAD", "TC"],
    "Others": ["ICSE", "FOCS", "STOC", "ICDAR"],
}


def _is_low_priority(title):
    t = title.strip()
    if not t:
        return False
    has_brackets = any(c in t for c in ("(", ")", "（", "）"))
    has_keywords = any(kw in t.lower() for kw in ("abstract", "poster"))
    return has_brackets or has_keywords


def main():
    root = project_root()
    with open(root / "cached" / "dblp.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    with open(root / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    keywords = []
    for line in (config.get("dblp") or {}).get("lines") or []:
        keywords.extend(str(k).strip() for k in (line.get("keywords") or []) if str(k).strip())
    priority_keyword = keywords[0].lower() if keywords else ""

    aggregated = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    unknown_venues = set()
    for _key, papers in data.items():
        if not isinstance(papers, list):
            continue
        for paper in papers:
            raw_venue = (paper.get("venue") or "").strip()
            if not raw_venue:
                continue
            venue = VENUE_MAP.get(raw_venue, raw_venue)
            category = CATEGORY_MAP.get(venue)
            if category is None:
                unknown_venues.add(raw_venue)
                continue
            try:
                year = int(paper.get("year", ""))
            except (TypeError, ValueError):
                continue
            aggregated[category][year][venue].append(paper)

    if unknown_venues:
        print("[WARN] Unknown venues (skipped):")
        for venue in sorted(unknown_venues):
            print(f"  - {venue}")

    lines = ["# FL Papers", ""]
    for category in CATEGORY_ORDER:
        if category not in aggregated:
            continue
        lines.append(f"## {category}")
        lines.append("")
        for year in sorted(aggregated[category].keys(), reverse=True):
            lines.append(f"### {year}")
            lines.append("")
            venue_order = {v: i for i, v in enumerate(VENUE_ORDER.get(category, []))}
            for venue in sorted(aggregated[category][year].keys(), key=lambda v: (venue_order.get(v, 999), v)):
                lines.append(f"#### {venue}")
                lines.append("")
                papers = sorted(
                    aggregated[category][year][venue],
                    key=lambda p: (
                        1 if _is_low_priority(p.get("title", "")) else 0,
                        0 if priority_keyword and priority_keyword in (p.get("title") or "").lower() else 1,
                        (p.get("title") or "").lower(),
                    ),
                )
                for paper in papers:
                    title = (paper.get("title") or "").strip()
                    ee = (paper.get("ee") or "").strip()
                    code = (paper.get("related_code") or "").strip()
                    suffix = "" if title.endswith(".") else "."
                    parts = [f"- {title}{suffix}"]
                    if ee:
                        parts.append(f"[[PUB]({ee})]")
                    if code:
                        parts.append(f"[[CODE]({code})]")
                    lines.append(" ".join(parts))
                lines.append("")

    output = root / "FL-Papers.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Done! Written to {output}")


if __name__ == "__main__":
    main()
