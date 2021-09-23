# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from datetime import date, datetime, time

import logging
_logger = logging.getLogger(__name__)


class WorkingHours(models.Model):
    _name = 'working.hours'
    _description = "Working Hours"

    @api.multi
    def name_get(self):
        result = []
        for record in self:
            name = str(record.year) + ' - ' + record.start_hour + ':' + record.start_minute + ' to ' + \
                   record.end_hour + ':' + record.end_minute + ' UTC'
            result.append((record.id, name))
        return result

    @api.model
    def _get_hour(self):
        res = []
        for i in range(0, 24):
            if i < 10:
                i = str('0') + str(i)
            i = str(i)
            res.append((i, i))
        return res

    year = fields.Integer("Year", default=datetime.now().year)
    active = fields.Boolean("Active", default=True)
    start_hour = fields.Selection('_get_hour', 'Start Time', default='00', required=True)
    end_hour = fields.Selection('_get_hour', 'End Time', default='00', required=True)
    start_minute = fields.Selection([('00', '00'), ('30', '30')], 'Start Minute', default='00', required=True)
    end_minute = fields.Selection([('00', '00'), ('30', '30')], 'End Minute', default='00', required=True)
    deadline_revise_percentage = fields.Integer("Percentage", required=True, default=10,
                                                help="This percentage will be used in Revise Deadline calculation.")
    non_working_days_line = fields.One2many('non.working.days.line', 'working_hours_id', "Non-Working Days")

    @api.multi
    @api.constrains('active')
    def _check_active(self):
        """ To keep only one active record """
        for record in self:
            count = self.search_count([('active', '=', True), ('id', '!=', record.id)])
            if count:
                raise ValidationError(_('Multiple active records. Please Inactive other!'))

    @api.multi
    @api.constrains('start_hour', 'end_hour')
    def _check_hours(self):
        """ To keep only one active record """
        for record in self:
            if record.start_hour or record.end_hour:
                if int(record.start_hour) == int(record.end_hour):
                    raise ValidationError(_('Please enter different Start Hours and End Hours!'))
                if int(record.start_hour) > int(record.end_hour):
                    raise ValidationError(_('Start hours can not be greater than end hours for the day.'))

    @api.multi
    def get_working_hour(self):
        """ To fetch working hour values """
        working_hrs_id = self.search([('active', '=', True)])
        if working_hrs_id:
            return {
                'biz_open_time': time(int(working_hrs_id.start_hour), int(working_hrs_id.start_minute), 0),
                'biz_close_time': time(int(working_hrs_id.end_hour), int(working_hrs_id.end_minute), 0),
                'holiday_list': {line.occ_date: line.name for line in working_hrs_id.non_working_days_line},
                'deadline_revise_percentage': working_hrs_id.deadline_revise_percentage,
            }
        raise ValidationError("Working Hour configuration is missing!")


class NonWorkingDaysLine(models.Model):
    _name = 'non.working.days.line'
    _description = 'Non Working Days Line Items'

    name = fields.Char("Occasion")
    occ_date = fields.Date("Date")
    hour_day = fields.Selection([('sun', 'Sunday'),
                                 ('mon', 'Monday'),
                                 ('tue', 'Tuesday'),
                                 ('wed', 'Wednesday'),
                                 ('thu', 'Thursday'),
                                 ('fri', 'Friday'),
                                 ('sat', 'Saturday')], "Days")
    working_hours_id = fields.Many2one("working.hours", "Working hours ID")

    @api.multi
    @api.constrains('occ_date')
    def _check_occ_date(self):
        """ Restrict to add duplicate dates"""
        for record in self:
            count = self.search_count(
                [('occ_date', '=', record.occ_date), ('working_hours_id', '=', record.working_hours_id.id)])
            if count > 1:
                raise ValidationError(_('%s date already exists!' % record.occ_date))
