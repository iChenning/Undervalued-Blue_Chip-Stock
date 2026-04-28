from __future__ import annotations

import argparse
import csv
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


COLUMNS = [
    "股票名称",
    "时间",
    "最终裁决",
    "数据时效声明",
    "排雷过滤器",
    "现价",
    "止损位",
    "第一目标价",
    "第二目标价",
    "保守盈亏比",
    "下跌10%的概率",
    "下跌20%的概率",
]

REPORT_FILE_RE = re.compile(r"^(?P<stock>.+)-(?P<date>\d{4}-\d{2}-\d{2})\.md$")
FLAG_SUMMARY_RE = re.compile(r"^\*排雷结论：(?P<value>.+)\*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="汇总当前目录下的股票分析 Markdown 报告为表格文件。"
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        default=".",
        help="待扫描的目录，默认是当前目录。",
    )
    parser.add_argument(
        "--csv",
        default="analysis_summary.csv",
        help="输出 CSV 文件名，默认 analysis_summary.csv。",
    )
    parser.add_argument(
        "--md",
        default="analysis_summary.md",
        help="输出 Markdown 文件名，默认 analysis_summary.md。",
    )
    parser.add_argument(
        "--xlsx",
        default="analysis_summary.xlsx",
        help="输出 Excel 文件名，默认 analysis_summary.xlsx。",
    )
    return parser.parse_args()


def normalize_line(raw_line: str) -> str:
    line = raw_line.strip()
    if line.startswith("- "):
        line = line[2:]
    return line.replace("**", "").strip()


def clean_value(value: str) -> str:
    return value.replace("**", "").replace("`", "").strip()


def extract_bracket_value(value: str) -> str:
    cleaned = clean_value(value)
    if cleaned.startswith("【") and cleaned.endswith("】"):
        return cleaned[1:-1].strip()
    return cleaned


def strip_after_markers(value: str, markers: tuple[str, ...]) -> str:
    cleaned = clean_value(value)
    for marker in markers:
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[0].strip()
    return cleaned


def strip_parenthetical(value: str) -> str:
    return strip_after_markers(value, (" (", "（"))


def strip_reasoning(value: str) -> str:
    return strip_after_markers(value, (" (依据：", "（依据："))


def extract_fields(content: str) -> dict[str, str]:
    fields: dict[str, str] = {column: "" for column in COLUMNS}

    for raw_line in content.splitlines():
        stripped = raw_line.strip()

        flag_match = FLAG_SUMMARY_RE.match(stripped)
        if flag_match:
            fields["排雷过滤器"] = clean_value(flag_match.group("value"))
            continue

        line = normalize_line(raw_line)
        if not line:
            continue

        if line.startswith("最终裁决："):
            fields["最终裁决"] = extract_bracket_value(line.split("：", 1)[1])
        elif line.startswith("数据时效声明："):
            fields["数据时效声明"] = extract_bracket_value(line.split("：", 1)[1])
        elif line.startswith("现价位置："):
            fields["现价"] = strip_parenthetical(line.split("：", 1)[1])
        elif line.startswith("预定止损位(撤退线)："):
            fields["止损位"] = strip_parenthetical(line.split("：", 1)[1])
        elif line.startswith("第一目标价(估值修复)："):
            fields["第一目标价"] = strip_parenthetical(line.split("：", 1)[1])
        elif line.startswith("第二目标价(景气反转)："):
            fields["第二目标价"] = strip_parenthetical(line.split("：", 1)[1])
        elif line.startswith("保守盈亏比："):
            fields["保守盈亏比"] = strip_parenthetical(line.split("：", 1)[1])
        elif line.startswith("当前价下跌 10%") and "概率：" in line:
            fields["下跌10%的概率"] = strip_reasoning(line.split("概率：", 1)[1])
        elif line.startswith("当前价下跌 20%") and "概率：" in line:
            fields["下跌20%的概率"] = strip_reasoning(line.split("概率：", 1)[1])

    return fields


def build_row(file_path: Path) -> dict[str, str]:
    match = REPORT_FILE_RE.match(file_path.name)
    if not match:
        raise ValueError(f"文件名不符合预期格式: {file_path.name}")

    content = file_path.read_text(encoding="utf-8")
    row = extract_fields(content)
    row["股票名称"] = match.group("stock")
    row["时间"] = match.group("date")
    return row


def escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def write_csv(output_path: Path, rows: list[dict[str, str]]) -> None:
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(output_path: Path, rows: list[dict[str, str]]) -> None:
    lines = [
        "| " + " | ".join(COLUMNS) + " |",
        "| " + " | ".join(["---"] * len(COLUMNS)) + " |",
    ]

    for row in rows:
        cells = [escape_markdown_cell(row.get(column, "")) for column in COLUMNS]
        lines.append("| " + " | ".join(cells) + " |")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def excel_column_name(index: int) -> str:
        name = ""
        current = index + 1
        while current > 0:
                current, remainder = divmod(current - 1, 26)
                name = chr(ord("A") + remainder) + name
        return name


