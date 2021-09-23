# -*- coding: utf-8 -*-
import math
from datetime import date, datetime, time, timedelta
from business_duration import businessDuration


def get_deadline_revise_hrs(start_datetime, deadline, biz_open_time, biz_close_time, holiday_list, percentage, initial):
    """
        To calculate Deadline Revise Date (hours) = [Translation Level Deadline – start_datetime] * percentage
        :param start_datetime: first time it will be quotation sent datetime and next iteration onwards it will be
                                previous revise datetime
        :param deadline: deadline from service level line
        :param biz_open_time: Business open hour
        :param biz_close_time: Business close time
        :param holiday_list: dict of non-working days from master
        :param percentage: percentage
        :param initial: if true then will consider 24hours else working hours
        :return: deadline_revise_hrs: deadline revise hours
    """
    deadline_revise_hrs, total_working_hrs = 0.0, 0.0
    if initial:
        total_working_hrs = businessDuration(startdate=start_datetime, enddate=deadline, starttime=time(0, 0, 0),
                                             endtime=time(23, 59, 59), holidaylist=[], unit='hour', weekendlist=[])
    else:
        total_working_hrs = businessDuration(startdate=start_datetime, enddate=deadline, starttime=biz_open_time,
                                             endtime=biz_close_time, holidaylist=holiday_list, unit='hour',
                                             weekendlist=[])

    if math.isnan(total_working_hrs):
        deadline_revise_hrs = 0.0
    else:
        deadline_revise_hrs = (total_working_hrs * percentage) / 100
    return deadline_revise_hrs


def validate_revise_date(revised_date, holiday_list):
    """
        To check revise date in non-working day or not
        :param revised_date: revised date after adding hours
        :param holiday_list: dict of non-working days from master
        :return: if non-working day then return true else false
    """
    if revised_date in holiday_list:
        return True
    return False


def check_non_working_day(revised_date, holiday_list):
    """
        To check revised date is non-working day or not
        if non-working day then push to next day
        :param revised_date: calculated revise date
        :param holiday_list: dict of non-working days from master
        :return: final_revised_date:
    """
    final_revised_date = revised_date
    while final_revised_date:
        result = validate_revise_date(final_revised_date, holiday_list)
        if result:
            final_revised_date = final_revised_date + timedelta(days=1)
        else:
            break
    return final_revised_date


def adjust_revise_deadline_time(biz_open_time, biz_close_time, rounded_revised_deadline, holiday_list):
    """
        To push revise deadline if revise deadline time is non-working hours
        :param biz_open_time: Business open hour
        :param biz_close_time: Business close time
        :param rounded_revised_deadline: revise deadline datetime
        :param holiday_list: dict of non-working days from master
        :return: final_deadline_datetime: final revise deadline datetime
    """
    biz_open_time_float = biz_open_time.hour + biz_open_time.minute / 60.0
    biz_close_time_float = biz_close_time.hour + biz_close_time.minute / 60.0
    working_hrs = biz_close_time_float - biz_open_time_float
    if working_hrs < 0.0:
        working_hrs = biz_open_time_float - biz_close_time_float

    deadline_time = rounded_revised_deadline.time()
    deadline_time_float = deadline_time.hour+deadline_time.minute/60.0
    diff_deadline_time_float = deadline_time_float - biz_close_time_float
    if diff_deadline_time_float < 0.0:
        diff_deadline_time_float = biz_close_time_float - deadline_time_float

    final_date = rounded_revised_deadline.date()

    while diff_deadline_time_float > working_hrs:
        diff_deadline_time_float = diff_deadline_time_float - working_hrs
        final_date = final_date + timedelta(days=1)
        final_date = check_non_working_day(final_date, holiday_list)

    final_time = deadline_time

    if diff_deadline_time_float > 0.0:
        final_date = final_date + timedelta(days=1)
        temp_time = biz_open_time_float + diff_deadline_time_float
        final_time = (datetime.fromordinal(final_date.toordinal()) + timedelta(seconds=temp_time * 3600)).time()

        # # Between after working hour to 00
        # if biz_close_time < final_time < time(18, 30, 0):
        #     final_date = final_date + timedelta(days=1)
        # elif time(18, 30, 0) <= final_time < time(23, 59, 59):
        #     final_date = final_date + timedelta(days=1)

    final_deadline_datetime = datetime.combine(final_date, final_time)
    return final_deadline_datetime


