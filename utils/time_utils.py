from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))
def get_kst_now() -> datetime:
    return datetime.now(KST)
def to_kst(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=KST)
    return dt.astimezone(KST)
def format_dt(dt_or_ts, fmt="%Y-%m-%d %H:%M:%S") -> str:
    if isinstance(dt_or_ts, (int, float)):
        dt = datetime.fromtimestamp(dt_or_ts, KST)
    else:
        dt = to_kst(dt_or_ts)
    return dt.strftime(fmt)