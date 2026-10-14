from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Any, List

import pandas as pd

from .. import Snapshot, _rs
from .._bridge import to_ts
from .._typing import DemeterError


def _ts(snapshot_or_time) -> int:
    """timestamp in seconds of a snapshot (engine snapshots carry it as `.ts`) or a datetime"""
    ts = getattr(snapshot_or_time, "ts", None)
    if isinstance(ts, int):
        return ts
    t = getattr(snapshot_or_time, "timestamp", snapshot_or_time)
    return to_ts(t)


def to_minute(time: datetime) -> datetime:
    """
    Convert a datetime instance to minute(Just set its second to 0)

    :param time: time instance to convert
    :type time: datetime
    :return: time whose second is zero
    :rtype: datetime
    """
    return datetime(time.year, time.month, time.day, time.hour, time.minute)


class Trigger:
    """
    Abstract trigger.

    Trigger will do something(decide by do function) when condition is met(decide by when function)

    Extra args can be passed through kwargs. e.g. tg = Trigger(lambda r:r, extra_arg1=0, extra_arg2="1")

    :param do: which action to take.
    :type do: Callable[[RowData], Any]
    """

    def __init__(self, do: Callable[[Snapshot], Any], **kwargs):
        self._do = do if do is not None else lambda x: x
        self.kwargs = kwargs

    def when(self, snapshot: Snapshot) -> bool:
        """
        If the condition is met or not.

        :param snapshot: data of this iteration. used to decide to if the condition is meet.
        :type snapshot: Snapshot
        :return: if condition is met, return true
        :rtype: bool
        """
        return False

    def do(self, snapshot: Snapshot):
        """
        when condition is met, what actions will be taken

        :param snapshot: data of this iteration
        :type snapshot: condition
        :return: Anything do function returns
        :rtype: Any
        """
        return self._do(snapshot, **self.kwargs)

    def is_out_date(self, t) -> bool:
        return False


class AtTimeTrigger(Trigger):
    """
    Trigger action at a specific time

    Extra args can be passed through kwargs.

    :param time: time to trigger action
    :type time: datetime
    :param do: which action to take.
    :type do: Callable[[RowData], Any]
    """

    def __init__(self, time: datetime, do, **kwargs):
        self._time = to_minute(time)
        self._native = _rs.NativeTrigger.at_time(to_ts(self._time))
        super().__init__(do, **kwargs)

    def when(self, snapshot: Snapshot) -> bool:
        return self._native.when_ts(_ts(snapshot))

    def is_out_date(self, t) -> bool:
        return self._native.is_out_date_ts(_ts(t))


class AtTimesTrigger(Trigger):
    """
    trigger action at some specific times

    Extra args can be passed through kwargs.

    :param time: when current timestamp is in List[datetime], will trigger action
    :type time: List[datetime]
    :param do: which action to take.
    :type do: Callable[[RowData], Any]

    """

    def __init__(self, time: List[datetime], do, **kwargs):
        self._time = [to_minute(t) for t in time]
        self._native = _rs.NativeTrigger.at_times([to_ts(t) for t in self._time])
        super().__init__(do, **kwargs)

    def when(self, snapshot: Snapshot) -> bool:
        # fixed: the python version did `self._time in snapshot.timestamp` and raised TypeError
        return self._native.when_ts(_ts(snapshot))

    def is_out_date(self, t) -> bool:
        return self._native.is_out_date_ts(_ts(t))


@dataclass
class TimeRange:
    """
    Time range
    """

    start: datetime
    end: datetime


class TimeRangeTrigger(Trigger):
    """
    trigger action at a time range

    Extra args can be passed through kwargs. e.g. tg = Trigger(lambda r:r, extra_arg1=0, extra_arg2="1")

    :param time_range: when current timestamp is between time range, will trigger action, end time will not be included
    :type time_range: TimeRange
    :param do: which action to take.
    :type do: Callable[[RowData], Any]
    """

    def __init__(self, time_range: TimeRange, do, **kwargs):
        self._time_range = TimeRange(to_minute(time_range.start), to_minute(time_range.end))
        self._native = _rs.NativeTrigger.time_range(to_ts(self._time_range.start), to_ts(self._time_range.end))
        super().__init__(do, **kwargs)

    def when(self, snapshot: Snapshot) -> bool:
        return self._native.when_ts(_ts(snapshot))

    def is_out_date(self, t) -> bool:
        return self._native.is_out_date_ts(_ts(t))


