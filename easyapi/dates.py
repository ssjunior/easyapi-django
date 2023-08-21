from datetime import timedelta

import calendar
from dateutil import rrule
from dateutil.relativedelta import relativedelta
from django.utils import timezone
import pytz


def date_to_string(date):
    if not date:
        return date
    return date.strftime("%Y-%m-%d %H:%M:%S")


def get_weekday(day):
    return calendar.day_name[day]


class Dates(object):
    # last 12 months, this4, last4, last4quarters
    def __init__(self, tz='UTC', remove_tz=True):
        if remove_tz:
            self.now = timezone.now().astimezone(tz=pytz.timezone(tz)).replace(tzinfo=None)
        else:
            self.now = timezone.now().astimezone(tz=pytz.timezone(tz))

        self.start = self.now.replace(
            hour=0, minute=0, second=0, microsecond=0)
        self.end = self.now.replace(
            hour=23, minute=59, second=59, microsecond=99)

        self.delta_days = 0
        self.delta_months = 0
        self.delta_years = 0

    def base(self, day_start=0, day_end=0, month_start=0, month_end=0):
        day_start = day_start or self.start.day
        month_start = month_start or self.start.month

        day_end = day_end or self.last_monthday(self.end.year, self.end.month)
        month_end = month_end or self.end.month

        start = self.start.replace(day=day_start, month=month_start) - relativedelta(
            days=self.delta_days, months=self.delta_months, years=self.delta_years
        )
        end = self.end.replace(day=day_end, month=month_end) - relativedelta(
            days=self.delta_days, months=self.delta_months, years=self.delta_years
        )

        return start, end

    def day_delta(self, delta):
        return self.today(-int(delta))

    def month_delta(self, delta=0):
        return self.this_month(-int(delta))

    def year_delta(self, delta):
        return self.this_year(-int(delta))

    def last_monthday(self, year=0, month=0):
        return calendar.monthrange(year, month)[-1]

    def this_month(self, delta=0):
        self.delta_months = delta
        return self.base(day_start=1)

    def last_month(self, delta=0):
        start = self.this_month(1)[0]
        end = start + relativedelta(months=1)
        return start, end

    def next_month(self, delta=0):
        start = self.this_month(-1)[0]
        end = start + relativedelta(months=1)
        return start, end

    def this_week(self, delta=0):
        start = self.today(self.start.weekday() + (delta * 7))[0]
        end = start + relativedelta(days=7, seconds=-1)
        return start, end

    def last_week(self, delta=0):
        return self.this_week(1)

    def next_week(self, delta=0):
        return self.this_week(-1)

    def today(self, delta=0):
        self.delta_days = delta
        start = self.base()[0]
        end = start + relativedelta(days=1, seconds=-1)
        return start, end

    def yesterday(self):
        return self.today(1)

    def tomorrow(self):
        return self.today(-1)

    def last_delta_days(self, delta=0):
        start = self.today(delta)[0]
        end = start + relativedelta(days=delta + 1, seconds=-1)
        return start, end

    def next_delta_days(self, delta=0):
        start = self.today(-delta)[0]
        end = start + relativedelta(days=delta + 1, seconds=-1)
        return start, end

    def last_7_days(self):
        return self.last_delta_days(7)

    def last_30_days(self):
        return self.last_delta_days(30)

    def last_60_days(self):
        return self.last_delta_days(60)

    def last_90_days(self):
        return self.last_delta_days(90)

    def next_7_days(self):
        return self.next_delta_days(7)

    def next_30_days(self):
        return self.next_delta_days(30)

    def next_60_days(self):
        return self.next_delta_days(60)

    def next_90_days(self):
        return self.next_delta_days(90)

    def this_year(self, delta=0):
        self.delta_years = delta
        start = self.base(day_start=1, month_start=1)[0]
        end = start + relativedelta(years=1, seconds=-1)
        return start, end

    def last_year(self):
        return self.this_year(1)

    def next_year(self):
        return self.this_year(-1)

    def get_min_date(self, period, value):
        if period == 'days':
            self.start = self.start - relativedelta(days=value)
        elif period == 'months':
            self.start = self.start - relativedelta(months=value)
        elif period == 'years':
            self.start = self.start - relativedelta(years=value)

    def get_max_date(self, period, value):
        if period == 'days':
            self.end = self.end - relativedelta(days=value)
        elif period == 'months':
            self.end = self.end - relativedelta(months=value)
        elif period == 'years':
            self.end = self.end - relativedelta(years=value)

    def age(self, values, operator):
        self.base()
        if operator == 'range':
            min_value = values.get('min_value')
            max_value = values.get('max_value')
            self.get_min_date(max_value.get('type'),
                              int(max_value.get('value')))
            self.get_max_date(min_value.get('type'),
                              int(min_value.get('value')))

        elif operator == 'gte':
            self.get_min_date(values.get('type'), int(values.get('value')))

        elif operator == 'lte':
            self.get_max_date(values.get('type'), int(values.get('value')))

        elif operator == 'exact':
            self.get_min_date(values.get('type'), int(values.get('value')) + 1)
            self.get_max_date(values.get('type'), int(values.get('value')))
        return self.start, self.end


def range_months(date_start, date_end):
    return list(
        rrule.rrule(
            rrule.MONTHLY,
            bymonthday=(date_start.day, -1),
            bysetpos=1,
            dtstart=date_start,
            until=date_end
        )
    )


def range_days(date_start, date_end):
    return list(
        rrule.rrule(
            rrule.DAILY,
            dtstart=date_start,
            until=date_end
        )
    )


def range_hour(date_start, date_end):
    return list(
        rrule.rrule(
            rrule.HOURLY,
            dtstart=date_start,
            until=date_end
        )
    )


def format_duration(duration):
    if duration:

        if type(duration) is not timedelta:
            duration = timedelta(seconds=duration)

        minutes = (duration.seconds % 3600) / 60
        hours = (duration.seconds % 86400) / 3600

        f_time = ''
        if duration.days:
            f_time = '{}d'.format(duration.days)

        if hours:
            f_hours = '{}h'.format(hours)
            if f_time:
                f_time += ', ' + f_hours
            else:
                f_time += f_hours

        if minutes:
            if f_time:
                if hours:
                    f_time += ':{}m'.format(minutes).zfill(2)
                else:
                    f_time += ',  {}m'.format(minutes)
            else:
                f_time = '{}m'.format(minutes)

        return f_time

    return '0m'