def get_revised_time(rounded_revised_deadline, biz_open_time, biz_close_time, holiday_list):
    """
        To check time is between working hours or not
        if in between working hours then return revise time else working hour's start time
        :param rounded_revised_deadline: revise date
        :param biz_open_time: Business open hour
        :param biz_close_time: Business close time
        :param holiday_list: dict of non-working days from master
        :return: final time for revise date
    """
    deadline_time = rounded_revised_deadline.time()
    # Between working hours
    if biz_open_time <= deadline_time <= biz_close_time:
        return rounded_revised_deadline
    else:
        final_deadline_datetime = adjust_revise_deadline_time(biz_open_time, biz_close_time, rounded_revised_deadline,
                                                              holiday_list)
        return final_deadline_datetime

    # # Between after working hour to 00
    # elif biz_close_time < deadline_time < time(18, 30, 0):
    #     return biz_open_time, True
    # elif time(18, 30, 0) <= deadline_time < time(23, 59, 59):
    #     return biz_open_time, True
    # elif time(0, 0, 0) <= deadline_time < biz_open_time:
    #     return biz_open_time, False


def deadline_revise_day(deadline_revise_hrs, previous_deadline_revise_day, holiday_list, biz_open_time, biz_close_time):
    """
        To get Revised Deadline day
        :param deadline_revise_hrs: Deadline Revise hours
        :param previous_deadline_revise_day: previous deadline revise datetime
        :param holiday_list: dict of non-working days from master
        :param biz_open_time: Business open hour
        :param biz_close_time: Business close time
        :return: deadline_revise_day: final revised deadline
    """
    revised_deadline_time = False
    if deadline_revise_hrs > 0.0:
        revised_deadline_time = timedelta(hours=deadline_revise_hrs) + previous_deadline_revise_day
    else:
        return False
    deadline_revise_day = round_time(revised_deadline_time, round_to=60 * 30)

    temp_revise_date = check_non_working_day(deadline_revise_day.date(), holiday_list)
    temp_revise_datetime = datetime.combine(temp_revise_date, deadline_revise_day.time())

    final_revise_datetime = get_revised_time(temp_revise_datetime, biz_open_time, biz_close_time, holiday_list)

    final_revise_date = check_non_working_day(final_revise_datetime.date(), holiday_list)

    # To get final revise deadline day
    final_deadline_revise_day = datetime.combine(final_revise_date, final_revise_datetime.time())
    return final_deadline_revise_day


def get_revised_deadline(deadline_revise_hrs, deadline, biz_open_time, biz_close_time, holiday_list):
    """
        To get Revised Deadline
        :param deadline_revise_hrs: Deadline Revise hours
        :param deadline: deadline from service level line
        :param biz_open_time: Business open hour
        :param biz_close_time: Business close time
        :param holiday_list: dict of non-working days from master
        :return: final_revised_deadline: final reivsed deadline
    """
    revised_deadline = False
    if deadline_revise_hrs > 0.0:
        revised_deadline = timedelta(hours=deadline_revise_hrs) + deadline
    else:
        return False

    rounded_revised_deadline = round_time(revised_deadline, round_to=60 * 30)

    temp_revise_date = check_non_working_day(rounded_revised_deadline.date(), holiday_list)
    temp_revised_deadline = datetime.combine(temp_revise_date, rounded_revised_deadline.time())

    final_deadline_datetime = get_revised_time(temp_revised_deadline, biz_open_time, biz_close_time, holiday_list)

    final_revise_date = check_non_working_day(final_deadline_datetime.date(), holiday_list)

    # To get final revise deadline
    final_revised_deadline = datetime.combine(final_revise_date, final_deadline_datetime.time())
    return final_revised_deadline


def round_time(dt=None, round_to=60):
    """ Round datetime to any time interval in seconds """
    if dt == None:
        dt = datetime.now()
    seconds = (dt - dt.min).seconds
    rounding = (seconds+round_to/2) // round_to * round_to
    return dt + timedelta(0, rounding-seconds, -dt.microsecond)
