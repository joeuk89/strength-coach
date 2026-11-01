import datetime


def utc_instant(moment: datetime.datetime) -> str:
    """An instant as the store writes it: ISO text in UTC with seconds (schema.md, "DDL")."""
    return moment.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_instant(text: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(text)
