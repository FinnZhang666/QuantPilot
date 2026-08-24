import csv
import io
import re
import zipfile
from html.parser import HTMLParser
from decimal import Decimal, InvalidOperation
from typing import List
from xml.etree import ElementTree

from app.universe.models import HoldingRecord


SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")


def normalize_symbol(value: object) -> str:
    symbol = str(value or "").strip().upper().replace("US.", "").replace("/", ".")
    if not SYMBOL_RE.fullmatch(symbol) or symbol in {"USD", "CASH", "N/A", "NA"}:
        return ""
    return symbol


def _decimal(value):
    text = str(value or "").replace("%", "").replace(",", "").replace("$", "").strip()
    if not text or text in {"-", "--", "N/A"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def parse_rows(rows: List[List[str]]) -> List[HoldingRecord]:
    aliases = {
        "symbol": {"ticker", "holdingticker", "symbol", "tickersymbol"},
        "name": {"name", "holdingname", "securityname", "companyname"},
        "weight": {"weight", "weightpercent", "weighting", "weightpct"},
        "sector": {"sector", "gicssector"}, "industry": {"industry", "gicsindustry"},
        "market_cap": {"marketcap", "marketcapitalization"},
    }
    header_at = -1
    columns = {}
    for index, row in enumerate(rows[:80]):
        normalized = [_key(cell) for cell in row]
        for field, names in aliases.items():
            for position, value in enumerate(normalized):
                if value in names:
                    columns[field] = position
                    break
        if "symbol" in columns:
            header_at = index
            break
        columns = {}
    if header_at < 0:
        raise ValueError("持仓文件中未找到Ticker/Symbol表头。")
    output = {}
    for row in rows[header_at + 1:]:
        def cell(field):
            pos = columns.get(field)
            return row[pos].strip() if pos is not None and pos < len(row) else ""
        symbol = normalize_symbol(cell("symbol"))
        if not symbol:
            continue
        output[symbol] = HoldingRecord(
            symbol=symbol, company_name=cell("name") or None,
            weight=_decimal(cell("weight")), sector=cell("sector") or None,
            industry=cell("industry") or None, market_cap=_decimal(cell("market_cap")),
        )
    if not output:
        raise ValueError("持仓文件没有有效证券记录。")
    return list(output.values())


def parse_csv(content: bytes) -> List[HoldingRecord]:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = content.decode(encoding)
            return parse_rows(list(csv.reader(io.StringIO(text))))
        except UnicodeDecodeError:
            continue
    raise ValueError("持仓CSV编码无法识别。")


def parse_xlsx(content: bytes) -> List[HoldingRecord]:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(namespace + "si"):
                shared.append("".join(node.text or "" for node in item.iter(namespace + "t")))
        sheet_name = next(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
        root = ElementTree.fromstring(archive.read(sheet_name))
        rows = []
        for row in root.iter(namespace + "row"):
            values = []
            for cell in row.findall(namespace + "c"):
                ref = cell.attrib.get("r", "A1")
                col = 0
                for char in re.match(r"[A-Z]+", ref).group(0):
                    col = col * 26 + ord(char) - 64
                while len(values) < col:
                    values.append("")
                node = cell.find(namespace + "v")
                value = node.text if node is not None else ""
                if cell.attrib.get("t") == "s" and value:
                    value = shared[int(value)]
                elif cell.attrib.get("t") == "inlineStr":
                    value = "".join(n.text or "" for n in cell.iter(namespace + "t"))
                values[col - 1] = value
            rows.append(values)
    return parse_rows(rows)


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.table, self.row, self.cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table": self.table = []
        elif tag == "tr" and self.table is not None: self.row = []
        elif tag in ("th", "td") and self.row is not None: self.cell = []

    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split())); self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row: self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table); self.table = None


def parse_html(content: bytes) -> List[HoldingRecord]:
    parser = _TableParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    errors = []
    for table in parser.tables:
        try:
            return parse_rows(table)
        except ValueError as exc:
            errors.append(str(exc))
    raise ValueError("HTML中未找到有效持仓表。")


def parse_holdings(content: bytes, file_format: str) -> List[HoldingRecord]:
    if file_format == "xlsx": return parse_xlsx(content)
    if file_format == "html": return parse_html(content)
    return parse_csv(content)
