import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .schemas import DocumentBlock, Evidence, FindingDraft


@dataclass
class Fact:
    value: object
    display: str
    block: DocumentBlock


def run_consistency_rules(
    tender_blocks: list[DocumentBlock], bid_blocks: list[DocumentBlock]
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []

    tender_amount = _amount(tender_blocks, "最高投标限价|最高限价|预算金额|项目预算")
    bid_amount = _amount(bid_blocks, "投标报价|报价金额|总报价")
    if tender_amount and bid_amount and bid_amount.value > tender_amount.value:
        findings.append(
            _finding(
                "amount",
                "投标报价超过招标限价",
                f"投标报价 {bid_amount.display} 高于招标限价 {tender_amount.display}。",
                "核对报价汇总和分项报价，确保最终投标报价不超过招标限价。",
                tender_amount,
                bid_amount,
                0.99,
            )
        )

    tender_date = _deadline(tender_blocks)
    bid_date = _deadline(bid_blocks)
    if tender_date and bid_date and tender_date.value != bid_date.value:
        findings.append(
            _finding(
                "date",
                "投标截止日期不一致",
                f"招标文件截止日期为 {tender_date.display}，投标文件填写为 {bid_date.display}。",
                "统一投标文件中的截止日期，并以招标文件及最新澄清文件为准。",
                tender_date,
                bid_date,
                0.98,
            )
        )

    tender_name = _project_name(tender_blocks)
    bid_name = _project_name(bid_blocks)
    if tender_name and bid_name and _normalize_name(tender_name.display) != _normalize_name(bid_name.display):
        findings.append(
            _finding(
                "project_name",
                "项目名称不一致",
                f"招标项目名称为“{tender_name.display}”，投标文件填写为“{bid_name.display}”。",
                "统一封面、报价表和响应文件中的项目名称，以招标文件名称为准。",
                tender_name,
                bid_name,
                0.99,
            )
        )

    tender_duration = _duration(tender_blocks)
    bid_duration = _duration(bid_blocks)
    if tender_duration and bid_duration:
        maximum = tender_duration.display.startswith("不超过")
        conflict = (
            bid_duration.value > tender_duration.value
            if maximum
            else bid_duration.value != tender_duration.value
        )
        if conflict:
            findings.append(
                _finding(
                    "duration",
                    "投标工期不符合招标要求",
                    f"招标工期要求{tender_duration.display}，投标文件承诺{bid_duration.display}。",
                    "修正工期承诺及进度计划，确保不超过招标文件规定的工期。",
                    tender_duration,
                    bid_duration,
                    0.99,
                )
            )

    return findings


def _amount(blocks: list[DocumentBlock], labels: str) -> Fact | None:
    pattern = re.compile(
        rf"(?:{labels})[^0-9]{{0,20}}([0-9][0-9,]*(?:\.[0-9]+)?)\s*(万元|元)"
    )
    for block in blocks:
        if match := pattern.search(block.content):
            value = Decimal(match.group(1).replace(",", ""))
            if match.group(2) == "万元":
                value *= 10_000
            return Fact(value, f"{value:,.2f} 元", block)
    return None


def _deadline(blocks: list[DocumentBlock]) -> Fact | None:
    pattern = re.compile(
        r"(?:投标截止时间|投标截止日期|截止时间|截止日期)[^0-9]{0,12}"
        r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?"
    )
    for block in blocks:
        if match := pattern.search(block.content):
            try:
                value = date(*(int(part) for part in match.groups()))
            except ValueError:
                continue
            return Fact(value, value.isoformat(), block)
    return None


def _project_name(blocks: list[DocumentBlock]) -> Fact | None:
    pattern = re.compile(r"项目名称\s*[：:]\s*([^\n。；;]{2,100})")
    for block in blocks:
        if match := pattern.search(block.content):
            value = match.group(1).strip()
            return Fact(value, value, block)
    return None


def _duration(blocks: list[DocumentBlock]) -> Fact | None:
    pattern = re.compile(r"(?:建设)?工期([^0-9]{0,20})(\d+)\s*(?:个)?日历天")
    for block in blocks:
        if match := pattern.search(block.content):
            days = int(match.group(2))
            is_maximum = any(word in match.group(1) for word in ("不得超过", "不超过", "≤"))
            return Fact(days, f"{'不超过' if is_maximum else '为'} {days} 日历天", block)
    return None


def _normalize_name(value: str) -> str:
    return re.sub(r"[\s·•_—－（）()《》“”\"'，,。.;；:：-]", "", value).casefold()


def _finding(
    category: str,
    title: str,
    description: str,
    suggestion: str,
    tender: Fact,
    bid: Fact,
    confidence: float,
) -> FindingDraft:
    return FindingDraft(
        category=category,
        risk_level="medium" if category == "date" else "high",
        title=title,
        description=description,
        suggestion=suggestion,
        evidence=[_evidence(tender.block, "tender"), _evidence(bid.block, "bid")],
        confidence=confidence,
    )


def _evidence(block: DocumentBlock, role: str) -> Evidence:
    return Evidence(
        block_id=block.id,
        page_number=block.page_number,
        excerpt=block.content[:500],
        document_role=role,
        location_confidence=block.location_confidence,
    )