def text_display_width(value: str) -> int:
        width = 0
        for char in value:
                width += 2 if ord(char) > 127 else 1
        return width


def build_column_widths(rows: list[dict[str, str]]) -> list[float]:
        widths: list[float] = []
        for column in COLUMNS:
                max_width = text_display_width(column)
                for row in rows:
                        max_width = max(max_width, text_display_width(row.get(column, "")))

                widths.append(min(max(max_width * 0.9 + 2, 12), 60))
        return widths


def make_excel_cell(row_index: int, column_index: int, value: str, style_id: int) -> str:
        cell_ref = f"{excel_column_name(column_index)}{row_index}"
        escaped = escape(value)
        return (
                f'<c r="{cell_ref}" t="inlineStr" s="{style_id}">'
                f'<is><t xml:space="preserve">{escaped}</t></is>'
                f"</c>"
        )


def write_xlsx(output_path: Path, rows: list[dict[str, str]]) -> None:
        total_rows = len(rows) + 1
        last_cell = f"{excel_column_name(len(COLUMNS) - 1)}{total_rows}"
        column_widths = build_column_widths(rows)

        header_cells = "".join(
                make_excel_cell(1, index, column, style_id=1)
                for index, column in enumerate(COLUMNS)
        )
        sheet_rows = [f'<row r="1">{header_cells}</row>']

        for row_index, row in enumerate(rows, start=2):
                body_cells = "".join(
                        make_excel_cell(row_index, column_index, row.get(column, ""), style_id=0)
                        for column_index, column in enumerate(COLUMNS)
                )
                sheet_rows.append(f'<row r="{row_index}">{body_cells}</row>')

        cols_xml = "".join(
                f'<col min="{index}" max="{index}" width="{width:.1f}" customWidth="1"/>'
                for index, width in enumerate(column_widths, start=1)
        )

        worksheet_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <dimension ref="A1:{last_cell}"/>
    <sheetViews>
        <sheetView workbookViewId="0">
            <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
        </sheetView>
    </sheetViews>
    <sheetFormatPr defaultRowHeight="18"/>
    <cols>{cols_xml}</cols>
    <sheetData>{sheet_rows}</sheetData>
    <autoFilter ref="A1:{last_cell}"/>
</worksheet>
""".format(last_cell=last_cell, cols_xml=cols_xml, sheet_rows="".join(sheet_rows))

        workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <sheets>
        <sheet name="汇总" sheetId="1" r:id="rId1"/>
    </sheets>
</workbook>
"""

        workbook_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""

        root_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

        content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
    <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
    <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>
"""

        styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <fonts count="2">
        <font><sz val="11"/><name val="Calibri"/></font>
        <font><b/><sz val="11"/><name val="Calibri"/></font>
    </fonts>
    <fills count="2">
        <fill><patternFill patternType="none"/></fill>
        <fill><patternFill patternType="gray125"/></fill>
    </fills>
    <borders count="1">
        <border><left/><right/><top/><bottom/><diagonal/></border>
    </borders>
    <cellStyleXfs count="1">
        <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
    </cellStyleXfs>
    <cellXfs count="2">
        <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">
            <alignment vertical="top" wrapText="1"/>
        </xf>
        <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyAlignment="1" applyFont="1">
            <alignment vertical="top" wrapText="1"/>
        </xf>
    </cellXfs>
    <cellStyles count="1">
        <cellStyle name="Normal" xfId="0" builtinId="0"/>
    </cellStyles>
</styleSheet>
"""

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", content_types_xml)
                archive.writestr("_rels/.rels", root_rels_xml)
                archive.writestr("xl/workbook.xml", workbook_xml)
                archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
                archive.writestr("xl/styles.xml", styles_xml)
                archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)


def collect_rows(input_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    report_files = sorted(
        file_path
        for file_path in input_dir.iterdir()
        if file_path.is_file() and REPORT_FILE_RE.match(file_path.name)
    )

    for file_path in report_files:
        row = build_row(file_path)
        rows.append(row)

        missing_fields = [
            column
            for column in COLUMNS[2:]
            if not row.get(column, "").strip()
        ]
        if missing_fields:
            missing_text = "、".join(missing_fields)
            print(f"[WARN] {file_path.name} 缺少字段: {missing_text}", file=sys.stderr)

    rows.sort(key=lambda item: (item["时间"], item["股票名称"]))
    return rows


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"输入目录不存在或不是目录: {input_dir}", file=sys.stderr)
        return 1

    rows = collect_rows(input_dir)
    if not rows:
        print(f"未在 {input_dir} 下找到符合命名规则的分析文档。", file=sys.stderr)
        return 1

    csv_path = input_dir / args.csv
    md_path = input_dir / args.md
    xlsx_path = input_dir / args.xlsx
    write_csv(csv_path, rows)
    write_markdown(md_path, rows)
    write_xlsx(xlsx_path, rows)

    print(f"已汇总 {len(rows)} 份报告")
    print(f"CSV: {csv_path}")
    print(f"Markdown: {md_path}")
    print(f"Excel: {xlsx_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())