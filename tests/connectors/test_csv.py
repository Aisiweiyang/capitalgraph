"""CSV fixture 连接器测试：schema contract、坏行隔离、实体推断。"""

from datetime import date

import pytest
from cg_connectors.base import ConnectorContext
from cg_connectors.csv_source import CsvFixtureConnector
from cg_connectors.ingest import run_connector
from cg_domain.errors import RatioError
from cg_domain.repo import Repository

VALID_CSV = """record_type,subject_id,subject_name,subject_uscc,predicate,object_id,object_name,object_uscc,ratio,ratio_unit,valid_from,valid_to,evidence_url,field_path,raw_value
entity,COMPANY-1,示例甲有限公司,91110000ABCDEF01X9,,,,,,,,,,,
entity,PERSON-1,张测试,,,,,,,,,,,,,
holding,PERSON-1,张测试,,h0,COMPANY-1,示例甲有限公司,,51.00,percent,2020-01-01,,https://example.gov/a,row[2].ratio,51.00%
holding,COMPANY-1,示例甲有限公司,91110000ABCDEF01X9,holds,COMPANY-2,示例乙有限公司,,55.50,percent,2021-06-30,,https://example.gov/b,row[3].ratio,55.50
control,COMPANY-1,示例甲有限公司,,ctrl,COMPANY-2,示例乙有限公司,,,percent,2021-06-30,,https://example.gov/c,row[4].control,是
"""

BAD_ROWS_CSV = (
    VALID_CSV
    + "holding,PERSON-1,张测试,,h1,COMPANY-1,示例甲有限公司,,101.0,percent,2020-01-01,,x,f,101%\n"
    + "frobnicate,A,B,,,,,,,,,,,\n"
    + "holding,PERSON-1,张测试,,h2,COMPANY-1,示例甲有限公司,,abc,percent,2020-01-01,,x,f,abc\n"
)


def write_csv(tmp_path, content: str):
    path = tmp_path / "fixture.csv"
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_csv_schema_mismatch(tmp_path):
    path = write_csv(tmp_path, "a,b,c\n1,2,3\n")
    connector = CsvFixtureConnector()
    batches = list(connector.fetch(ConnectorContext(params={"path": path})))
    _result, issue = batches[0]
    assert issue is not None
    assert issue.code == "schema_mismatch"
    assert "record_type" in issue.message


def test_csv_file_not_found():
    connector = CsvFixtureConnector()
    result, issue = next(iter(connector.fetch(ConnectorContext(params={"path": "Z:/nope.csv"}))))
    assert issue is not None and issue.code == "file_not_found"
    assert result.entities == []


def test_csv_valid_rows_parse(tmp_path):
    path = write_csv(tmp_path, VALID_CSV)
    connector = CsvFixtureConnector()
    (result, issue), *_ = list(connector.fetch(ConnectorContext(params={"path": path})))
    assert issue is None
    assert len(result.entities) == 3  # COMPANY-1/2 + PERSON-1
    assert len(result.statements) == 3
    holding = result.statements[0]
    assert holding.share_ratio == 51.0
    assert holding.valid_from == date(2020, 1, 1)
    assert holding.evidence[0].raw_value == "51.00%"
    control = result.statements[2]
    assert control.control_type is not None


def test_csv_bad_rows_isolated_not_fatal(tmp_path):
    path = write_csv(tmp_path, BAD_ROWS_CSV)
    connector = CsvFixtureConnector()
    batches = list(connector.fetch(ConnectorContext(params={"path": path})))
    first_result, first_issue = batches[0]
    # 第一批正常记录入库；坏行以 issue 报告，不中断
    assert len(first_result.statements) == 3
    codes = {first_issue.code if first_issue else ""}
    issues = [first_issue] + [i for _, i in batches[1:]]
    codes |= {i.code for i in issues if i}
    assert "row_rejected" in codes
    joined = "; ".join(i.message for i in issues if i)
    assert "比例越界" in joined or "could not convert" in joined or "abc" in joined


def test_csv_max_records_guard(tmp_path):
    rows = [
        "record_type,subject_id,subject_name,subject_uscc,predicate,object_id,object_name,object_uscc,ratio,ratio_unit,valid_from,valid_to,evidence_url,field_path,raw_value"
    ]
    for i in range(10):
        rows.append(f"holding,P{i},人{i},,h{i},C{i},公司{i},,1.00,percent,2020-01-01,,x,f,1%")
    path = write_csv(tmp_path, "\n".join(rows))
    connector = CsvFixtureConnector()
    batches = list(connector.fetch(ConnectorContext(params={"path": path}, max_records=5)))
    _first_result, first_issue = batches[0]
    assert first_issue is not None
    assert first_issue.code == "max_records"