class TimeRangesTrigger(Trigger):
    """
    trigger action at some time range

    Extra args can be passed through kwargs. e.g. tg = Trigger(lambda r:r, extra_arg1=0, extra_arg2="1")

    :param time_range: when current timestamp is between any time range, will trigger action, end time will not be included
    :type time_range: List[TimeRange]
    :param do: which action to take.
    :type do: Callable[[RowData], Any]
    """

    def __init__(self, time_range: List[TimeRange], do, **kwargs):
        self._time_range: [TimeRange] = [TimeRange(to_minute(t.start), to_minute(t.end)) for t in time_range]
        self._native = _rs.NativeTrigger.time_ranges([(to_ts(r.start), to_ts(r.end)) for r in self._time_range])
        super().__init__(do, **kwargs)

    def when(self, snapshot: Snapshot) -> bool:
        return self._native.when_ts(_ts(snapshot))

    def is_out_date(self, t) -> bool:
        return self._native.is_out_date_ts(_ts(t))


def _check_time_delta(delta: timedelta):
    if delta.total_seconds() % 60 != 0:
        raise DemeterError("min time span is 1 minute")


class PeriodTrigger(Trigger):
    """
    Trigger action periodically

    Extra args can be passed through kwargs. e.g. tg = Trigger(lambda r:r, extra_arg1=0, extra_arg2="1")

    :param time_delta: Period
    :type time_delta: timedelta
    :param do: which action to take.
    :type do: Callable[[RowData], Any]
    :param trigger_immediately: whither to trigger action when back test just started
    :type trigger_immediately: bool
    :param pending: pending time to start the trigger, can be used to trigger at specific time of a day.
    :type pending: timedelta
    """

    def __init__(self, time_delta: timedelta, do, trigger_immediately=False, pending=timedelta(minutes=0), **kwargs):
        self._delta = time_delta
        self._trigger_immediately = trigger_immediately
        self._pending = pending
        _check_time_delta(time_delta)
        self._native = _rs.NativeTrigger.period(
            int(time_delta.total_seconds()), bool(trigger_immediately), int(pending.total_seconds())
        )
        super().__init__(do, **kwargs)

    @property
    def _next_match(self):
        n = self._native.next_match
        return None if n is None else datetime.fromtimestamp(n, timezone.utc).replace(tzinfo=None)

    def reset(self):
        self._native.reset()

    def when(self, snapshot: Snapshot) -> bool:
        return self._native.when_ts(_ts(snapshot))


class PeriodsTrigger(Trigger):
    """
    trigger action periodically, but you can set multiple period.

    Extra args can be passed through kwargs. e.g. tg = Trigger(lambda r:r, extra_arg1=0, extra_arg2="1")

    :param time_delta: Periods,
    :type time_delta: List[timedelta]
    :param do: which action to take.
    :type do: Callable[[RowData], Any]
    :param trigger_immediately: whither to trigger action when back test just started
    :type trigger_immediately: bool
    :param pending: pending time to start the trigger, can be used to trigger at specific time of a day.
    :type pending: timedelta
    """

    def __init__(
        self, time_delta: List[timedelta], do, trigger_immediately=False, pending=timedelta(minutes=0), **kwargs
    ):
        self._deltas = time_delta
        self._trigger_immediately = trigger_immediately
        self._pending = pending

        for td in time_delta:
            _check_time_delta(td)
        self._native = _rs.NativeTrigger.periods(
            [int(d.total_seconds()) for d in time_delta], bool(trigger_immediately), int(pending.total_seconds())
        )
        super().__init__(do, **kwargs)

    def reset(self):
        self._native.reset()

    def when(self, snapshot: Snapshot) -> bool:
        return self._native.when_ts(_ts(snapshot))


class PriceTrigger(Trigger):
    """
    Trigger when price meet a customized condition

    Extra args can be passed through kwargs. e.g. tg = Trigger(lambda r:r, extra_arg1=0, extra_arg2="1")

    :param condition: customized condition, arg is price of tokens
    :type condition: Callable[[pd.Series], bool]
    :param do: which action to take.
    :type do: Callable[[RowData], Any]
    """

    def __init__(self, condition: Callable[[pd.Series], bool], do, **kwargs):
        self._condition = condition
        super().__init__(do, **kwargs)

    def when(self, snapshot: Snapshot) -> bool:
        return self._condition(snapshot.prices)


class CustomizedTrigger(Trigger):
    """
    Trigger on customized condition

    Extra args can be passed through kwargs. e.g. tg = Trigger(lambda r:r, extra_arg1=0, extra_arg2="1")

    :param condition: customized condition
    :type condition: Callable[[RowData], bool]
    :param do: which action to take.
    :type do: Callable[[RowData], Any]
    """

    def __init__(self, condition: Callable[[Snapshot], bool], do, **kwargs):
        self._condition = condition
        super().__init__(do, **kwargs)

    def when(self, snapshot: Snapshot) -> bool:
        return self._condition(snapshot)


# Triggers whose exact type is in this tuple are evaluated natively by the engine (no python call
# per iteration). Subclasses, e.g. a user trigger overriding `when`, always go through python.
NATIVE_TRIGGER_TYPES = (AtTimeTrigger, AtTimesTrigger, TimeRangeTrigger, TimeRangesTrigger, PeriodTrigger, PeriodsTrigger)
