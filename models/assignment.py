# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from datetime import date, datetime, timedelta
import pytz
import os.path
from odoo.tools import float_round, float_repr
from odoo.http import request
from odoo.exceptions import ValidationError, UserError
import logging
_logger = logging.getLogger(__name__)


class Assignment(models.Model):
    _name = 'assignment'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = 'Client Assignments'

    def _check_pending_since(self):
        """
            Calculate pending time form create date
            :return: pending_since
        """
        for rec in self:
            diff = False
            days, hour, minute = 0, 0, 0
            if rec.create_date:
                now = datetime.now()
                diff = now - rec.create_date
            if diff:
                days, hour, minute = diff.days, diff.seconds // 3600, (diff.seconds // 60) % 60
            rec.pending_since = '%s D %s Hr %s Mins' % (str(days), str(hour), str(minute))

    def advance_payment_default(self):
        if self.partner_id.send_inv_monthly is True:
            return '0'
        else:
            return '100'

    name = fields.Char('ASN Code', track_visibility='onchange')
    partner_id = fields.Many2one('res.partner', string="Client")
    quotation_id = fields.Many2one('sale.order', string="Quotation Ref.")
    parent_asn_id = fields.Many2one('sale.order', string="Parent ASN Ref.")
    service_level_id = fields.Many2one('service.level',
                        string='Translation Level',track_visibility='onchange')
    source_lang_id = fields.Many2one(
        'res.lang', string='Source language', track_visibility='onchange')
    target_lang_id = fields.Many2one(
        'res.lang', string='Target language', track_visibility='onchange')
    pending_since = fields.Char('Pending Since',
                                   compute="_check_pending_since")
    # hour_day = fields.Selection([('hour', 'Hours'),
    #                              ('day', 'Days')],
    #                             "Days", compute="_check_pending_since")
    deadline = fields.Datetime("Deadline for ASN", track_visibility='onchange')
    character_count = fields.Integer("Total Unit Count")
    currency_id = fields.Many2one("res.currency", string="Currency")
    mark_as_special = fields.Boolean("Mark as Special")
    mark_as_trial = fields.Boolean("Mark as Trial")
    trial_flag = fields.Boolean("Mark as Trial")
    # All Fee Calculation
    translation_fee = fields.Float("Translation Fee")
    total_addons_fee = fields.Float("Total Addons Fee")
    project_management_cost = fields.Float("Project Management Cost")
    gross_fee = fields.Float("Gross Fee")
    discount = fields.Float("Discount")
    premium = fields.Float("Premium")
    subtotal_without_tax = fields.Float("Sub Total Without Tax")
    tax = fields.Float("Tax")
    total_fees = fields.Float("Total Fees")
    asn_addons_fee_line = fields.One2many('asn.addons.fee.line',
                                      'asn_id','Addons Fee Line')

    # All One2Many Lines
    assignment_instruction_line = fields.One2many(
        "assignment.instruction.line", 'assignment_ins_id',
        'Assignment Original File Line')
    assignment_original_file_line = fields.One2many(
        'ir.attachment', 'assignment_id', 'Original Assignment File Lines',
        domain=[('file_type', '=', 'client')])
    asn_reference_line = fields.One2many(
        'ir.attachment', 'assignment_id', 'ASN Instruction Lines',
        domain=[('file_type', '=', 'refrence')])

    # Pm related Field Details
    state = fields.Selection([('new', 'New'),
                              ('on-hold', 'On-Hold'),
                              ('transfer', 'Transfer'),
                              ('revised', 'Revised Assignments'),
                              ('pending', 'Pending For Delivery'),
                              ('deliver', 'Delivered'),
                              ('cancel', 'Reject')],
                             'PM Status', default='new',
                             track_visibility='onchange')
    membership_id = fields.Many2one("membership.master", string="MEMID")
    note = fields.Text("Reason", track_visibility='onchange')
    reject_date = fields.Datetime("Reject Date", track_visibility='onchange')
    addon_service_ids = fields.Many2many('product.product', 'product_addons_rel', 'product_id', 'addons_id', string='AddOn Service')
    # Technical field: to get previous state of assignment
    previous_state = fields.Selection([('new', 'New'),
                                       ('on-hold', 'On-Hold'),
                                       ('transfer', 'Transfer'),
                                       ('revised', 'Revised Assignments'),
                                       ('pending', 'Pending For Delivery'),
                                       ('deliver', 'Delivered'),
                                       ('cancel', 'Reject')], 'Previous PM Status', default='new')

    initial_received_on_pm = fields.Datetime(string="Initial Received On")
    received_on_pm = fields.Datetime(string="Received On", track_visibility='onchange')
    delivered_on = fields.Datetime(string="Delivered On", track_visibility='onchange')
    revised_on = fields.Datetime(string="Revised On", track_visibility='onchange')
    deadline_breach = fields.Selection([('yes', 'Yes'),
                                        ('no', 'No')],
                                       'Deadline Breach', default='no')

    country = fields.Char("Country")
    ip_address = fields.Char("IP Address")
    browser = fields.Char("Browser")

    # Added for lastline
    ulatus_lastline = fields.Text(string="Ulatus lastline")
    priority = fields.Selection([('standard', 'Standard'),
                                 ('express', 'Express'),
                                 ('super_express', 'Super Express')], 'Priority', default='standard')
    product_id = fields.Many2one('product.product', string="Product")
    area_type = fields.Selection([('subject_area', 'Subject Area'),
                                  ('industrial_area', 'Industrial Area')], 'Area Type')
    subject_industrial_area_level1_id = fields.Many2one("subject.industrial.area.level1", "Level 1")
    subject_industrial_area_level2_id = fields.Many2one("subject.industrial.area.level2.line", "Level 2")
    subject_industrial_area_level3_id = fields.Many2one("subject.industrial.area.level3.line", "Level 3")
    level3_other_area_bool = fields.Boolean("Others Bool", default=False)
    level3_other_area = fields.Char("Others")
    client_query_types = fields.Char("Client Query Types", default=False)
    is_revision_asn = fields.Boolean("Is Revision ASN", default=False)
    reason_history_line = fields.One2many('reason.history.line', 'child_asn_id', 'Reason History Line')
    is_seen = fields.Boolean("Is Seen", default=False)
    advance_payment = fields.Selection(
        [('0', '0%'),
         ('1_99', '1-99%'),
         ('100', '100%')], 'Advance Payment Type', default=advance_payment_default)
    advance_payment_value = fields.Integer('Advance Payment %', default=100)
    advance_payment_amount = fields.Float("Advance Payment Amount")
    advance_pending_amount = fields.Float("Advance Pending Amount")

    # Use for Revision ASN Status
    revision_asn_state = fields.Selection([('on-hold', 'ASN On-Hold'),
                                           ('sale', 'ASN confirmed'),
                                           ('revised', 'ASN Revised'),
                                           ('asn_work_in_progress', 'ASN Work-in-progress'),
                                           ('done', 'ASN Completed'),
                                           ('cancel', 'Rejected')],
                                          'Revision ASN Status', default='asn_work_in_progress',
                                          compute='_compute_revision_asn_state',
                                          track_visibility='onchange', copy=True,
                                          help='Revision ASN Status on CS Side.')

    parent_asn_ref_id = fields.Many2one('sale.order', string="Original ASN Ref.")
    # use for grant access rights to user
    user_id = fields.Many2one('res.users', string='User', track_visibility='onchange')
    asn_previous_state = fields.Char('Status for handling progress bar')
    is_legacy_data = fields.Boolean("Is legacy Data", default=False)
    external_deadline = fields.Datetime(string="Deadline for ASN", compute='_compute_external_deadline')
    language_pair = fields.Char(string='Language Pair', compute='_compute_language_pair')
    unit_id = fields.Many2one('service.unit', string='Unit', compute='_get_unit_name')
    confirmation_date = fields.Datetime('Date Of Confirmation', related='quotation_id.quote_confirmation_datetime')

    # Invoice/Payment related fields
    send_inv_monthly = fields.Boolean('Monthly Invoicing')
    po_required = fields.Boolean(readonly=True)
    po_number = fields.Char('Client PO#')
    invoice_status = fields.Selection(
        [('pending', 'Pending for Data'),
         ('to_invoice', 'To Invoice'),
         ('invoiced', 'Invoiced')], 'Invoice Status')
    invoice_type = fields.Selection(
        [('ind', 'Individual'),
         ('org', 'Org Level')], 'Invoicing Level')

    @api.depends('state')
    def _compute_revision_asn_state(self):
        """
             To make the Revision ASN status same as Parenst ASN on CS end
        """
        for rec in self:
            if rec.is_revision_asn:
                if rec.state == 'on-hold':
                    rec.revision_asn_state = 'on-hold'
                elif rec.state in ['new', 'transfer', 'pending']:
                    rec.revision_asn_state = 'asn_work_in_progress'
                elif rec.state == 'deliver':
                    rec.revision_asn_state = 'done'
                elif rec.state == 'cancel':
                    rec.revision_asn_state = 'cancel'
                elif rec.state == 'revised':
                    rec.revision_asn_state = 'revised'

    @api.onchange('deadline')
    def onchange_deadline(self):
        if self.deadline:
            line_id = self.parent_asn_id
            current_date = datetime.strptime(
            line_id.dashboard_convert_to_user_timezone(
                    datetime.now()).strftime("%Y-%m-%d %H:00:00"),
                                            '%Y-%m-%d %H:00:00')
            deadline = datetime.strptime(
                        line_id.dashboard_convert_to_user_timezone(
                            self.deadline).strftime("%Y-%m-%d %H:00:00"), '%Y-%m-%d %H:00:00')
            current_date = current_date + timedelta(hours=1, minutes=00, seconds=00)
            if deadline < current_date:
                tz = 'GMT'
                if self.env.context['tz']:
                    tz = self.env.context['tz']
                today_utc = fields.Datetime.to_string(pytz.timezone(tz).localize(
                            fields.Datetime.from_string(current_date),
                            is_dst=None).astimezone(pytz.utc))
                self.deadline = today_utc

    @api.depends('deadline')
    def _compute_external_deadline(self):
        """
             Redused deadline by 1 Hour for PM
        """
        for rec in self:
            if rec.deadline:
                rec.external_deadline = rec.deadline - timedelta(hours=1)

    def _compute_language_pair(self):
        """
             Concatenated Source and Target Language for PM
        """
        for rec in self:
            source_lang = '' if rec.source_lang_id.name == False else rec.source_lang_id.name
            target_lang = '' if rec.target_lang_id.name == False else rec.target_lang_id.name
            rec.language_pair = source_lang + ' ' + 'to' + ' ' + target_lang

    def _get_unit_name(self):
        """
             Get unit name for PM
        """
        for rec in self:
            rec.unit_id = rec.quotation_id.order_line.filtered(lambda f: f.target_lang_id == rec.target_lang_id).unit_id.id


    @api.multi
    def reload_btn(self):
        return {
            'type': 'ir.actions.close_wizard_refresh_view',
            # 'tag': 'reload_btn',
        }

    # Funtion to create lastline for ulatus
    @api.multi
    def generate_ulatus_lastline(self):
        lastline = []
        source_lang = '' if self.source_lang_id.name == False else self.source_lang_id.name
        target_lang = '' if self.target_lang_id.name == False else self.target_lang_id.name
        service = source_lang + ' ' + 'to' + ' ' + target_lang
        lastline.append(service)
        sr_no = ''
        lastline.append(sr_no)
        asn_no = '%s_cancelled' % self.name if self.state == 'cancel' else self.name
        lastline.append(asn_no)
        # received_date = self._get_client_deadline('date')
        # date and time of quotation confirmation
        received_date = self.get_quotation_confirmation()
        lastline.append(received_date)
        # received_time = self._get_client_deadline('time')
        # date and time of last line sent to PM team
        received_time = self.get_initial_received_on_pm()
        lastline.append(received_time)
        external_deadline = self._get_client_deadline('diff')
        lastline.append(external_deadline)
        translation_level = '' if self.service_level_id.pm_name == False else self.service_level_id.pm_name
        lastline.append(translation_level)

        count = 0
        if self.asn_reference_line:
            for rec in self.asn_reference_line:
                if rec.category_type_id.name == 'Glossary':
                    count = count + 1
        technical_checklist = 'Yes' if count > 0 else 'No'
        lastline.append(technical_checklist)
        translation_budget = ''
        lastline.append(translation_budget)
        tc_budget = ''
        lastline.append(tc_budget)
        nc_budget = ''
        lastline.append(nc_budget)
        priority = '' if self.priority == False else dict(self._fields['priority'].selection).get(self.priority)
        lastline.append(priority)
        word_count = str(self.character_count)
        lastline.append(word_count)
        sa_level_1 = '' if self.subject_industrial_area_level1_id.name == False else self.subject_industrial_area_level1_id.name
        lastline.append(sa_level_1)
        sa_level_2 = '' if self.subject_industrial_area_level2_id.name == False else self.subject_industrial_area_level2_id.name
        lastline.append(sa_level_2)
        sa_level_3 = self.level3_other_area if self.level3_other_area_bool == True else \
            '' if self.subject_industrial_area_level3_id.name == False else self.subject_industrial_area_level3_id.name
        lastline.append(sa_level_3)
        industry_1 = ''
        lastline.append(industry_1)
        industry_2 = ''
        lastline.append(industry_2)
        lastline.append(source_lang)
        lastline.append(target_lang)
        addons_name = []
        unit_count_of_addons = []
        if self.asn_addons_fee_line:
            for line in self.asn_addons_fee_line:
                addons_name.append(line.product_id.name)
                unit_count_of_addons.append(line.unit_id.name + '/' + str(line.no_of_unit))
        lastline.append(','.join(addons_name))
        # lastline.append(','.join(unit_count_of_addons))
        journal_name = ''
        lastline.append(journal_name)
        purpose_1 = '' if self.product_id.name == False else self.product_id.name
        lastline.append(purpose_1)
        purpose_2 = ''
        lastline.append(purpose_2)
        english = ''
        lastline.append(english)
        no_of_files = str(len(self.assignment_original_file_line))
        lastline.append(no_of_files)
        ref_file_count = 0
        if self.asn_reference_line:
            for rec in self.asn_reference_line:
                if rec.category_type_id.name != 'Analysis':
                    ref_file_count += 1
            # for rec in self.asn_reference_line:
            #     if rec.category_type_id.name == 'Analysis':
            #         ref_file_count = ref_file_count - 1
            #     elif rec.category_type_id.id == False:
            #         ref_file_count = ref_file_count + 1
            #     else:
            #         ref_file_count = ref_file_count + 1
        no_of_ref_files = str(ref_file_count)
        lastline.append(no_of_ref_files)
        file_size = ''
        lastline.append(file_size)
        file_name = self._get_file_names('name')
        lastline.append(file_name)
        input_file_format = self._get_file_names('format')
        lastline.append(input_file_format)
        # client_translator_preferance = '0'
        client_translator_preferance = ''
        lastline.append(client_translator_preferance)
        additional_instructions = self._get_cs_instructions()
        lastline.append(additional_instructions)
        translation_style_1 = ''
        lastline.append(translation_style_1)
        translation_style_2 = ''
        lastline.append(translation_style_2)
        prospective_repeat_client = ''
        lastline.append(prospective_repeat_client)
        # acc_non_acc = '' if self.area_type == False else dict(self._fields['area_type'].selection).get(self.area_type)
        lastline.append('Non-Academic')
        voxtab_deadline = ''
        lastline.append(voxtab_deadline)
        cs_alert_imp_asn = ''
        lastline.append(cs_alert_imp_asn)
        typeof_doc = ''
        lastline.append(typeof_doc)
        ftp = ''
        lastline.append(ftp)
        translation_memory_name = self._get_file_names('tm_name')
        lastline.append(translation_memory_name)
        if self.mark_as_trial is True:
            special_trial_asn = 'TRIAL'
        elif self.mark_as_special is True:
            special_trial_asn = 'YES'
        else:
            special_trial_asn = ''
        lastline.append(special_trial_asn)
        client_name = '' if self.partner_id.name is False else self.partner_id.name
        lastline.append(client_name)
        client_primary_email = '' if self.partner_id.email is False else self.partner_id.email
        lastline.append(client_primary_email)
        co_responsable_delivery = ''
        lastline.append(co_responsable_delivery)
        company_name = '' if self.partner_id.parent_id.name is False else self.partner_id.parent_id.name
        lastline.append(company_name)
        # client_fee = '' if self.total_fees == False else str(self.total_fees)
        client_fee_without_tax = float_repr((self.subtotal_without_tax / 2), 2) if self.subtotal_without_tax > 0 else '0'
        lastline.append(client_fee_without_tax)
        currency = '' if self.currency_id.name is False else self.currency_id.name
        lastline.append(currency)
        invoice_date = ''
        lastline.append(invoice_date)
        asn_from = 'Global'
        lastline.append(asn_from)
        try:
            lastline = '|'.join(lastline)
        except Exception as e:
            lastline = ''
            _logger.error('Ulatus last line generation error: %s', e)
        return lastline

    # def _get_client_deadline(self, type):
    #     if type == 'date':
    #         received_date = datetime.strftime(self.create_date, "%d-%b")
    #         return received_date
    #     elif type == 'time':
    #         received_time = datetime.strftime(self.create_date, "%d-%b-%y %I:%M %p")
    #         return received_time
    #     elif type == 'diff':
    #         external_deadline = self.deadline - timedelta(hours=1)
    #         external_deadline = datetime.strftime(external_deadline, "%d/%m/%Y %I:%M")
    #         return external_deadline

    def _get_client_deadline(self, type):
        if type == 'date':
            received_date = datetime.strftime(self.create_date, "%d-%b-%y")
            return received_date
        elif type == 'time':
            ist_deadline = self.convert_gmt_to_ist_tz(self.create_date)
            received_time = datetime.strftime(ist_deadline, "%d-%b-%y %I:%M %p")
            return received_time
        elif type == 'diff':
            external_deadline = self.deadline - timedelta(hours=1)
            ist_deadline = self.convert_gmt_to_ist_tz(external_deadline)
            external_deadline = datetime.strftime(ist_deadline, "%d/%m/%Y %I:%M %p")
            return external_deadline

    def get_quotation_confirmation(self):
        """ To get quotation confirmation datetime in IST """
        quote_confirmation_datetime = ''
        if self.quotation_id.quote_confirmation_datetime:
            ist_quote_confirmation_datetime = self.convert_gmt_to_ist_tz(self.quotation_id.quote_confirmation_datetime)
            quote_confirmation_datetime = datetime.strftime(ist_quote_confirmation_datetime, "%d-%b-%y %I:%M %p")
        return quote_confirmation_datetime

    def get_initial_received_on_pm(self):
        """ To get date and time of last line sent to PM team(initial one) in IST """
        initial_received_on_pm = ''
        if self.initial_received_on_pm:
            ist_initial_received_on_pm = self.convert_gmt_to_ist_tz(self.initial_received_on_pm)
            initial_received_on_pm = datetime.strftime(ist_initial_received_on_pm, "%d-%b-%y %I:%M %p")
        return initial_received_on_pm

    def convert_gmt_to_ist_tz(self, value):
        """
            Convert datetime GMT to IST
            :param value: datetime to be convert
            :return: Converted IST datetime
        """
        res_datetime_str = fields.Datetime.from_string(value)
        datetime_loc = pytz.UTC.localize(res_datetime_str)
        ist_deadline = datetime_loc.astimezone(pytz.timezone('Asia/Kolkata'))
        return ist_deadline

    def _get_file_names(self,flag):
        if flag == 'name':
            files = [line.name for line in self.assignment_original_file_line]
            return ','.join(files)
        elif flag == 'format':
            files = [os.path.splitext(line.name)[1][1:] for line in self.assignment_original_file_line]
            return ','.join(files)
        elif flag == 'tm_name':
            files = []
            for line in self.asn_reference_line:
                if line.category_type_id.name == 'Translation Memory':
                    files.append(line.name)
            return ','.join(files)
        else:
            return ''

    def _get_cs_instructions(self):
        # comment_history = ''
        client_instructions = ''
        cs_instructions = ''
        client_instructions_line = self.env['assignment.instruction.line'].search(
            [('is_original_ins', '=', True), ('assignment_ins_id', '=', self.id), ('ins_for_pm', '=', True)])
        if client_instructions_line:
            client_instructions = ['- ' + line.name for line in client_instructions_line]
            client_instructions = ', '.join(client_instructions)

        cs_instructions_line = self.env['assignment.instruction.line'].search(
            [('is_original_ins', '=', False), ('assignment_ins_id', '=', self.id), ('ins_for_pm', '=', True)])
        if cs_instructions_line:
            cs_instructions = ['- ' + line.name for line in cs_instructions_line]
            cs_instructions = ', '.join(cs_instructions)

        # active_id = self._context.get('active_id')
        # active_model = self._context.get('active_model')
        #
        # if self._context.get('active_model') == 'sale.order':
        # #FOR SALE.ORDER MODEL ASN STATE= ASN_WORK_IN_PROGRESS
        #     if self.state == 'new':
        #         query = """
        #             SELECT comment
        #             FROM reason_history_line
        #             WHERE state='asn_work_in_progress'
        #             AND quote_id= %s
        #             ORDER BY logging_date desc LIMIT 1;""" % (active_id)
        #         self.env.cr.execute(query)
        #         values = self.env.cr.fetchall()
        #         comment_history = [x[0] for x in values]
        #         comment_history = ''.join(comment_history)
        #
        # # FOR SALE.ORDER MODEL ASN STATE= ON-HOLD
        #     elif self.state == 'on-hold':
        #         query = """
        #             SELECT comment
        #             FROM reason_history_line
        #             WHERE state='on-hold'
        #             AND quote_id= %s
        #             ORDER BY logging_date desc LIMIT 1;""" % (active_id)
        #         self.env.cr.execute(query)
        #         values = self.env.cr.fetchall()
        #         comment_history = [x[0] for x in values]
        #         comment_history = ''.join(comment_history)
        #
        # elif self._context.get('active_model') == 'assignment':
        # # FOR ASSIGNMENT MODEL ASN STATE= NEW
        #     if self.state == 'new':
        #         query = """
        #             SELECT comment
        #             FROM reason_history_line
        #             WHERE state='new'
        #             AND child_asn_id= %s
        #             ORDER BY logging_date desc LIMIT 1;""" % (self.id)
        #         self.env.cr.execute(query)
        #         values = self.env.cr.fetchall()
        #         comment_history = [x[0] for x in values]
        #         comment_history = ''.join(comment_history)
        #
        # # FOR ASSIGNMENT MODEL ASN STATE= ON-HOLD
        #     elif self.state == 'on-hold':
        #         query = """
        #                 SELECT comment
        #                 FROM reason_history_line
        #                 WHERE state='on-hold'
        #                 AND child_asn_id= %s
        #                 ORDER BY logging_date desc LIMIT 1;""" % (self.id)
        #         self.env.cr.execute(query)
        #         values = self.env.cr.fetchall()
        #         comment_history = [x[0] for x in values]
        #         comment_history = ''.join(comment_history)
        #
        # if cs_instructions and client_instructions and comment_history:
        #     return '[CS] : ' + cs_instructions + ', ' + comment_history + '     ' + ' [Client] : ' + client_instructions
        # elif not cs_instructions:
        #     return '[CS] : ' + comment_history + '     ' + ' [Client] : ' + client_instructions
        # elif not comment_history:
        final_instructions = '[CS] : ' + cs_instructions + ' [Client] : ' + client_instructions
        final_instructions = final_instructions.replace('\n', ' ').replace('\r', '')
        return final_instructions

    @api.multi
    def write(self, vals):
        """
            Move child ASN to revised ASNs screen and update highest child deadline in parent deadline
        """
        inst_lines, revision_type_list = [], []
        if vals.get('assignment_instruction_line') or vals.get('asn_reference_line') or vals.get('deadline'):
            if vals.get('assignment_instruction_line'):
                for ins in vals.get('assignment_instruction_line'):
                    if ins[0] == 4:
                        continue
                    if ins[0] == 2:
                        inst_lines.append(ins)
                    if ins[0] == 0:
                        inst_lines.append((0, 0, {
                            'name': ins[2].get('name'),
                            'ins_for_pm': True,
                            'mark_reviewed': True,
                            'is_original_ins': ins[2].get('is_original_ins')
                        }))
                    if ins[0] == 1:
                        inst_lines.append(ins)
                vals['assignment_instruction_line'] = inst_lines

            # client_queries = self.env['client.query'].search(
            #     ['|', ('parent_asn_id', '=', self.parent_asn_id.id), ('child_asn_id', '=', self.id)], order="id desc")
            # if client_queries:
            #     client_instruction = client_queries.filtered(lambda x: x.query_type == 'instruction')
            #     client_deadline = client_queries.filtered(lambda x: x.query_type == 'deadline')
            #     client_reference_file = client_queries.filtered(lambda x: x.query_type == 'reference')

            vals['client_query_types'] = ''

            if vals.get('deadline'):
                vals['client_query_types'] += 'Revised deadline,'
                revision_type_list.append('Deadline')

            if vals.get('assignment_instruction_line'):
                vals['client_query_types'] += 'Revised instruction,'
                revision_type_list.append('Instructions')

            if vals.get('asn_reference_line'):
                vals['client_query_types'] += 'Revised reference,'
                revision_type_list.append('Reference')

            if self.client_query_types:
                vals['client_query_types'] += self.client_query_types
            else:
                vals['client_query_types'] = vals['client_query_types'][:-1]

            if self.parent_asn_id.id:
                if vals.get('deadline') and ((datetime.strptime(vals.get('deadline') , "%Y-%m-%d %H:%M:%S") > self.parent_asn_id.deadline)):
                    self.parent_asn_id.update({'deadline': vals.get('deadline')})

            vals['revised_on'] = datetime.now()
            vals['state'] = 'revised'

        res = super(Assignment, self).write(vals)

        # send email to pm team to inform asn is revised and there is a change in the asn's Last Line
        if vals.get('assignment_instruction_line') or vals.get('asn_reference_line') or vals.get('deadline'):
            revision_type = ",".join(revision_type_list)
            self.env['mail.trigger'].with_context(revision_type=revision_type).pm_mail(self, 'asn_revised')
        return res

    @api.multi
    def action_fine_uploader_wiz(self):
        """
            To open Fine uploader wizard
            :return: Fine uploader wizard action
        """
        file_type = ''
        context = self.env.context.copy()
        if context.get('field_name') == 'asn_reference_line':
            file_type = 'refrence'

        context.update({
            'default_active_id': self.id,
            'default_active_model': 'assignment',
            'default_field_name': context.get('field_name'),
            'default_so_type': 'child_asn',
            'default_file_type': file_type,
        })
        view_id = self.env.ref('fine_uploader.view_file_uploader_wizard').id
        return {
            'name': 'Upload File(s)',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'file.uploader.wizard',
            'view_id': view_id,
            'target': 'new',
            'context': context,
        }

    @api.multi
    def open_quotation_readonly(self):
        """
            To open quotation readonly view
            :return: Quotation action
        """
        action = self.env.ref('ulatus_cs.action_pending_quotation_order_form_readonly').read()[0]
        form_view = [(self.env.ref('ulatus_cs.pending_quotation_order_form_view').id, 'form')]
        action['views'] = form_view
        action['res_id'] = self.quotation_id.id
        return action

    @api.multi
    def open_parent_asn_readonly(self):
        """
            To open parent asn readonly view
            :return: Parent ASN action
        """
        action = self.env.ref('ulatus_cs.action_assignment_order').read()[0]
        form_view = [(self.env.ref('ulatus_cs.assignment_order_form_view').id, 'form')]
        action['views'] = form_view
        action['res_id'] = self.parent_asn_id.id
        return action

    @api.multi
    def submit_post_delivery_service(self, client_geo_info, user_timezone, **kw):
        inquiry_data = self.env['sale.order'].sudo().browse(self.quotation_id).id

        target_lang_ids = False
        deadline_dt = False
        utc_delivery_date = False
        if kw.get('deadline_date', False):
            config_setting_id = self.env['ulatus.config.settings'].sudo().search([])
            # datetime_format = config_setting_id[-1].date_format + ' - ' + config_setting_id[-1].time_format
            datetime_format = '%m/%d/%Y %H:%M'
            deadline_dt = datetime.strptime(kw.get('deadline_date'), datetime_format)
            # convert back from user's timezone to UTC
            if user_timezone:
                try:
                    user_tz = pytz.timezone(user_timezone)
                    utc = pytz.utc
                    utc_delivery_date = user_tz.localize(deadline_dt).astimezone(utc)
                except Exception:
                    _logger.info("Failed to convert the value from the user's timezone (%s) to UTC", user_timezone)

        if kw.get('deadline_date_from_backend', False):
            utc_delivery_date = kw.get('deadline_date_from_backend')

        if kw.get('target_lang_ids_from_backend', False):
            target_lang_ids = kw.get('target_lang_ids_from_backend')
        else:
            target_lang_ids = request.httprequest.form.getlist('target_langs[]')

        tax_ids = self.env['account.tax'].sudo().search(
            [('currency_id', '=', inquiry_data.currency_id.id),
             ('type_tax_use', '=', 'sale')])

        revise_ins = []
        if kw.get('instruction'):
            revise_ins = [(0, 0, {'name': kw.get('instruction'), 'is_quote_revision_ins': True})]

        vals = {
                'name': 'RR',
                'is_rr_inquiry': True,
                'partner_id': inquiry_data.partner_id.id,
                'domain_id': inquiry_data.domain_id.id,
                'type': "inquiry",
                'inquiry_state': 'un_assign',
                'user_id': False,
                'currency_id': inquiry_data.currency_id.id,
                'tax_percent_ids': [(6, 0, tax_ids.ids)],
                'source_lang_id': inquiry_data.source_lang_id.id,
                'unit_id': inquiry_data.unit_id.id,
                'note': kw.get('instruction'),
                'client_deadline': utc_delivery_date,
                'target_lang_ids': [(6, 0, target_lang_ids)],
                'mem_id': inquiry_data.partner_id.active_memid.id,
                'ip_address': client_geo_info['ip_address'] if client_geo_info else False,
                'browser': client_geo_info['browser'] if client_geo_info else False,
                'country': client_geo_info['country'] if client_geo_info else False,
                'initial_create_inquiry': datetime.now(),
                'organization_id': inquiry_data.organization_id.id,
                'organization_name': inquiry_data.organization_name,
                'parent_asn_ref_id': self.parent_asn_id.id,
                'instruction_line': revise_ins,
                'service_level_id': self.service_level_id.id,
                'created_by_client': True,
            }
        rr_inquiry = self.env['sale.order'].sudo().create(vals)
        return rr_inquiry

    @api.multi
    def action_cancel(self):
        """
            To open Cancel Request wizard(file.revision.request.wiz) to cancel child asn
            :return: wizard(file.revision.request.wiz) action
        """
        ctx = self._context.copy()
        ctx.update({
            'default_child_asn_id': self.id,
            'reason_type': 'asn',
            'message': 'Do you want to Reject this Assignment..?'
        })
        view_id = self.env.ref('ulatus_cs.view_cancel_quotation_message').id
        return {
            'name': 'Cancel Request',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'file.revision.request.wiz',
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def request_for_delivery_deadline(self):
        """
            To open Request a revision in delivery deadline wizard(file.revision.request.wiz) for child asn
            :return: wizard(file.revision.request.wiz) action
        """
        ctx = self._context.copy()
        ctx.update({
            'default_child_asn_id': self.id,
        })
        view_id = self.env.ref('ulatus_cs.view_request_for_deadline_wiz').id
        return {
            'name': 'Request a revision in delivery deadline',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'file.revision.request.wiz',
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def add_instruction(self):
        """
            To open Add Instruction wizard(file.revision.request.wiz) for child asn
            :return: wizard(file.revision.request.wiz) action
        """
        ctx = self._context.copy()
        ctx.update({
            'default_child_asn_id': self.id,
        })
        view_id = self.env.ref('ulatus_cs.view_add_instruction_wiz').id
        return {
            'name': 'Add Instruction',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'file.revision.request.wiz',
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def child_asn_onhold(self):
        """
            To open ASN On-Hold wizard(file.revision.request.wiz) for child asn
            :return: wizard(file.revision.request.wiz) action
        """
        ctx = self._context.copy()
        ctx.update({
            'default_child_asn_id': self.id,
        })
        view_id = self.env.ref('ulatus_cs.view_parent_asn_hold_message').id
        return {
            'name': 'ASN On-Hold',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'file.revision.request.wiz',
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def child_asn_offhold(self):
        """
            To open ASN Off-Hold wizard(file.revision.request.wiz) for child asn
            :return: wizard(file.revision.request.wiz) action
        """
        ctx = self._context.copy()
        ctx.update({
            'default_child_asn_id': self.id,
        })
        view_id = self.env.ref('ulatus_cs.view_parent_asn_offhold_message').id
        return {
            'name': 'ASN Off-Hold',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'file.revision.request.wiz',
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def action_fine_uploader_revise_ref_file(self):
        """
            To open Fine uploader wizard for revise reference files for child asn
            :return: Fine uploader wizard action
        """
        context = self.env.context.copy()
        context.update({
            'default_active_id': self.id,
            'default_active_model': 'assignment',
            'default_field_name': 'client_query_line',
            'default_so_type': 'false',
            'default_file_uploader_no': self.env['file.uploader.wizard'].generate_seq_no(),
            'default_client_query_backend': 'True',
            'client_query': True,
        })
        view_id = self.env.ref('fine_uploader.view_file_uploader_wizard').id
        return {
            'name': 'Add a reference file',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'file.uploader.wizard',
            'view_id': view_id,
            'target': 'new',
            'context': context,
        }

    @api.multi
    def open_original_asn(self):
        """
            To open original asn view
            :return: asn action
        """
        action = self.env.ref('ulatus_cs.action_assignment_order').read()[0]
        form_view = [(self.env.ref('ulatus_cs.assignment_order_form_view').id, 'form')]
        action['views'] = form_view
        action['res_id'] = self.parent_asn_ref_id.id
        return action

    def asn_invoice_create(self):
        self._prepare_invoice()
        return None

    @api.multi
    def _prepare_invoice(self):
        """
        Prepare the dict of values to create the new invoice for a sales order. This method may be
        overridden to implement custom invoice generation (making sure to call super() to establish
        a clean extension chain).
        """
        self.ensure_one()
        company_id = self.quotation_id.company_id.id
        journal_id = (self.env['account.invoice'].with_context(
            company_id=company_id or self.env.user.company_id.id).default_get(
            ['journal_id'])['journal_id'])
        if not journal_id:
            raise UserError(_('Please define an accounting sales journal for this company.'))

        current_sale_line = self.env['asn.addons.fee.line'].search([('asn_id', '=', self.id)])
        invoice_vals = {
            'name': '',
            'origin': self.name,
            'type': 'out_invoice',
            'inv_type': 'ind' if (self.quotation_id.partner_invoice_id.send_inv_monthly is False) else 'mon',
            'po_number': self.quotation_id.po_number,
            'date_invoice': date.today(),
            'date_due': date.today(),
            'account_id': self.quotation_id.partner_invoice_id.property_account_receivable_id.id,
            'partner_id': self.quotation_id.partner_invoice_id.id,
            'partner_shipping_id': self.quotation_id.partner_shipping_id.id,
            'journal_id': journal_id,
            'currency_id': self.currency_id.id,
            'comment': self.note,
            'payment_term_id': self.quotation_id.payment_term_id.id,
            'fiscal_position_id': self.quotation_id.fiscal_position_id.id or self.quotation_id.partner_invoice_id.property_account_position_id.id,
            'company_id': company_id,
            'user_id': self.quotation_id.user_id and self.quotation_id.user_id.id,
            'team_id': self.quotation_id.team_id.id,
            # 'transaction_ids': [(6, 0, self.transaction_ids.ids)],
            'advance_payment': self.advance_payment,
            'advance_payment_value': self.advance_payment_value,
            'advance_payment_amount': self.advance_payment_amount,
            'advance_pending_amount': self.advance_pending_amount,
            'char_count': self.character_count,
            'product_id': self.parent_asn_id.product_id.id,
            'service': self.service_level_id.name,
            'assignment_id': self.id,
            'deadline': self.deadline,
            'payer_name': self.partner_id.name,
            'portal_street': self.partner_id.street,
            'portal_street2': self.partner_id.street2,
            'portal_city': self.partner_id.city,
            'portal_zip': self.partner_id.zip,
            'portal_state_id': self.partner_id.state_id.id,
            'portal_country_id': self.partner_id.country_id.id,
            'portal_phone': self.partner_id.phone,
            'portal_mobile': self.partner_id.mobile,
            # 'invoice_line_ids': [(6, 0, sale_line.id)]
        }
        print(invoice_vals)

        order_line = self.env['sale.order.line']
        # order_line._prepare_invoice_line()
        res_obj = self.env['res.partner'].search(
            [('id', '=', self.quotation_id.partner_invoice_id.id), ('send_inv_monthly', '=', False)])
        if res_obj:
            # mail_content = "  Hello  " + str(
            #     res_obj.name) + ",<br> Invoice has been created against your the inquiry " \
            #                + str(self.name) + "."
            # main_content = {
            #     'subject': _('Invoice Generated Against SO - %s') % self.name,
            #     'author_id': self.env.user.partner_id.id,
            #     'body_html': mail_content,
            #     'email_to': self.quotation_id.partner_invoice_id.email,
            # }
            inv_created = self.env['account.invoice'].create(invoice_vals)
            invoice_line_vals = []
            for sale_line in current_sale_line:
                invoice_line_vals.append((0, 0, {
                        'name': sale_line.product_id.name,
                        'origin': sale_line.product_id.name,
                        'account_id': 31,
                        'price_unit': sale_line.price_unit,
                        'quantity': 1,
                        'discount': 0.0,
                        'uom_id': sale_line.product_id.uom_id.id,
                        'product_id': sale_line.product_id.id,
                }))

            invoice_line_vals.append((0, 0, {
                        'name': self.service_level_id.name,
                        'origin': self.service_level_id.name,
                        'account_id': 31,
                        'price_unit': self.translation_fee,
                        'quantity': 1,
                        'discount': 0.0,
                        'uom_id': self.service_level_id.product_id.uom_id.id,
                        'product_id': self.service_level_id.product_id.id,
                }))
            project_mng_product = self.env.ref('ulatus_cs.project_management_cost')
            invoice_line_vals.append((0, 0, {
                'name': project_mng_product.name,
                'origin': project_mng_product.name,
                'account_id': 31,
                'price_unit': self.project_management_cost,
                'quantity': 1,
                'discount': 0.0,
                'uom_id': 1,
            }))

            invoice_line_vals.append((0, 0, {
                'name': 'Quote Level - Discount',
                'origin': project_mng_product.name,
                'account_id': 31,
                'price_unit': -self.discount,
                'quantity': 1,
                'discount': 0.0,
                'uom_id': 1,
            }))

            invoice_line_vals.append((0, 0, {
                'name': 'Quote level - Premium',
                'origin': project_mng_product.name,
                'account_id': 31,
                'price_unit': self.premium,
                'quantity': 1,
                'discount': 0.0,
                'uom_id': 1,
            }))

            self.env['account.invoice'].search([(
                'id', '=', inv_created.id)]).update({'invoice_line_ids': invoice_line_vals})

            # Validate Invoice
            inv_created.action_invoice_open()
            inv_created.update({'payment_state': 'open'})

            # Update Invoice Sequence
            if self.partner_id.send_inv_monthly is False:
                sequence_values = {
                    'number': self.env['ir.sequence'].next_by_code('seq.individual.invoice'),
                }
            else:
                sequence_values = {
                    'number': self.env['ir.sequence'].next_by_code('seq.monthly.invoice'),
                }
            self.env['account.invoice'].search([('id', '=', inv_created.id)]).update(sequence_values)

            if self.advance_payment in ('1_99', '100'):
                # self.env['mail.mail'].sudo().create(main_content).send()

                # send email on invoice generation
                inv_created.send_email_on_inv_generate()

            # Create transaction history record after RR ASN invoice generated
            if inv_created:
                last_outstanding_amount = 0
                last_transaction = self.env['transaction.history.line'].sudo().search(
                    [('partner_id', '=', inv_created.partner_id.id), ('currency_id', '=', inv_created.currency_id.id)],
                    order='create_date desc',
                    limit=1
                )
                if last_transaction:
                    last_outstanding_amount = last_transaction.outstanding_amount

                vals = {
                    'partner_id': inv_created.partner_id.id,
                    'invoice_id': inv_created.id,
                    'charges_amount': inv_created.amount_total,
                    'outstanding_amount': float_round((last_outstanding_amount + inv_created.amount_total), 2),
                    'activity': 'Charges for ' + self.name[:-8] if self.name.endswith('_On-Hold') else self.name,
                    'date': date.today(),
                    'currency_id': inv_created.currency_id.id
                }
                self.env['transaction.history.line'].sudo().create(vals)

                bi_report = self.env['bi.daily.report'].search([('quote_id', '=', self.quotation_id.id), ('target_lang_ids', 'in', [self.target_lang_id.id])])
                if bi_report:
                    bi_report_vals = {
                        'inv_type': inv_created.inv_type,
                        'invoice_create_date': self.convert_gmt_to_ist_tz(inv_created.create_date)
                    }
                    bi_report.sudo().write(bi_report_vals)
        return invoice_vals

    @api.multi
    def action_fine_uploader_revised_wiz(self):
        """
            To open Fine uploader wizard to add revised Deadline, Instructions and Reference Files
            :return: Fine uploader wizard action
        """
        self.write({
            'revision_type': False,
            'file_uploader_no': self.env['file.uploader.wizard'].generate_seq_no()
        })
        view_id = self.env.ref('ulatus_cs.child_asn_revised_view').id
        return {
            'name': 'Add or Update Deadline, Instructions and Reference Files',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'assignment',
            'res_id': self.id,
            'view_id': view_id,
            'target': 'new',
        }

    @api.multi
    def update_revised_details(self):
        """
            1. Link attachment records with asn_reference_line field
            2. Update client_query_types(used in pm dashboard)
            3. Send email to pm team to inform asn is revised
        """
        attach_ids = self.env['ir.attachment'].search([('file_uploader_no', '=', self.file_uploader_no)])
        if attach_ids:
            # link attachment records with asn_reference_line field
            self.write({'asn_reference_line': [(4, attach_id.id) for attach_id in attach_ids]})

        # Update client_query_types
        if self.revision_type:
            client_query_types_list = self.revision_type.split(', ')
            client_query_types = ",".join([REPLACEMENTS.get(x, x) for x in client_query_types_list])
            if self.client_query_types:
                self.write({'client_query_types': '%s,%s' % (client_query_types, self.client_query_types)})
            elif not self.client_query_types:
                self.write({'client_query_types': client_query_types})

            # send email to pm team to inform asn is revised and there is a change in the asn's Last Line
            self.env['mail.trigger'].with_context(revision_type=self.revision_type).pm_mail(self, 'asn_revised')
        return True

    @api.multi
    def update_bi_report_data(self, order_line):
        trans_id = order_line.service_level_line.filtered(lambda l: l.service_level_id.id == self.service_level_id.id)
        internal_client_deadline = self.deadline - timedelta(hours=1)
        if self.is_revision_asn == True:
            bi_report = self.env['bi.daily.report'].search(
                [('quote_id', '=', self.quotation_id.id), ('target_lang_ids', 'in', [self.target_lang_id.id])])
            if bi_report:
                bi_report_vals = {
                    'asn_id': self.id,
                    'asn_number': self.name,
                    'service_level_id': self.service_level_id.name,
                    'priority': self.priority,
                    'unit_id': self.parent_asn_ref_id.unit_id.name,
                    'char_count': self.character_count,
                    'asn_state': self.state,
                    'gross_fee': self.gross_fee,
                    'premium_percentage': self.parent_asn_ref_id.add_premium_rate if self.parent_asn_ref_id.add_premium_type == 'percent' else False,
                    'premium_amount': self.premium,
                    'discount_percentage': self.parent_asn_ref_id.ks_global_discount_rate if self.parent_asn_ref_id.ks_global_discount_type == 'percent' else False,
                    'discount_amount': self.discount,
                    'total_tax': self.tax,
                    'total_fees': self.total_fees,
                    'quote_confirmation_date': self.convert_gmt_to_ist_tz(self.received_on_pm) if self.received_on_pm else self.received_on_pm,
                    'asn_confirmed_by': self.user_id.name,
                    'assignment_current_status': 'Assignment',
                    'project_management_cost': self.project_management_cost,
                    'final_rate': trans_id.unit_rate,
                    'actual_client_deadline': self.convert_gmt_to_ist_tz(self.deadline) if self.deadline else self.deadline,
                    'internal_client_deadline': self.convert_gmt_to_ist_tz(internal_client_deadline) if internal_client_deadline else internal_client_deadline,
                }
                bi_report.sudo().write(bi_report_vals)
        else:
            bi_report = self.env['bi.daily.report'].search([('parent_asn_id', '=', self.parent_asn_id.id)])
            if bi_report:
                bi_report_vals = {
                    'inquiry_id': bi_report[0].inquiry_id.id,
                    'quote_id': bi_report[0].quote_id.id,
                    'parent_asn_id': bi_report[0].parent_asn_id.id,
                    'asn_id': self.id,
                    'inquiry_date': bi_report[0].inquiry_date,
                    'inquiry_state': bi_report[0].inquiry_state,
                    'mem_id': bi_report[0].mem_id,
                    'client_name': bi_report[0].client_name,
                    'target_lang_ids': [(4, self.target_lang_id.id)],
                    'service': self.source_lang_id.name + ' - ' + self.target_lang_id.name,
                    'client_deadline': bi_report[0].client_deadline,
                    'currency_id': bi_report[0].currency_id,
                    'client_type': bi_report[0].client_type,
                    'new_client': bi_report[0].new_client,
                    'client_instructions': bi_report[0].client_instructions,
                    'reject_reason': bi_report[0].reject_reason,
                    'reject_date': bi_report[0].reject_date,
                    'assignment_current_status': bi_report[0].assignment_current_status,
                    'actual_client_deadline': self.convert_gmt_to_ist_tz(self.deadline) if self.deadline else self.deadline,
                    'internal_client_deadline': self.convert_gmt_to_ist_tz(internal_client_deadline) if internal_client_deadline else internal_client_deadline,
                    'area_type': bi_report[0].area_type,
                    'subject_industrial_area_level1_id': bi_report[0].subject_industrial_area_level1_id,
                    'subject_industrial_area_level2_id': bi_report[0].subject_industrial_area_level2_id,
                    'subject_industrial_area_level3_id': bi_report[0].subject_industrial_area_level3_id,
                    'mark_as_special': bi_report[0].mark_as_special,
                    'quotataion_sent_by': bi_report[0].quotataion_sent_by,
                    'quote_state': bi_report[0].quote_state,
                    'response_time': bi_report[0].response_time,
                    'po_number': bi_report[0].po_number,
                    'project_management_cost': self.project_management_cost,
                    'final_rate': trans_id.unit_rate,
                    'organisation_name': bi_report[0].organisation_name,
                    'is_parent_or_child': 'Child'
                }

                memsource_line_ids = order_line.mapped('memsource_line').filtered(lambda l: l.sale_line_id.id == order_line.id)
                non_editable_count, wc_0_49_count, wc_50_74_count, wc_75_84_count, wc_85_94_count = 0.0, 0.0, 0.0, 0.0, 0.0
                wc_95_99_count, wc_100_count, wc_101_count, repetitions_count, machine_translation_count = 0.0, 0.0, 0.0, 0.0, 0.0
                for mem_line in memsource_line_ids:
                    if mem_line.percent_type.name == 'Non-editable Count':
                        non_editable_count += mem_line.weighted_count
                    if mem_line.percent_type.name == '0%–49%':
                        wc_0_49_count += mem_line.weighted_count
                    if mem_line.percent_type.name == '50%–74%':
                        wc_50_74_count += mem_line.weighted_count
                    if mem_line.percent_type.name == '75%–84%':
                        wc_75_84_count += mem_line.weighted_count
                    if mem_line.percent_type.name == '85%–94%':
                        wc_85_94_count += mem_line.weighted_count
                    if mem_line.percent_type.name == '95%–99%':
                        wc_95_99_count += mem_line.weighted_count
                    if mem_line.percent_type.name == '100%':
                        wc_100_count += mem_line.weighted_count
                    if mem_line.percent_type.name == '101%':
                        wc_101_count += mem_line.weighted_count
                    if mem_line.percent_type.name == 'Repetitions':
                        repetitions_count += mem_line.weighted_count
                    if mem_line.percent_type.name == 'Machine Translation':
                        machine_translation_count += mem_line.weighted_count

                bi_report_vals.update({'non_editable_count': non_editable_count,
                                       'wc_0_49_percent': wc_0_49_count,
                                       'wc_50_74_percent': wc_50_74_count,
                                       'wc_75_84_percent': wc_75_84_count,
                                       'wc_85_94_percent': wc_85_94_count,
                                       'wc_95_99_percent': wc_95_99_count,
                                       'wc_100_percent': wc_100_count,
                                       'wc_101_percent': wc_101_count,
                                       'repetitions': repetitions_count,
                                       'machine_translation': machine_translation_count,
                                       'asn_number': self.name,
                                       'service_level_id': self.service_level_id.name,
                                       'priority': self.priority,
                                       'unit_id': self.parent_asn_id.unit_id.name,
                                       'char_count': self.character_count,
                                       'asn_state': bi_report[0].asn_state,
                                       'gross_fee': self.gross_fee,
                                       'premium_percentage': self.parent_asn_id.add_premium_rate if self.parent_asn_id.add_premium_type == 'percent' else False,
                                       'premium_amount': self.premium,
                                       'discount_percentage': self.parent_asn_id.ks_global_discount_rate if self.parent_asn_id.ks_global_discount_type == 'percent' else False,
                                       'discount_amount': self.discount,
                                       'total_tax': self.tax,
                                       'total_fees': self.total_fees,
                                       'quote_confirmation_date': bi_report[0].quote_confirmation_date,
                                       'asn_confirmed_by': bi_report[0].asn_confirmed_by,
                                       'inv_type': bi_report[0].inv_type,
                                       'invoice_create_date': bi_report[0].invoice_create_date
                                       })
                self.env['bi.daily.report'].sudo().create(bi_report_vals)
        if order_line.addons_fee_line:
            for addons in order_line.addons_fee_line:
                bi_report = self.env['bi.daily.report'].search([('asn_id', '=', self.id)])
                if bi_report:
                    bi_report.write({addons.addons_id.addons_technical_field: addons.total_price})

    def suffix(self, d):
        return 'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')

    def date_suffix(self, format, date):
        return date.strftime(format).replace('{S}', str(date.day) + '<sup>' + self.suffix(date.day) + '</sup>')


class AssignmentInstructionLine(models.Model):
    _name = 'assignment.instruction.line'
    _description = 'Assignment Instruction Line'

    assignment_ins_id = fields.Many2one("assignment", "Assignment Id")
    name = fields.Text("Instruction")
    mark_reviewed = fields.Boolean("Mark as Reviewed")
    is_original_ins = fields.Boolean('Is Original Instruction')
    ins_for_pm = fields.Boolean("Instruction for PM")


class AsnAddonsFeeLine(models.Model):
    _name = 'asn.addons.fee.line'
    _description = 'ASN Addons Fee Line'

    asn_id = fields.Many2one("assignment", "ASN Id")
    product_id = fields.Many2one('product.product',
                                        string="Add-ons Service")
    unit_id = fields.Many2one('service.unit', string="Unit")
    price_unit = fields.Float("Fee")
    no_of_unit = fields.Float("No. of Unit")