@pytest.mark.asyncio
async def test_csv_end_to_end_ingestion(db_session, tmp_path):
    path = write_csv(tmp_path, VALID_CSV)
    connector = CsvFixtureConnector()
    stats = await run_connector(db_session, connector, ConnectorContext(params={"path": path}))
    assert stats is not None
    assert stats.entities_created == 3
    assert stats.statements_created == 3

    repo = Repository(db_session)
    hits, total = await repo.search("示例甲")
    assert total == 1
    detail_in = await repo.neighbours(hits[0].id)
    assert any(s.predicate == "holds_shares" for s in detail_in["incoming"])
    # 幂等：再次运行跳过
    stats2 = await run_connector(db_session, connector, ConnectorContext(params={"path": path}))
    assert stats2 is None


def test_ratio_out_of_range_rejected_by_contract():
    from datetime import date

    from cg_domain.enums import Predicate
    from cg_domain.models import StatementRecord

    with pytest.raises(RatioError):
        StatementRecord(
            subject_key="src:csv:A",
            predicate=Predicate.HOLDS_SHARES,
            object_key="src:csv:B",
            valid_from=date(2020, 1, 1),
            share_ratio=101.0,
        )


RICH_HEADER = (
    "record_type,subject_id,subject_name,subject_uscc,region_code,industry,"
    "predicate,object_id,object_name,object_uscc,ratio,ratio_unit,valid_from,valid_to,"
    "evidence_url,field_path,raw_value,amount_wan"
)

RICH_ENTITY_A = "entity,COMPANY-A,示例甲有限公司,91110000ABCDEF01X9,110000,金融业,,,,,,,,,,,,,"
RICH_ENTITY_B = "entity,COMPANY-B,示例乙科技有限公司,,310000,科学研究和技术服务业,,,,,,,,,,,,,"
RICH_HOLDING = (
    "holding,COMPANY-A,示例甲有限公司,,110000,,h0,COMPANY-B,示例乙科技有限公司,,"
    "66.60,percent,2022-03-01,,https://example.gov/r1,row[3].ratio,66.6,80.0"
)


def test_csv_optional_dimension_columns(tmp_path):
    """可选列 region_code/industry/amount_wan：合法值进入领域记录。"""
    from cg_connectors.base import ConnectorContext
    from cg_connectors.csv_source import CsvFixtureConnector

    path = write_csv(tmp_path, "\n".join([RICH_HEADER, RICH_ENTITY_A, RICH_ENTITY_B, RICH_HOLDING]))
    connector = CsvFixtureConnector()
    batches = list(connector.fetch(ConnectorContext(params={"path": path}, max_records=100)))
    result = batches[0][0]
    by_ext = {e.external_id: e for e in result.entities}
    assert by_ext["COMPANY-A"].region_code == "110000"
    assert by_ext["COMPANY-A"].industry == "金融业"
    assert by_ext["COMPANY-B"].region_code == "310000"
    # 关系行的金额进入声明记录（万元 → amount_scaled 由模型换算）
    stmt = next(s for s in result.statements if s.predicate.value == "holds_shares")
    assert stmt.amount_wan == 80.0
    assert stmt.amount_scaled == 8000  # 万元×100


def test_csv_invalid_region_code_rejects_row(tmp_path):
    """region_code 非省级代码 → 该行拒绝（坏行隔离），其余照常。"""
    from cg_connectors.base import ConnectorContext
    from cg_connectors.csv_source import CsvFixtureConnector

    bad_row = RICH_HOLDING.replace(",,110000,,h0", ",,999999,,h0")
    path = write_csv(tmp_path, "\n".join([RICH_HEADER, RICH_ENTITY_A, RICH_ENTITY_B, bad_row]))
    connector = CsvFixtureConnector()
    batches = list(connector.fetch(ConnectorContext(params={"path": path}, max_records=100)))
    issues = [issue for _, issue in batches if issue is not None]
    assert any("region_code" in (i.message or "") for i in issues)
    # 坏行被隔离，好的 entity 行仍然导入
    result = batches[0][0]
    assert {e.external_id for e in result.entities} >= {"COMPANY-A", "COMPANY-B"}


def test_csv_relative_path_accepted(tmp_path, monkeypatch):
    """相对路径参数应被解析为绝对路径后读取（as_uri 兼容），不抛 ValueError。"""
    from cg_connectors.base import ConnectorContext
    from cg_connectors.csv_source import CsvFixtureConnector

    write_csv(tmp_path, VALID_CSV)
    monkeypatch.chdir(tmp_path)
    connector = CsvFixtureConnector()
    batches = list(
        connector.fetch(ConnectorContext(params={"path": "fixture.csv"}, max_records=100))
    )
    result, issue = batches[0]
    assert issue is None
    assert len(result.entities) == 3
    assert "fixture.csv" in result.raw_payloads
