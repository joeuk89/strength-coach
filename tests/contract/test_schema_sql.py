import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCHEMA_DOC = REPO / "docs" / "spec" / "schema.md"
SCHEMA_SQL = REPO / "src" / "coach" / "store" / "schema.sql"

SQL_BLOCK = re.compile(r"^```sql\n(.*?)^```$", re.MULTILINE | re.DOTALL)


def sql_blocks(markdown: str) -> str:
    return "\n".join(SQL_BLOCK.findall(markdown))


def test_schema_sql_is_byte_identical_to_the_sql_blocks_of_schema_md() -> None:
    # The one permitted read of a spec document (docs/spec/testing.md, "Two explicit exceptions").
    expected = sql_blocks(SCHEMA_DOC.read_text(encoding="utf-8")).encode("utf-8")

    assert SCHEMA_SQL.read_bytes() == expected
