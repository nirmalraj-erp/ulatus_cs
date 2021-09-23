# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from datetime import timedelta
import time
import itertools
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError, UserError
from odoo.tools.float_utils import float_round
import pytz
from . import revise_date_tool
import logging
_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    _order = 'create_date desc'

    def _check_pending_since(self):
        """
            Calculate pending time form create
            :return: pending_since
        """
        for rec in self:
            diff = False
            days, hour, minute, total_mins = 0, 0, 0, 0.0
            if rec.initial_create_inquiry:
                now = datetime.now()
                diff = now - rec.initial_create_inquiry
            if diff:
                days, hour, minute = diff.days, diff.seconds//3600, (diff.seconds//60)%60
                duration_in_s = diff.total_seconds()
                total_mins = divmod(duration_in_s, 60)[0]
            rec.pending_since = '%s D %s Hr %s Mins' % (str(days), str(hour), str(minute))
            rec.pending_since_in_minutes = total_mins

    @api.onchange('client_deadline')
    def onchange_client_deadline(self):
        if self.client_deadline:
            current_date = datetime.strptime(
                self.dashboard_convert_to_user_timezone(datetime.now()).
                    strftime("%Y-%m-%d %H:00:00"), '%Y-%m-%d %H:00:00')
            deadline = datetime.strptime(
                self.dashboard_convert_to_user_timezone(self.client_deadline).
                    strftime("%Y-%m-%d %H:00:00"), '%Y-%m-%d %H:00:00')
            current_date = current_date + timedelta(hours=1, minutes=00,
                                                      seconds=00)
            if deadline < current_date:
                tz = 'GMT'
                if self.env.context['tz']:
                    tz = self.env.context['tz']
                today_utc = fields.Datetime.to_string(
                    pytz.timezone(tz).localize(
                        fields.Datetime.from_string(current_date),
                        is_dst=None).astimezone(pytz.utc))
                self.client_deadline = today_utc

    @api.onchange('deadline')
    def onchange_deadline(self):
        if self.deadline:
            current_date = datetime.strptime(
                self.dashboard_convert_to_user_timezone(datetime.now()).
                    strftime("%Y-%m-%d %H:00:00"), '%Y-%m-%d %H:00:00')
            deadline = datetime.strptime(
                self.dashboard_convert_to_user_timezone(self.deadline).
                    strftime("%Y-%m-%d %H:00:00"),'%Y-%m-%d %H:00:00')
            current_date = current_date + timedelta(hours=1, minutes=00,
                                                      seconds=00)
            if deadline < current_date:
                tz = 'GMT'
                if self.env.context['tz']:
                    tz = self.env.context['tz']
                today_utc = fields.Datetime.to_string(
                    pytz.timezone(tz).localize(
                        fields.Datetime.from_string(current_date),
                        is_dst=None).astimezone(pytz.utc))
                self.deadline = today_utc

    @api.onchange('order_line')
    def onchange_final_deadline(self):
        res = {}
        res.update(
            {'char_count': sum(self.order_line.mapped('character_count'))})
        fee_dict = {}
        deadline_dict = {}
        deadline = False
        for line in self.order_line:
            for service in line.service_level_line:
                if service.visible_to_client:
                    ser = service.service_level_id.id
                    if ser in fee_dict.keys():
                        fee_dict[ser] += service.fee
                    else:
                        fee_dict.update({ser: service.fee})
            if line.deadline:
                deadline_dict.update({line.id: line.deadline})
        if deadline_dict:
            max_deadline = max(deadline_dict.keys(),
                               key=(lambda k: deadline_dict[k]))
            deadline = deadline_dict.get(max_deadline)
            res.update({'deadline': deadline,
                'recommended_deadline': deadline})
        tran_ids = self.order_line.mapped('service_level_line').filtered(lambda f: f.reccommend)
        if tran_ids:
            rec_deadline = tran_ids.filtered(lambda d: d.deadline).mapped('deadline')
            res.update({'lowest_fee': sum(tran_ids.mapped('fee')),
                        'recommended_deadline': max(rec_deadline) if rec_deadline else deadline })
        else:
            if fee_dict:
                min_fee = min(fee_dict.keys(), key=(lambda k: fee_dict[k]))
                res.update({'lowest_fee': fee_dict.get(min_fee)})
        return self.update(res)

    @api.multi
    def update_end_client_domain(self):
        """
            Configure domain for end client field on inquiry and quotation
            :return: action
        """
        ctx = self._context.copy()
        model = 'update.end.client.wiz'
        ctx.update({'default_order_id': self.id})
        view_id = self.env.ref('ulatus_cs.view_update_end_client_wiz').id
        return {
            'name': 'Configure End Client',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    def inv_type(self):
        if self.partner_id.parent_id:
            if self.partner_id.parent_id.send_inv_monthly is True:
                return True
            else:
                return False
        else:
            if self.partner_id.send_inv_monthly is True:
                return True
            else:
                return False

    initial_create_inquiry = fields.Datetime(string="Initial Create Inquiry")
    # Add by Darshan
    new_client = fields.Boolean(related='partner_id.new_client',
                                string="New Client")
    new_org = fields.Boolean("New Organization")
    is_seen = fields.Boolean("Is Seen")
    recommended_deadline = fields.Datetime(
        "Recommended Deadline", copy=True)
    char_count = fields.Integer("Character Count")
    lowest_fee = fields.Monetary("Fee")
    # use for grant access rights to user 
    user_id = fields.Many2one(
        'res.users', string='User', track_visibility='onchange')
    # visible user name when quotation revised or revision request handle by multiple user
    r_user_id = fields.Many2one(
        'res.users', string='Display User')
    partner_id = fields.Many2one(
        'res.partner', string='Client', states={}, track_visibility='onchange')
    inquiry_id = fields.Many2one('sale.order', string="Inquiry Ref")
    service_level_id = fields.Many2one(
        'service.level', string='Translation Level', track_visibility='onchange')
    inquiry_date = fields.Date("Inquiry Date", track_visibility='onchange')
    pending_since = fields.Char('Pending Since', compute="_check_pending_since")
    pending_since_in_minutes = fields.Float('Pending Since In Minutes', compute="_check_pending_since")
    pending_notification_sent = fields.Boolean('Pending Since Notification Sent', default=False)
    # hour_day = fields.Selection([('hour', 'Hours'),
    #                              ('day', 'Days')],
    #                             "Days", compute="_check_pending_since")
    source_lang_id = fields.Many2one(
        'res.lang', string='Source language', track_visibility='onchange')
    currency_id = fields.Many2one("res.currency", related=False, required=False, string="Currency",
                                  readonly=False, track_visibility='onchange')
    state = fields.Selection([('draft', 'New Quotation'),
                              ('sent', 'Quotation Sent'),
                              ('revision_request', 'Revision Requested'),
                              ('revise', 'Revised'),
                              ('on-hold', 'ASN On-Hold'),
                              ('sale', 'ASN confirmed'),
                              ('asn_work_in_progress', 'ASN Work-in-progress'),
                              ('done', 'ASN Completed'),
                              ('cancel', 'Rejected')],
                             'Status', default='draft',
                             track_visibility='onchange', copy=True)
    deadline = fields.Datetime(
        "Delivery Deadline", track_visibility='onchange', copy=True)
    client_deadline = fields.Datetime(
        "Client Deadline", track_visibility='onchange', copy=True)
    sale_bool = fields.Boolean()
    mark_as_special = fields.Boolean(
        "Mark as Special", track_visibility='onchange')
    mark_as_trial = fields.Boolean("Mark as Trial")
    send_inv_monthly = fields.Boolean('Inv Type', default=inv_type)
    advance_payment = fields.Selection(
        [('0', '0%'),
         ('1_99', '1-99%'),
         ('100', '100%')], string='Advance Payment Type', default='0')
    advance_payment_value = fields.Integer('Advance Payment %')
    po_required = fields.Boolean(readonly=True)
    po_number = fields.Char('Client PO#')
    additional_comments = fields.Text("Additional Comments")
    sale_order_addons_line = fields.One2many(
        "sale.order.addons.line", 'sale_addons_id', 'Sale Order Addons Lines', copy=True)
    checklist_line = fields.One2many(
        'checklist.line', 'sale_checklist_id', 'ChickList Line', copy=True)
    is_file_revision = fields.Boolean("Is File Revision", default=False)
    reason_history_line = fields.One2many(
        'reason.history.line', 'quote_id', 'Reason History Line')
    product_id = fields.Many2one('product.product', string="Product")
    priority = fields.Selection([('standard', 'Standard'),
                                ('express', 'Express'),
                                ('super_express', 'Super Express')], 'Priority', default='standard')
    project_management_cost = fields.Float("Project Management Cost")
    sequence = fields.Integer(related="partner_id.sequence", string="Sequence")
    tax_percent_ids = fields.Many2many("account.tax", string="Tax Percent")
    add_translation_level_line = fields.One2many("add.translation.level.line",
                                                 "sale_order_id",
                                                 "Add Translation Level Line", copy=True)
    """
    Below fields are for revision requests and maintain history
    """
    has_revision = fields.Boolean("Has Revision", default=False)
    main_quotation_id = fields.Many2one('sale.order', string='Main Quotation')
    revision_request_line = fields.One2many(
        'sale.order', 'main_quotation_id', 'Revision Requests')
    quotation_ref_line = fields.One2many(
        'sale.order', 'quotation_ref_id', 'Ref Quotation')
    to_show = fields.Boolean("Show to Client", default=False)
    """
    Inquiry Details
    """
    question_validity_date = fields.Integer("Question's Validity Date")
    parent_id = fields.Many2one(
        'sale.order', string="Parent ASN")
    inquiry_state = fields.Selection(
        [('un_assign', 'Unassigned'), ('assign', 'Assigned'),
         ('process', 'Processed')], 'Inquiry State', default='un_assign',
        track_visibility='onchange')
    type = fields.Selection([('inquiry', 'Inquiry'),
                             ('quotation', 'Quotation'), ('asn', 'ASN')],
                            'Type', track_visibility='onchange')
    target_lang_ids = fields.Many2many(
        'res.lang', string="Target language", track_visibility='onchange')
    translation_file_line = fields.One2many(
        "ir.attachment", 'inquiry_id', 'Original File Line',
        track_visibility='onchange', domain=[('file_type', '=', 'client')], copy=True)
    refrence_file_line = fields.One2many(
        "ir.attachment", 'inquiry_id', 'Refrence File Line',
        track_visibility='onchange', domain=[('file_type', '=', 'refrence')], copy=True)
    end_client_id = fields.Many2one('res.partner', string="End Client",
                                    track_visibility='onchange')
    organization_id = fields.Many2one('res.partner', string="Organization",
         track_visibility='onchange')
    organization_name = fields.Char("Organization Name")
    """
    Parent Assignment Configurartions
    """
    revision_no = fields.Integer("Revision No.", default=1)
    cs_state = fields.Selection([('un_assign', 'Unassigned'),
                                ('assign', 'Assigned'),
                                ('sent_to_pm_team', 'Sent to PM Team')],
                                'CS State', default='un_assign',
                                track_visibility='onchange')
    quotation_ref_id = fields.Many2one('sale.order', string="Quotation Ref.")
    parent_asn_completed_file_line = fields.One2many(
        "ir.attachment", 'parent_asn_id', 'parent ASN Completed File Lines',
        domain=[('file_type', '=', 'complete')], track_visibility='onchange', copy=True)
    parent_asn_ins_line = fields.One2many("parent.asn.instruction.line",
                                          'parent_ins_asn_id',
                                          'parent ASN Instruction Line', copy=True)
    child_asn_count = fields.Integer(
        compute='_compute_child_asn_count', string='Child ASN')

    # Child Assignment
    child_asn_line = fields.One2many("assignment", 'parent_asn_id',
                                     'Child Asn Lines', copy=True)
    reject_reason = fields.Char("Reason", track_visibility='onchange')
    # MEMID for set while Quotation process
    mem_id = fields.Many2one("membership.master", string="MEMID", track_visibility='onchange')
    domain_id = fields.Many2one("org.domain", string="Domain", track_visibility='onchange')
    # Unit of measure for source language
    unit_id = fields.Many2one('service.unit', string="Unit",
                              track_visibility='onchange')
    instruction_line = fields.One2many('sale.instruction.line', 'order_id',
                                       'Instructions', copy=True)
    is_delivered = fields.Boolean("Any Child Delivered", default=False)
    country = fields.Char("Country")
    ip_address = fields.Char("IP Address")
    browser = fields.Char("Browser")
    reject_date = fields.Datetime("Reject Date", track_visibility='onchange')
    area_type = fields.Selection([('subject_area', 'Subject Area'),
                                  ('industrial_area', 'Industrial Area')], 'Area Type')
    subject_industrial_area_level1_id = fields.Many2one("subject.industrial.area.level1", "Level 1")
    subject_industrial_area_level2_id = fields.Many2one("subject.industrial.area.level2.line", "Level 2")
    subject_industrial_area_level3_id = fields.Many2one("subject.industrial.area.level3.line", "Level 3")
    level3_other_area_bool = fields.Boolean("Others Bool", default=False)
    level3_other_area = fields.Char("Others")
    received_on_pm = fields.Datetime("Received On", track_visibility='onchange')
    is_rr_inquiry = fields.Boolean("Is RR Inquiry", default=False)
    parent_asn_ref_id = fields.Many2one('sale.order', string="Original ASN Ref.")

    # To maintain files uploaded by client
    client_files_line = fields.One2many("ir.attachment", 'client_inquiry_id', 'Original Files Uploaded By Client')
    rr_sequence = fields.Integer("RR ASN Sequence", default=1)
    advance_payment_amount = fields.Float("Advance Payment Amount")
    advance_pending_amount = fields.Float("Advance Pending Amount")

    # Technical field: to get previous state of quotation(for progress bar)
    quote_previous_state = fields.Char('Status on Client End')
    asn_previous_state = fields.Char('Status on Client End For ASN')
    on_hold_cancelled = fields.Boolean('On-Hold ASN Cancelled', default=False)
    send_reminder_datetime = fields.Datetime("Send Quotation Reminder Datetime")
    send_reminder_count = fields.Integer("Reminders sent ", default=False)
    is_reminder_sent = fields.Integer('Is Quotation Reminder Sent', default=0)

    created_by_client = fields.Boolean('Created By Client', default=False)
    quote_sent_datetime = fields.Datetime("Quotation Sent")
    # endclient_weightage_id = fields.Many2one('endclient.weightage', 'Endclient Weightage')
    hide_download_button = fields.Boolean('Hide Download Button', default=False)
    parent_asn_complete_date = fields.Datetime("Parent ASN Complete Date", track_visibility='onchange')

    is_legacy_data = fields.Boolean('Is Legacy Data', default=False)
    legacy_parent_asn_status = fields.Char('Legacy Parent ASN Status')
    legacy_parent_asn_no = fields.Char('Legacy Parent ASN No.')
    legacy_parent_total_fees = fields.Float('Legacy Parent ASN Total Fees')
    legacy_serial_no = fields.Char('Legacy Serial No.')
    legacy_parent_actual_delivery_datetime = fields.Datetime('Legacy Parent Actual Delivery Datetime')
    quote_confirmation_datetime = fields.Datetime("Quote Confirmation")
    legacy_data_line = fields.One2many("legacy.data.line", 'sale_order_id', 'Legacy Data Line')
    legacy_quotation_created = fields.Boolean('Legacy Quotation Created', default=False)
    legacy_asn_created = fields.Boolean('Legacy ASN Created', default=False)

    trial_flag = fields.Boolean('Mark as Trial', default=False)
    process_type = fields.Selection([('memsource', 'Memsource'), ('manually', 'Manually')], string='Process Type')

    deadline_breach = fields.Selection([('yes', 'Yes'),
                                        ('no', 'No')],
                                       'Deadline Breach', default='no')
    delivered_on = fields.Datetime(string="Delivered On")

    @api.onchange('area_type')
    def reset_dropdown_data(self):
        if self.area_type:
            self.subject_industrial_area_level1_id = [(6, 0, [])]

    @api.onchange('subject_industrial_area_level1_id')
    def get_area_level1_id(self):
        lst = []
        self.level3_other_area = False
        self.subject_industrial_area_level2_id = [(6, 0, [])]
        level1_line = [rec.id for rec in self.subject_industrial_area_level1_id]
        level2_line = [rec.id for rec in self.subject_industrial_area_level2_id.filtered(
            lambda x: x.level2_id.level1_id.id in level1_line)]
        self.subject_industrial_area_level2_id = [(6, 0, level2_line)]

    @api.onchange('subject_industrial_area_level2_id')
    def get_area_level2_id(self):
        self.level3_other_area = False
        self.subject_industrial_area_level3_id = [(6, 0, [])]
        level2_line = [rec.id for rec in self.subject_industrial_area_level2_id]
        level3_line = [rec.id for rec in self.subject_industrial_area_level3_id.filtered(
            lambda x: x.level3_id.parent_level2_line_id.id in level2_line)]
        self.subject_industrial_area_level3_id = [(6, 0, level3_line)]

    @api.onchange('subject_industrial_area_level3_id')
    def get_other_field(self):
        self.level3_other_area = False
        if self.subject_industrial_area_level3_id and self.subject_industrial_area_level3_id.name == 'Others':
            self.level3_other_area_bool = True
        else:
            self.level3_other_area_bool = False

    @api.onchange('translation_file_line')
    def onchange_translation_file_line(self):
        original_file_dict = {}
        for file in self.translation_file_line:
            if file.datas_fname in original_file_dict.keys():
                raise ValidationError(_("File with same name already exits!"))
            else:
                original_file_dict.update({file.datas_fname: False})

    @api.onchange('refrence_file_line')
    def onchange_refrence_file_line(self):
        ref_file_dict = {}
        for file in self.refrence_file_line:
            if file.datas_fname in ref_file_dict.keys():
                raise ValidationError(_("File with same name already exits!"))
            else:
                ref_file_dict.update({file.datas_fname: False})

    @api.onchange('currency_id')
    def _onchange_currency_id(self):
        if self.currency_id:
            tax_ids = self.env['account.tax'].search(
                [('currency_id', '=', self.currency_id.id),
                 ('type_tax_use', '=', 'sale')])
            self.tax_percent_ids = [(6, 0, tax_ids.ids)]

    def _compute_child_asn_count(self):
        """
        calculate Child ASN Delivered count
        :return: total count
        """
        if self.child_asn_line:
            self.child_asn_count = len(self.child_asn_line)
        return True

    def recomended_translation(self):
        quotation_id = self.search([('inquiry_id', '=', self.id),
                                    ('state', 'in', ('sent', 'revise'))])
        service = []
        if quotation_id:
            recommended_service = quotation_id.order_line.mapped('service_level_line').filtered(lambda l:l.reccommend)
            if recommended_service:
                total_fee = self.tooltip_details()[0].get('total_project_cost')
                service.append({
                    'currency_id': quotation_id.currency_id,
                    'fee': total_fee,
                    'deadline': max(recommended_service.mapped('deadline')),
                    'name': recommended_service.mapped(
                        'service_level_id').name})
        return service

    def tooltip_details(self):
        quotation_id = self.search([('inquiry_id', '=', self.id),
                                    ('state', 'in', ('sent', 'revise'))])
        tooltip_list = []
        if quotation_id:
            recommended_service = quotation_id.order_line.mapped('service_level_line').filtered(lambda l: l.reccommend)

            if quotation_id.currency_id.id == 20:
                total_translation_cost = float_round(sum(recommended_service.mapped('fee')), 0)
                total_addons_cost = float_round(sum([addons.addons_price for addons in quotation_id.sale_order_addons_line]), 0)
                project_mng_cost = float_round(((total_translation_cost + total_addons_cost) * quotation_id.project_management_cost / 100), 0)
                total_gross_fee = float_round((total_translation_cost + total_addons_cost + project_mng_cost),0)

                if quotation_id.discount_reason == 'First Project Discount':
                    if quotation_id.ks_global_discount_type == 'percent':
                        total_discount = float_round((((total_translation_cost + total_addons_cost) * quotation_id.ks_global_discount_rate) / 100), 0)
                    else:
                        total_discount = float_round(quotation_id.ks_global_discount_rate, 0)
                else:
                    if quotation_id.ks_global_discount_type == 'percent':
                        total_discount = float_round(((total_gross_fee * quotation_id.ks_global_discount_rate) / 100), 0)
                    else:
                        total_discount = float_round(quotation_id.ks_global_discount_rate, 0)
                if quotation_id.add_premium_type == 'percent':
                    total_premium = float_round(((total_gross_fee - total_discount) * quotation_id.add_premium_rate) / 100, 0)
                else:
                    total_premium = float_round(quotation_id.add_premium_rate,0)
                subtotal_without_tax = float_round((total_gross_fee - total_discount + total_premium),0)
            else:
                total_translation_cost = float_round(sum(recommended_service.mapped('fee')),2)
                total_addons_cost = float_round(sum([addons.addons_price for addons in quotation_id.sale_order_addons_line]),2)
                project_mng_cost = float_round((total_translation_cost + total_addons_cost) * quotation_id.project_management_cost / 100,2)
                total_gross_fee = float_round((total_translation_cost + total_addons_cost + project_mng_cost), 2)
                if quotation_id.ks_global_discount_type == 'percent':
                    total_discount = float_round((total_gross_fee * quotation_id.ks_global_discount_rate) / 100, 2)
                else:
                    total_discount = float_round(quotation_id.ks_global_discount_rate,2)
                if quotation_id.add_premium_type == 'percent':
                    total_premium = float_round(((total_gross_fee - total_discount) * quotation_id.add_premium_rate) / 100,2)
                else:
                    total_premium = float_round(quotation_id.add_premium_rate,2)
                subtotal_without_tax = float_round(total_gross_fee - total_discount + total_premium,2)

            # total_taxs = sum([(subtotal_without_tax * taxs.amount)/100 if taxs.amount_type == 'percent' else taxs.amount for taxs in quotation_id.tax_percent_ids])
            tax_list = []
            for taxs_id in quotation_id.tax_percent_ids:
                if taxs_id.amount_type == 'percent':
                    if quotation_id.currency_id.id == 20:
                        tax_list.append(float_round((subtotal_without_tax * taxs_id.amount) / 100, 0))
                    else:
                        tax_list.append(float_round((subtotal_without_tax * taxs_id.amount) / 100, 2))
                elif taxs_id.amount_type == 'group':
                    for child_tax in taxs_id.children_tax_ids:
                        if child_tax.amount_type == 'fixed':
                            if quotation_id.currency_id.id == 20:
                                tax_list.append(float_round(child_tax.amount,0))
                            else:
                                tax_list.append(float_round(child_tax.amount,2))
                        else:
                            if quotation_id.currency_id.id == 20:
                                tax_list.append(float_round((subtotal_without_tax * child_tax.amount) / 100, 0))
                            else:
                                tax_list.append(float_round((subtotal_without_tax * child_tax.amount) / 100, 2))
                elif taxs_id.amount_type == 'fixed':
                    if quotation_id.currency_id.id == 20:
                        tax_list.append(float_round(taxs_id.amount, 0))
                    else:
                        tax_list.append(float_round(taxs_id.amount, 2))
            if quotation_id.currency_id.id == 20:
                grand_total_tax = float_round(sum(tax_list), 0)
            else:
                grand_total_tax = float_round(sum(tax_list), 2)

            total_project_cost = subtotal_without_tax + grand_total_tax
            if quotation_id.currency_id.id == 20:
                tooltip_list.append({
                    'quotation_id': quotation_id,
                    'total_translation_cost': round(total_translation_cost),
                    'total_addons_cost': round(total_addons_cost),
                    'project_mng_cost': round(project_mng_cost),
                    'total_gross_fee': round(total_gross_fee),
                    'discount_type': quotation_id.ks_global_discount_type,
                    'total_discount': round(total_discount),
                    'discount_percent': quotation_id.ks_global_discount_rate,
                    'premium_type': quotation_id.add_premium_type,
                    'total_premium': round(total_premium),
                    'total_percent': quotation_id.add_premium_rate,
                    'subtotal_without_tax': round(subtotal_without_tax),
                    'grand_total_tax': round(grand_total_tax),
                    'total_project_cost': round(total_project_cost),

                })
            else:
                tooltip_list.append({
                    'quotation_id':quotation_id,
                    'total_translation_cost': '%.2f' % (round(total_translation_cost,2)),
                    'total_addons_cost': '%.2f' % (round(total_addons_cost,2)),
                    'project_mng_cost': '%.2f' % (round(project_mng_cost,2)),
                    'total_gross_fee': '%.2f' % (round(total_gross_fee,2)),
                    'discount_type': quotation_id.ks_global_discount_type,
                    'total_discount': '%.2f' % (round(total_discount,2)),
                    'discount_percent': '%.2f' % quotation_id.ks_global_discount_rate,
                    'premium_type': quotation_id.add_premium_type,
                    'total_premium': '%.2f' % (round(total_premium,2)),
                    'total_percent': '%.2f' % quotation_id.add_premium_rate,
                    'subtotal_without_tax': '%.2f' % (round(subtotal_without_tax,2)),
                    'grand_total_tax': '%.2f' % (round(grand_total_tax,2)),
                    'total_project_cost': '%.2f' % (round(total_project_cost,2)),

                })
        return tooltip_list

    def unit_count(self):
        quotation_id = self.search([('inquiry_id','=', self.id),
                                    ('state', 'in', ('sent', 'revise'))])
        unit_count = 0
        if quotation_id:
            unit_count = quotation_id.char_count
        return unit_count

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        self.mem_id = self.partner_id.active_memid.id if self.partner_id.active_memid else False
        self.source_lang_id = self.partner_id.source_lang_id.id if self.partner_id.source_lang_id else False
        self.target_lang_ids = [(6, 0, self.partner_id.target_lang_ids.ids)] \
            if self.partner_id.target_lang_ids else False
        self.currency_id = self.partner_id.client_currency_id.id
        self.organization_id = self.partner_id.parent_id.id if self.partner_id.parent_id else False
        if self.partner_id.end_client_ids:
            if len(self.partner_id.end_client_ids) == 1:
                self.end_client_id = self.partner_id.end_client_ids.id
        else:
            self.end_client_id = False

    @api.multi
    def action_open_child_asn(self):
        """
            Open child assignment from parent assignment view
            :return: action: action
        """
        child_asn = self.mapped('child_asn_line')
        action = self.env.ref('ulatus_cs.action_child_asn').read()[0]
        action['domain'] = [('id', 'in', child_asn.ids)]
        return action

    @api.multi
    def add_translation_level(self):
        ctx = self._context.copy()
        model = 'sale.order'
        if self.partner_id.service_level_id:
            service_level = []
            if not self.add_translation_level_line and \
                    self.partner_id.service_level_id.id in \
                    self.product_id.translation_level_ids.ids:
                service_level = [(0, 0, {
                    'service_level_id': self.partner_id.service_level_id.id,
                    'visible_to_client': True})]
                self.write({'add_translation_level_line': service_level})
        view_id = self.env.ref(
            'ulatus_cs.quotation_add_translation_level_view').id
        return {
            'name': 'Add Translation Level',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'res_id': self.id,
            'target': 'new',
            'context': ctx,
        }

    @api.onchange('add_translation_level_line')
    def onchange_add_translation_level_line(self):
        service_dict = {}
        # visible_service_count = len(list(filter(lambda service:
        #                                         service.visible_to_client,
        #                                         self.add_translation_level_line)))
        # if not self.add_translation_level_line:
        #     raise ValidationError(_("Minimum one line is required for Translation Level!"))
        # if visible_service_count > 3:
        #     raise UserError(_("You cannot select 'Visible to Client' in more"
        #                       " than 3 Translation Services!"))
        for service in self.add_translation_level_line:
            ser = service.service_level_id
            if ser:
                service.visible_to_client = True
            if ser.id in service_dict.keys():
                raise ValidationError(
                    "You can not select duplicate translation level!")
            else:
                service_dict.update({ser.id: False})
            if service.reccommend:
                if service.reccommend in service_dict.values():
                    raise ValidationError((
                        "Already recommended on 1 translation level,"
                        " Please uncheck other if you wish to recommend this"
                        " one!"))
                service_dict.update({ser.id: service.reccommend})

    @api.multi
    def update_service_level(self):
        # to change check_deadline field false from Add Translation Level Button
        update_trans_query1 = """UPDATE sale_order_line
                               SET check_deadline=false"""
        if len(self.order_line.ids) == 1:
            tup = self.order_line.id
            update_trans_query2 = """WHERE id=%s""" %str(tup)
        else:
            tup = tuple(self.order_line.ids)
            update_trans_query2 = """WHERE id IN %s""" %str(tup)

        update_trans_query = update_trans_query1 + " \n " + update_trans_query2
        self.env.cr.execute(update_trans_query)
        self.env.cr.commit()

        translation_list = list(filter(lambda service: service.visible_to_client
                                       , self.add_translation_level_line))

        recommended_list = list(
            filter(lambda recommended: recommended.reccommend,
                   self.add_translation_level_line))
        if self.add_translation_level_line:
            if len(self.add_translation_level_line) > 1:
                visible_service_count = len(translation_list)
                recommended_service_count = len(recommended_list)
                if visible_service_count < 1:
                    raise UserError(_("Please select at least 1 Translation Level!"))
                if visible_service_count > 3:
                    raise UserError(_("You can not select more than 3 Translation Level!"))
                if recommended_service_count < 1:
                    raise UserError(_("Please select 'recommended' at least in 1 Translation Level!"))
            if len(self.add_translation_level_line) == 1:
                self.add_translation_level_line[0].visible_to_client = True
                self.add_translation_level_line[0].reccommend = True
        service_lines = []
        del_tra_line = self.order_line.mapped("service_level_line"). \
            filtered(lambda f: f.service_level_id.id not in
                               self.add_translation_level_line.mapped("service_level_id").ids)
        if del_tra_line:
            del_tra_line.unlink()
        end_client, membership_id = '', ''
        if self.end_client_id:
            end_client = """ AND end_client_id = """ + str(self.end_client_id.id)
        else:
            end_client = """ AND end_client_id is NULL """
        if self.mem_id:
            membership_id = """ AND membership_id = """ + str(self.mem_id.id)
        else:
            membership_id = """ AND membership_id is NULL """

        for rec in self.add_translation_level_line:
            translation_line = self.order_line.mapped("service_level_line"). \
                filtered(lambda f: f.service_level_id.id ==
                                   rec.service_level_id.id)
            if translation_line:
                translation_line.write({
                    'reccommend': rec.reccommend,
                    'add_translation_level_id': rec.id,
                    'visible_to_client': rec.visible_to_client})
            else:
                for line in self.order_line:
                    fee = []
                    fee_updated = False
                    fee_query = """SELECT price from fee_master 
                                   WHERE product_id = %s 
                                   AND translation_level_id = %s
                                   AND priority = '%s'
                                   AND source_lang_id = %s 
                                   AND target_lang_id = %s
                                   AND currency_id = %s
                                """ % (
                        str(self.product_id.id), str(rec.service_level_id.id),
                        str(self.priority), str(self.source_lang_id.id),
                        str(line.target_lang_id.id), str(self.currency_id.id))

                    common_query = fee_query
                    fee_query += end_client + membership_id
                    self.env.cr.execute(fee_query)
                    data = self.env.cr.fetchall()
                    fee = [x[0] for x in data]
                    if fee:
                        fee_updated = True
                        self.env['service.level.line'].create({
                             'unit_rate': fee[0] or 0.0,
                             'fee': fee[0] * line.character_count,
                             'service_level_id': rec.service_level_id.id,
                             'reccommend': rec.reccommend,
                             'add_translation_level_id': rec.id,
                             'visible_to_client': rec.visible_to_client,
                             'sale_service_line_id': line.id,
                         })
                    if not fee_updated and self.mem_id:
                        fee_query = common_query + membership_id + """AND end_client_id is NULL"""
                        self.env.cr.execute(fee_query)
                        data = self.env.cr.fetchall()
                        fee = [x[0] for x in data]
                        if fee:
                            fee_updated = True
                            self.env['service.level.line'].create({
                                'unit_rate': fee[0] or 0.0,
                                'fee': fee[0] * line.character_count,
                                'service_level_id': rec.service_level_id.id,
                                'reccommend': rec.reccommend,
                                'add_translation_level_id': rec.id,
                                'visible_to_client': rec.visible_to_client,
                                'sale_service_line_id': line.id,
                            })
                    if not fee_updated and self.end_client_id:
                        fee_query = common_query + end_client + """AND membership_id is NULL"""
                        self.env.cr.execute(fee_query)
                        data = self.env.cr.fetchall()
                        fee = [x[0] for x in data]
                        if fee:
                            fee_updated = True
                            self.env['service.level.line'].create({
                                'unit_rate': fee[0] or 0.0,
                                'fee': fee[0] * line.character_count,
                                'service_level_id': rec.service_level_id.id,
                                'reccommend': rec.reccommend,
                                'add_translation_level_id': rec.id,
                                'visible_to_client': rec.visible_to_client,
                                'sale_service_line_id': line.id,
                            })
                    if not fee_updated:
                        fee_query = common_query + """ AND end_client_id is NULL 
                                                       AND membership_id is NULL"""
                        self.env.cr.execute(fee_query)
                        data = self.env.cr.fetchall()
                        fee = [x[0] for x in data]
                        if fee:
                            self.env['service.level.line'].create({
                                'unit_rate': fee[0] or 0.0,
                                'fee': fee[0] * line.character_count,
                                'service_level_id': rec.service_level_id.id,
                                'reccommend': rec.reccommend,
                                'add_translation_level_id': rec.id,
                                'visible_to_client': rec.visible_to_client,
                                'sale_service_line_id': line.id,
                            })
                        else:
                            self.env['service.level.line'].create({
                                'unit_rate': 0.0,
                                'fee': 0.0,
                                'service_level_id': rec.service_level_id.id,
                                'reccommend': rec.reccommend,
                                'add_translation_level_id': rec.id,
                                'visible_to_client': rec.visible_to_client,
                                'sale_service_line_id': line.id,
                            })
        self.onchange_final_deadline()
        return True

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'seq.new.inquiry') or '/'
        if vals.get('name', 'RR') == 'RR':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'seq.revision.request.inquiry') or '/'
        if vals.get('type') == 'inquiry':
            vals['inquiry_date'] = fields.Date.today()
        res = super(SaleOrder, self).create(vals)
        if res.inquiry_state == 'un_assign' and res.state == 'draft' and res.type != 'asn' \
                and not res.created_by_client:
            res.initial_create_inquiry = datetime.now()
        if res.inquiry_state == 'un_assign' and res.state == 'draft' and res.type != 'asn':
            if res.is_rr_inquiry:
                for lang in res.target_lang_ids:
                    bi_report_vals = {
                        'inquiry_id': res.id,
                        'website_name': 'Global',
                        'client_type': res.partner_id.client_type_id.name,
                        'new_client': 'New' if res.partner_id.new_client == True else 'Existing',
                        'target_lang_ids': [(4, lang.id)],
                        'is_rr_inquiry': 'Yes',
                        'service': res.source_lang_id.name + ' - ' + lang.name if lang.id and res.source_lang_id else '',
                        'organisation_name': res.organization_id.name if res.organization_id else '',
                        'assignment_current_status': 'Inquiry',
                        'inquiry_date': self.convert_gmt_to_ist_tz(datetime.now()),
                        'currency_id': res.currency_id.name,
                        'client_instructions': res.note,
                        'is_parent_or_child': 'RR',
                        'client_deadline': self.convert_gmt_to_ist_tz(res.client_deadline)
                    }
                    self.env['bi.daily.report'].sudo().create(bi_report_vals)
            else:
                bi_report_vals = {
                    'inquiry_id': res.id,
                    'website_name': 'Global',
                    'client_type': res.partner_id.client_type_id.name,
                    'new_client': 'New' if res.partner_id.new_client == True else 'Existing',
                    'target_lang_ids': [(6, 0, res.target_lang_ids.ids)],
                    'service': ', '.join([res.source_lang_id.name + ' - ' + rec.name for rec in res.target_lang_ids]) if res.target_lang_ids else '',
                    'organisation_name': res.organization_id.name if res.organization_id else '',
                    'assignment_current_status': 'Inquiry',
                    'inquiry_date': self.convert_gmt_to_ist_tz(datetime.now()),
                    'currency_id': res.currency_id.name,
                    'client_instructions': res.note,
                    'is_parent_or_child': 'Parent',
                    'client_deadline': self.convert_gmt_to_ist_tz(res.client_deadline)
                }
                self.env['bi.daily.report'].sudo().create(bi_report_vals)
        return res

    @api.multi
    def write(self, vals):
        """
            Validation : To prevent add more than 3 translation level
            :param vals: default vals
            :return: super call
        """
        res = super(SaleOrder, self).write(vals)
        if len(self.add_translation_level_line) > 3:
            raise UserError(_("You can not select more than 3 Translation Level!"))
        if self.advance_payment == '1_99' and (self.advance_payment_value <= 0 or self.advance_payment_value > 99):
            raise UserError(_("Advance Payment % should be between 1 to 99!"))
        return res

    def create_invoice(self):
        inv_obj = self.env['account.invoice']
        inv_data = self._prepare_invoice()
        invoice = inv_obj.create(inv_data)
        if invoice and self.order_line:
            for line in self.order_line:
                inv_line = line.invoice_line_create_vals(
                    invoice.id, line.product_uom_qty,
                )
                invoice.invoice_line_ids = inv_line
            invoice._onchange_invoice_line_ids()

    def _compute_access_url(self):
        super(SaleOrder, self)._compute_access_url()
        for order in self:
            if order.type == 'asn':
                order.access_url = '/page/order_details/%s' % (order.id)
            elif order.type == 'inquiry':
                order.access_url = '/page/inquiry_details/%s' % (order.id)
            elif order.type == 'quotation':
                order.access_url = '/page/quotations_details/%s' % (order.id)
            else:
                order.access_url = '/page/inquiry_page/%s' % (order.id)

    @api.multi
    def preview_sale_order(self):
        self.ensure_one()
        service_level_line = self.order_line.mapped(
            'service_level_line').filtered(lambda line: line.visible_to_client)
        deadline = service_level_line.mapped('deadline')
        if not service_level_line:
            raise ValidationError(("Please Load Translation Level for this Quotation!"))
        if False in deadline:
            raise ValidationError(
                ("Please enter missing deadline for Translation Level!"))
        if not self.deadline:
            raise ValidationError(
                ("Please enter deadline for this Quotation!"))
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': self.get_portal_url(),
        }

    @api.multi
    def add_reference_file(self):
        ctx = self._context.copy()
        ctx.update({'default_parent_asn_id': self.id})
        model = 'file.revision.request.wiz'
        view_id = self.env.ref('ulatus_cs.add_reference_file_wiz_form_view').id
        return {
            'name': 'Add a reference file',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def add_instruction(self):
        ctx = self._context.copy()
        ctx.update({'default_parent_asn_id': self.id})
        model = 'file.revision.request.wiz'
        view_id = self.env.ref('ulatus_cs.view_add_instruction_wiz').id
        return {
            'name': 'Add Instruction',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def request_for_delivery_deadline(self):
        ctx = self._context.copy()
        ctx.update({'default_parent_asn_id': self.id})
        model = 'file.revision.request.wiz'
        view_id = self.env.ref('ulatus_cs.view_request_for_deadline_wiz').id
        return {
            'name': 'Request a revision in delivery deadline',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def parent_asn_onhold(self):
        ctx = self._context.copy()
        ctx.update({'default_parent_asn_id': self.id})
        model = 'file.revision.request.wiz'
        view_id = self.env.ref('ulatus_cs.view_parent_asn_hold_message').id
        return {
            'name': ('ASN On-Hold'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def parent_asn_offhold(self):
        ctx = self._context.copy()
        ctx.update({'default_parent_asn_id': self.id})
        model = 'file.revision.request.wiz'
        view_id = self.env.ref('ulatus_cs.view_parent_asn_offhold_message').id
        return {
            'name': ('ASN Off-Hold'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def download_all_original_files(self):
        """
        Use for download all translation file with help of controller.
        :return: Download file url.
        """
        for rec in self:
            if rec.translation_file_line:
                # zipname = 'Translation Files'
                url = '/web/binary/download_document?tab_id=%s&zipname=%s' % (
                    [rec.translation_file_line.ids], rec.name)
                return {
                    'type': 'ir.actions.act_url',
                    'url': url,
                    'target': 'new',
                }
            else:
                raise UserError(_('No Translation files are available.'))

    @api.multi
    def download_all_reference_files(self):
        """
        Use for download all translation file with help of controller.
        :return: Download file url.
        """
        for rec in self:
            if rec.refrence_file_line:
                # zipname = 'Translation Files'
                url = '/web/binary/download_document?tab_id=%s&zipname=%s' % (
                    [rec.refrence_file_line.ids], rec.name)
                return {
                    'type': 'ir.actions.act_url',
                    'url': url,
                    'target': 'new',
                }
            else:
                raise UserError(_('No Refrence files are available.'))

    @api.multi
    def download_all_front_end_files(self):
        """
        Use for download all front-end file from assigment with help of
        controller.
        :return: Download file url.
        """
        for rec in self:
            if rec.translation_file_line:
                zipname = 'Translation Files'
                url = '/web/binary/download_document?tab_id=%s&zipname=%s' % (
                    [rec.translation_file_line.ids], zipname)
                return {
                    'type': 'ir.actions.act_url',
                    'url': url,
                    'target': 'new',
                }
            else:
                raise UserError(_('No Translation files are available.'))

    @api.multi
    def download_all_completed_files(self):
        """
        Use for download all Completed file with help of controller.
        :return: Download file url.
        """
        for rec in self:
            if rec.parent_asn_completed_file_line:
                zipname = 'Completed Files'
                url = '/web/binary/download_document?tab_id=%s&zipname=%s' % (
                    [rec.parent_asn_completed_file_line.ids], zipname)
                return {
                    'type': 'ir.actions.act_url',
                    'url': url,
                    'target': 'new',
                }
            else:
                raise UserError(_('No Completed files are available.'))

    @api.multi
    def update_download_all_button(self):
        hide_download_button = False
        is_delete_doc_after = self.partner_id.delete_doc_after
        if is_delete_doc_after is True:
            for rec in self.child_asn_line:
                if rec.delivered_on:
                    today = datetime.now()
                    delivery_date_difference = today - rec.delivered_on
                    days = delivery_date_difference.days
                    seconds = delivery_date_difference.seconds
                    total_seconds = (days * 86400) + seconds
                    if total_seconds > 1296000:                      # 15 days = 15 days = 1296000 seconds
                        hide_download_button = True
                        break
        return hide_download_button
    #             today = datetime.now()
    #             delivery_date_difference = today - rec.delivered_on
    #             diffence_in_days = delivery_date_difference.days
    #             if diffence_in_days > 15:
    #                 hide_download_button = True
    #                 break
    # return hide_download_button

    @api.multi
    def process_action(self):
        org = []
        mem_ids = []
        query = ""
        organization = False
        domain = False

        if self.partner_id.new_client:
            # if self.domain_id and self.organization_id:
            #     query = """SELECT distinct mg.mem_id
            #                FROM memid_domain_rel as md
            #                LEFT JOIN membership_org_rel as mg
            #                ON md.memid = mg.mem_id
            #                WHERE
            #             """
            #     query += "(md.domain_id = " + str(self.domain_id.id) +\
            #                 " AND mg.org_id = " + str(self.organization_id.id)+")"\
            #              " OR md.domain_id = " + str(self.domain_id.id)

            if self.domain_id:
                query = """SELECT distinct md.memid 
                           FROM memid_domain_rel as md
                           WHERE 
                        """
                query += "md.domain_id = " + str(self.domain_id.id)
            elif self.organization_id:
                query = """SELECT distinct mg.mem_id 
                           FROM membership_org_rel as mg
                           WHERE 
                        """
                query += "mg.org_id = " + str(self.organization_id.id)
            else:
                # permanent_memid = self.partner_id.membership_id[1:]
                # membership_id = self.env['membership.master'].create({
                #     'name': permanent_memid,
                #     'client_id': self.partner_id.id})
                # organization_line = [(0, 0, 
                #     {'membership_id': membership_id,
                #     'is_active': True})]
                # self.partner_id.update({
                #                     'active_memid': membership_id.id,
                #                     'membership_id': membership_id.name,
                #                     'new_client': False,
                #                     'organization_line': organization_line
                #                     })
                return self.process()
            mem_obj = False
            if query:
                self._cr.execute(query)
                mem_id = [mem_id[0] for mem_id in self._cr.fetchall()]
                if mem_id:
                    mem_obj = self.env['membership.master'].browse(mem_id)
                    message = "Map client to MEMID or not?"
                else:
                    if self.domain_id and self.organization_id:
                        domain_mem_id = ''
                        org_mem_id = ''
                        if self.domain_id:
                            query = """SELECT distinct md.memid 
                                       FROM memid_domain_rel as md
                                       WHERE 
                                    """
                            query += "md.domain_id = " + str(self.domain_id.id)
                            self._cr.execute(query)
                            domain_mem_id = self._cr.fetchone()
                        if self.organization_id and not domain_mem_id:
                            query = """SELECT distinct mg.mem_id 
                                       FROM membership_org_rel as mg
                                       WHERE 
                                    """
                            query += "mg.org_id = " + str(self.organization_id.id)
                            self._cr.execute(query)
                            org_mem_id = self._cr.fetchone()
                        if domain_mem_id:
                            mem_obj = self.env['membership.master'].browse(domain_mem_id[0])
                            message = "Map client to MEMID or not"
                            domain = True
                        elif org_mem_id:
                            mem_obj = self.env['membership.master'].browse(org_mem_id[0])
                            message = "Map client to MEMID or not"
                            organization = True
                    else:
                        # permanent_memid = self.partner_id.membership_id[1:]
                        # membership_id = self.env['membership.master'].create({
                        #     'name': permanent_memid,
                        #     'client_id': self.partner_id.id})
                        # organization_line = [(0, 0, 
                        #     {'membership_id': membership_id.id,
                        #     'is_active': True})]
                        # self.partner_id.update({
                        #             'active_memid': membership_id.id,
                        #             'membership_id': membership_id.name,
                        #             'new_client': False,
                        #             'organization_line': organization_line
                        #             })
                        return self.process()

            ctx = self._context.copy()
            if message:
                ctx.update({'default_message': message,
                            'membership_id': mem_obj.ids,
                            'default_mem_id': mem_obj.id if len(
                                mem_obj) == 1 else False,
                            'domain': domain,
                            'organization': organization})

            model = 'confirmation.message'
            view_id = self.env.ref(
                'ulatus_cs.inq_confirmation_wizard').id
            return {'name': ('Process'),
                    'type': 'ir.actions.act_window',
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': model,
                    'view_id': view_id,
                    'target': 'new',
                    'context': ctx
                    }
        else:
            return self.process()

    @api.multi
    def process(self):
        """
            To process the inquiry - if languages are not supported by Memsource then open wizard with message else
            create project in the Memsource and create the quotation
            :return: wizard action if languages are not supported by Memsource else url action to open quotation
                     in draft quotation view
        """
        response_data = self.create_project()
        if response_data.get('return_type') == 'wiz_action':
            return response_data.get('return_data')
        elif response_data.get('return_type') == 'memsource_project_id':
            url_action = self.process_operation()
            memsource_project_id = response_data.get('return_data')
            quotation_id = self.env['sale.order'].search([('name', '=', self.name), ('type', '=', 'quotation'),
                                                          ('has_revision', '=', False)])
            if quotation_id:
                quotation_id.update({
                    'mem_project_id': memsource_project_id.project_uid,
                    'memsource_project_id': memsource_project_id.id,
                    'process_type': 'memsource'
                })
                memsource_project_id.update({'quotation_id': quotation_id.id})
                self.update({'process_type': 'memsource'})
                return url_action

    @api.multi
    def process_operation(self):
        """
        Use for create a new quotation.
        :return: Quotation.
        """

        # Check Client Preferences
        if self.partner_id.parent_id:
            # PO Requirement Check
            if self.partner_id.parent_id.po_required is True:
                self.update({'po_required': True})
            else:
                self.update({'po_required': False})

            # Monthly Invoice Check - To be enabled for next Go-Live
            if self.partner_id.parent_id.send_inv_monthly is True:
                self.update({'advance_payment': '0',
                             'advance_payment_value': 0,
                             'send_inv_monthly': True})
            else:
                self.update({'advance_payment': '100',
                             'advance_payment_value': 100})

        else:
            # PO Requirement Check
            if self.partner_id.po_required is True:
                self.update({'po_required': True})
            else:
                self.update({'po_required': False})

            # Monthly Invoice Check - To be enabled for next Go-Live
            if self.partner_id.send_inv_monthly is True:
                self.update({'advance_payment': '0',
                             'advance_payment_value': 0,
                             'send_inv_monthly': True})
            else:
                self.update({'advance_payment': '100',
                             'advance_payment_value': 100})

        if not self.source_lang_id.unit_id:
            raise ValidationError(_(
                'Please contact CS Admin for configure Unit on Language %s!'
                % self.source_lang_id.name))
        param = self.env['ir.config_parameter']
        url_rec = param.search([('key', '=', 'web.base.url')])
        action_id = self.env.ref('ulatus_cs.action_cs_quotation_order').id
        url = url_rec.value + '/web#action=' + str(
            action_id) + "&model=sale.order" + "&view_type=list"
        ins = []
        self.update({
            'inquiry_state': 'process',
            'write_date': self.create_date,
        })

        self.translation_file_line.write({'line_delete_btn': True})
        self.refrence_file_line.write({'line_delete_btn': True})
        # original_file_line = [(0, 0, {
        #     'name': tra_file_id.datas_fname,
        #     'datas': tra_file_id.datas,
        #     'datas_fname': tra_file_id.datas_fname,
        #     'file_type': tra_file_id.file_type,
        #     }) for tra_file_id in self.translation_file_line]
        # ref_file_line = [(0, 0, {
        #     'name': ref_file_id.datas_fname,
        #     'datas': ref_file_id.datas,
        #     'datas_fname': ref_file_id.datas_fname,
        #     'file_type': ref_file_id.file_type,
        #     'category_type_id':ref_file_id.category_type_id and ref_file_id.category_type_id.id or False
        #     }) for ref_file_id in self.refrence_file_line]

        # To prepare attachment one2many records for sale_order
        order_original_file_line = self.prepare_one2many_records(self.name, 'quotation', self.translation_file_line,
                                                                 'translation_file_line', False)
        order_ref_file_line = self.prepare_one2many_records(self.name, 'quotation', self.refrence_file_line,
                                                            'refrence_file_line', False)

        if self.note:
            ins = [(0, 0, {'name': self.note, 'is_original_ins': True})]

        # To add default instructions in inquiry
        ins_config_ids = self.env['instruction.config'].search([])
        if ins_config_ids:
            default_ins = self.default_instruction()
            ins = ins + default_ins

        # Use for when inquiry create at the time of file revision fron
        # parent ASN
        service_level = []
        if self.service_level_id:
            service_level = [(0, 0, {
                'service_level_id': self.service_level_id.id,
                'visible_to_client': True,
                'is_original_service_level': True})]

        endclient_weightage_record = []
        query = """SELECT id
                   FROM endclient_weightage
                   WHERE """
        if self.end_client_id:
            query += """ end_client_id = %s""" % (self.end_client_id.id)
        else:
            query += " end_client_id is Null"
        if self.mem_id:
            query += """ AND membership_id = %s""" % (self.mem_id.id)
        else:
            query += " AND membership_id is Null"
        query += " LIMIT 1 ;"
        self.env.cr.execute(query)
        values = self.env.cr.fetchall()
        record = [x[0] for x in values]
        browse_vals = self.env['endclient.weightage'].sudo().browse(record)

        if values:
            endclient_weightage_record = [(0, 0, {'percent_type': rec.percent_type_id.id,
                                                  'unit_id': self.source_lang_id.unit_id.id if
                                                  self.source_lang_id.unit_id else False,
                                                  'weighted_percent': rec.percentage})
                                          for rec in browse_vals.endclient_weightage_line]
        else:
            type_rec = self.env['analyse.percent.type'].search([])
            endclient_weightage_record = [(0, 0, {'percent_type': l.id,
                                                  'unit_id': self.source_lang_id.unit_id.id if
                                                  self.source_lang_id.unit_id else False,
                                                  'weighted_percent': l.percentage}) for l in type_rec]

        target_lang_line = []
        for lang in self.target_lang_ids:
            # To prepare attachment one2many records for sale_order_line
            original_file_line = self.prepare_one2many_records(self.name, 'quotation', self.translation_file_line,
                                                               'sale_original_file_line', lang.initial_code)
            ref_file_line = self.prepare_one2many_records(self.name, 'quotation', self.refrence_file_line,
                                                          'reference_assignment_line', lang.initial_code)

            target_lang_line.append((0, 0, {
                'name': self.name + '_' + lang.initial_code,
                'source_lang_id': self.source_lang_id.id,
                'unit_id': self.source_lang_id.unit_id.id if
                self.source_lang_id.unit_id else False,
                'target_lang_id': lang.id,
                'sale_original_file_line': original_file_line,
                'reference_assignment_line': ref_file_line,
                'sale_instruction_line': ins,
                'memsource_line': endclient_weightage_record,
            }))

        # target_lang_line = [(0, 0, {
        #     'name': self.name,
        #     'source_lang_id': self.source_lang_id.id,
        #     'unit_id': self.source_lang_id.unit_id.id if
        #     self.source_lang_id.unit_id else False,
        #     'target_lang_id': lang.id,
        #     'sale_original_file_line': original_file_line,
        #     'reference_assignment_line': ref_file_line,
        #     'sale_instruction_line': ins,
        #
        #     }) for lang in self.target_lang_ids]

        quote_vals = {
            'name': self.name,
            'type': 'quotation',
            'inquiry_state': 'process',
            'source_lang_id': self.source_lang_id.id,
            'unit_id': self.source_lang_id.unit_id.id if
            self.source_lang_id.unit_id else False,
            'sale_bool': True,
            'partner_id': self.partner_id.id,
            'state': 'draft',
            'target_lang_ids': [(6, 0, self.target_lang_ids.ids)],
            'inquiry_date': self.inquiry_date,
            'order_line': target_lang_line,
            'service_level_line': service_level,
            'project_management_cost': self.partner_id.parent_id.project_management_cost if self.partner_id.parent_id
            else self.partner_id.project_management_cost,
            'tax_percent_ids': [(6,0, self.tax_percent_ids.ids)],
            # 'sale_order_addons_line': addons_service_line,
            'inquiry_id': self.id,
            'is_file_revision': self.is_file_revision,
            'translation_file_line': order_original_file_line,
            'refrence_file_line': order_ref_file_line,
            'service_level_id': self.service_level_id and
            self.service_level_id.id or False,
            'currency_id': self.currency_id and self.currency_id.id or False,
            'organization_id': self.organization_id and self.organization_id.id
            or False,
            'end_client_id': self.end_client_id and self.end_client_id.id or
            False,
            'client_deadline': self.client_deadline,
            'parent_id': self.parent_id and self.parent_id.id or False,
            'domain_id': self.domain_id and self.domain_id.id or False,
            'organization_name': self.organization_name,
            'mem_id': self.partner_id.active_memid.id,
            'user_id': self.user_id.id,
            'instruction_line': ins,
            'ip_address': self.ip_address,
            'browser': self.browser,
            'country': self.country,
            'initial_create_inquiry': self.initial_create_inquiry,
            'advance_payment': self.advance_payment,
            'advance_payment_value': self.advance_payment_value,
            'po_required': self.partner_id.parent_id.po_required if self.partner_id.parent_id else
            self.partner_id.po_required,
            'send_inv_monthly': self.send_inv_monthly,
            # 'product_id': weightage_var.product_id.id,
            # 'area_type': weightage_var.area_type,
            # 'subject_industrial_area_level1_id': weightage_var.subject_industrial_area_level1_id.id,
            # 'subject_industrial_area_level2_id': weightage_var.subject_industrial_area_level2_id.id,
            # 'subject_industrial_area_level3_id': weightage_var.subject_industrial_area_level3_id.id,
            # 'level3_other_area_bool': weightage_var.level3_other_area_bool,
            # 'level3_other_area': weightage_var.level3_other_area,
            'product_id': browse_vals.product_id.id,
            'area_type': browse_vals.area_type,
            'subject_industrial_area_level1_id': browse_vals.subject_industrial_area_level1_id.id,
            'subject_industrial_area_level2_id': browse_vals.subject_industrial_area_level2_id.id,
            'subject_industrial_area_level3_id': browse_vals.subject_industrial_area_level3_id.id,
            'level3_other_area_bool': browse_vals.level3_other_area_bool if browse_vals.level3_other_area_bool else False,
            # 'level3_other_area': browse_vals.level3_other_area if browse_vals.level3_other_are else False,
        }
        if self.partner_id.new_client:
            self.partner_id.update({'new_client': False})

        add_translation_level = []
        if self.is_rr_inquiry:
            add_translation_level = [(0, 0, {
                'sale_order_id': self.id,
                'service_level_id': self.service_level_id.id,
                'reccommend': True,
                'visible_to_client': True})]

            quote_vals.update({
                'is_rr_inquiry': self.is_rr_inquiry,
                'parent_asn_ref_id': self.parent_asn_ref_id.id,
                'product_id': self.parent_asn_ref_id.quotation_ref_id.product_id.id,
                'area_type': self.parent_asn_ref_id.quotation_ref_id.area_type,
                'subject_industrial_area_level1_id': self.parent_asn_ref_id.quotation_ref_id.subject_industrial_area_level1_id.id,
                'subject_industrial_area_level2_id': self.parent_asn_ref_id.quotation_ref_id.subject_industrial_area_level2_id.id,
                'subject_industrial_area_level3_id': self.parent_asn_ref_id.quotation_ref_id.subject_industrial_area_level3_id.id,
                'level3_other_area_bool': self.parent_asn_ref_id.quotation_ref_id.level3_other_area_bool if self.parent_asn_ref_id.quotation_ref_id.level3_other_area_bool else False,
                'level3_other_area': self.parent_asn_ref_id.quotation_ref_id.level3_other_area if self.parent_asn_ref_id.quotation_ref_id.level3_other_area else False,
                'add_translation_level_line': add_translation_level,
            })

        # To add default First Project discount if new client and there is not ASN for this client
        asn_query = """SELECT count(id)
                       FROM sale_order
                       WHERE partner_id='%s'
                       AND type = 'asn' 
                    """ % self.partner_id.id
        self.env.cr.execute(asn_query)
        asn_counts = self.env.cr.fetchone()

        # For B2B and LSP clients, existing ASN finding flag - Initially set to False
        asn_exist = False

        # IF Parent org exist, find if any other clients under same org have previous quotes or asn
        if self.partner_id.parent_id:
            other_child_clients = self.env['res.partner'].search([('parent_id', '=', self.partner_id.parent_id.id)])
            for other_child_client in other_child_clients:
                self.env.cr.execute("""SELECT count(id)
                                       FROM sale_order
                                       WHERE partner_id='%s'
                                       AND type = 'asn' 
                                    """ % other_child_client.id)
                other_child_asn = self.env.cr.fetchone()

                self.env.cr.execute("""SELECT count(id)
                                 FROM sale_order
                                 WHERE partner_id='%s'
                                 AND type = 'quotation' 
                                 AND state in ('draft','sent','revision_request','revise')
                                 AND first_project_discount = true
                            """ % other_child_client.id)
                other_child_quote_counts = self.env.cr.fetchone()

                if other_child_asn[0] > 0 or other_child_quote_counts[0] > 0:
                    asn_exist = True
                    break

        # For LSP Clients, check if this is fist asn under current MEM-ID
        if self.partner_id.parent_id and self.partner_id.client_type_id.name == 'LSP':
            same_memid_clients = self.env['res.partner'].search([('active_memid', '=', self.partner_id.active_memid.id)])

            for same_memid_client in same_memid_clients:
                self.env.cr.execute("""SELECT count(id)
                                       FROM sale_order
                                       WHERE partner_id='%s'
                                       AND type = 'asn' 
                                    """ % same_memid_client.id)
                other_client_asn = self.env.cr.fetchone()

                self.env.cr.execute("""SELECT count(id)
                                 FROM sale_order
                                 WHERE partner_id='%s'
                                 AND type = 'quotation' 
                                 AND state in ('draft','sent','revision_request','revise')
                                 AND first_project_discount = true
                            """ % same_memid_client.id)
                other_client_quote_counts = self.env.cr.fetchone()

                if other_client_asn[0] > 0 or other_client_quote_counts[0] > 0:
                    asn_exist = True
                    break

        quote_query = """SELECT count(id)
                         FROM sale_order
                         WHERE partner_id='%s'
                         AND type = 'quotation' 
                         AND state in ('draft','sent','revision_request','revise')
                         AND first_project_discount = true
                    """ % self.partner_id.id
        self.env.cr.execute(quote_query)
        quote_counts = self.env.cr.fetchone()

        if asn_counts[0] == 0 and quote_counts[0] == 0 and asn_exist is False:
            domain_list = [('discount_category', '=', 'first_project_discount'),
                           ('currency_ids', 'in', self.currency_id.id)]
            if self.partner_id.client_type_id:
                domain_list.append(('client_type_ids', 'in', self.partner_id.client_type_id.id))
            else:
                domain_list.append(('client_type_ids', '=', False))
            discount_master_id = self.env['discount.master'].search(domain_list)
            if discount_master_id:
                quote_vals.update({
                    'ks_global_discount_type': discount_master_id.discount_type,
                    'ks_global_discount_rate': discount_master_id.discount_value,
                    'discount_reason': 'First Project Discount',
                    'first_project_discount': True,
                })

        quote_id = self.env['sale.order'].create(quote_vals)

        if self.is_rr_inquiry:
            for line in quote_id.order_line:
                previous_sale_order = quote_id.parent_asn_ref_id.quotation_ref_id.order_line.filtered(
                lambda l: l.target_lang_id.id == line.target_lang_id.id)

                previous_service_level = previous_sale_order.service_level_line.filtered(
                    lambda l: l.service_level_id.id == quote_id.service_level_id.id)

                self.env['service.level.line'].create({
                    'unit_rate': previous_service_level.unit_rate,
                    # 'fee': previous_service_level.fee,
                    'service_level_id': previous_service_level.service_level_id.id,
                    'reccommend': True,
                    'visible_to_client': True,
                    'add_translation_level_id': quote_id.add_translation_level_line[0].id,
                    'sale_service_line_id': line.id,
                })

                # addons_fee_line = []
                # for addons in previous_sale_order.addons_fee_line:
                #     addons_fee_line.append((0, 0, {
                #         'sale_order_line_id': line.id,
                #         'addons_id': addons.addons_id.id,
                #         'no_of_unit': addons.no_of_unit,
                #         'price': addons.price,
                #         'total_price': addons.total_price,
                #         'unit_id': addons.unit_id.id,
                #         'enter_unit_bool': addons.enter_unit_bool
                #     }))
                #
                # line.write({
                #     'addons_fee_line': addons_fee_line
                # })
                #
                # addons_dict = {}
                # for addons in line.addons_fee_line:
                #     addons_id = addons.addons_id.id
                #     unit_id = addons.unit_id.id
                #     adoons_key = str(addons_id) + '_' + str(unit_id)
                #     if adoons_key not in addons_dict.keys():
                #         addons_dict.update({
                #             adoons_key: (0, 0, {
                #                 'unit': addons.no_of_unit,
                #                 'rate': addons.price,
                #                 'addons_price': addons.total_price,
                #                 'addons_service_id': addons_id,
                #                 'unit_id': unit_id,
                #             })
                #         })
                #     else:
                #         addons_dict[adoons_key][2]['unit'] += addons.no_of_unit
                #         addons_dict[adoons_key][2]['rate'] += addons.price
                #         addons_dict[adoons_key][2]['addons_price'] += addons.total_price
                #
                # line.order_id.write({
                #     'sale_order_addons_line': list(addons_dict.values())
                # })

        return {'name': ' ',
                'res_model': 'ir.actions.act_url',
                'type': 'ir.actions.act_url',
                'target': 'self',
                'url': url,
                }

    @api.multi
    def default_instruction(self):
        """
            Get default instructions which will be add in inquiry
            :return: ins : instructions list
        """
        ins = []
        # 1. Without client type, memID, end client
        only_ins_query = """SELECT name
                             FROM instruction_config
                             WHERE client_type_id IS NULL   
                             AND membership_id IS NULL
                             AND end_client_id IS NULL
                         """
        self.env.cr.execute(only_ins_query)
        only_ins = self.env.cr.fetchall()
        if only_ins:
            for inst in only_ins:
                ins.append((0, 0, {'name': inst[0], 'is_default_ins': True}))

        # 2. Check all cases
        ct_query, ec_query, memid_query = '', '', ''
        if self.partner_id.client_type_id:
            ct_query = '=' + str(self.partner_id.client_type_id.id)
        else:
            ct_query = 'IS NULL'

        if self.end_client_id:
            ec_query = '=' + str(self.end_client_id.id)
        else:
            ec_query = 'IS NULL'

        if self.partner_id.active_memid:
            memid_query = '=' + str(self.partner_id.active_memid.id)
        else:
            memid_query = 'IS NULL'

        match_ins_query = """SELECT name
                             FROM instruction_config
                             WHERE client_type_id %s
                             AND end_client_id %s
                             AND membership_id %s""" % (ct_query, ec_query, memid_query)
        self.env.cr.execute(match_ins_query)
        match_ins = self.env.cr.fetchall()
        if match_ins:
            for inst in match_ins:
                ins.append((0, 0, {'name': inst[0], 'is_default_ins': True}))
        return ins

    def value_format(self, currency_id, value, is_amount):
        """
            Format value and amount
            :param currency_id: to check currency and get symbol when value is amount
            :param value: value which need to format
            :param is_amount: to check value is amount or not
            :return: formatted value
        """
        value_format = ''
        # For amount
        if currency_id and is_amount:
            if currency_id.name == 'USD':
                value_format = currency_id.symbol + '{:,.2f}'.format(float(value))
            elif currency_id.name == 'INR':
                value_format = currency_id.symbol + ' ' + '{:,}'.format(round(float(value)))
            elif currency_id.name == 'EUR':
                if type(value) is int:
                    value = float_round(float(value),2)
                val_tuple = str(value).split('.')
                after_decimal_no = round(float('0.' + val_tuple[1]), 2)
                value_format = currency_id.symbol + '{:,}'.format(int(val_tuple[0])).replace(',', '.') + ',' + str(after_decimal_no).split('.')[1]
            else:
                if currency_id.position == 'before':
                    value_format = currency_id.symbol + ' ' + '{:,.2f}'.format(float(value))
                elif currency_id.position == 'after':
                    value_format = '{:,.2f}'.format(float(value)) + ' ' + currency_id.symbol
        # For other values like unit_count, etc.
        elif currency_id and not is_amount:
            if type(value) is str:
                split_value = value.split('.')
                if len(split_value) == 1:
                    value = int(value)
                elif len(split_value) == 2:
                    value = float(value)
            if currency_id.name == 'USD' or currency_id.name == 'INR':
                if type(value) is float:
                    value_format = '{:,.2f}'.format(float(value))
                elif type(value) is int:
                    value_format = '{:,}'.format(int(value))
            elif currency_id.name == 'EUR':
                if type(value) is float:
                    val_tuple = str(value).split('.')
                    after_decimal_no = round(float('0.' + val_tuple[1]), 2)
                    value_format = '{:,}'.format(int(val_tuple[0])).replace(',', '.') + ',' + str(after_decimal_no).split('.')[1]
                elif type(value) is int:
                    value_format = '{:,}'.format(int(value)).replace(',', '.')
            else:
                value_format = '{:,.2f}'.format(float(value))
        return value_format

    # Use for client portal user time zone change
    def convert_to_user_timezone(self, datetime):
        """
        Convert datetme into user timezone to print in report.
        :param datetime:
        :return:
        """
        if not datetime:
            return True
        tz = self.partner_id.tz
        if tz:
            date_order = fields.Datetime.from_string(datetime)
            today_utc = pytz.UTC.localize(date_order)
            date_order = today_utc.astimezone(pytz.timezone(tz))
            # date_order = fields.Datetime.to_string(date_order)
            return date_order
        return datetime

    # Use for client portal user time zone change
    def dashboard_convert_to_user_timezone(self, datetime):
        """
        Convert datetme into user timezone to print in report.
        :param datetime:
        :return:
        """
        if not datetime:
            return True
        tz = self.env.user.tz
        if tz:
            date_order = fields.Datetime.from_string(datetime)
            today_utc = pytz.UTC.localize(date_order)
            date_order = today_utc.astimezone(pytz.timezone(tz))
            # date_order = fields.Datetime.to_string(date_order)
            return date_order
        return datetime

    @api.model
    def fields_view_get(self, view_id=None, view_type='tree', toolbar=False,
                        submenu=False):
        toolbar = False
        return super(SaleOrder, self).fields_view_get(view_id=view_id,
                                                      view_type=view_type,
                                                      toolbar=toolbar,
                                                      submenu=submenu)

    # @api.onchange('mark_as_special')
    # def onchange_mark_as_special(self):
    #     if not self.mark_as_special:
    #         self.additional_comments = False
    #         self.checklist_line = [(6, 0, [])]

    @api.multi
    def action_cancel(self):
        ctx = self._context.copy()
        reason_type = False
        title = False
        if self.type == 'inquiry' or self.type == 'quotation':
            reason_type = 'inquiry'
            message = 'Do you want to Reject this Inquiry..?'
        else:
            reason_type = 'asn'
            message = 'Do you want to Reject this Assignment..?'
        ctx.update({'default_parent_asn_id': self.id,
                    'reason_type': reason_type,
                    'message': message})
        model = 'file.revision.request.wiz'
        view_id = self.env.ref('ulatus_cs.view_cancel_quotation_message').id
        return {
            'name': 'Cancel Request',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    # Open checklist wizard in Quotation/Revise Quotation
    @api.multi
    def quotation_send_to_client(self):
        if self.additional_comments:
            self.additional_comments = False
        service_level_line = self.order_line.mapped(
            'service_level_line').filtered(lambda line: line.visible_to_client)
        deadline = service_level_line.mapped('deadline')
        addons_services = self.mapped('sale_order_addons_line.show_option')
        if not service_level_line:
            raise ValidationError(
                _("Please Load Translation Level for this Quotation!"))
        if False in deadline:
            raise ValidationError(
                _("Please enter missing deadline for Translation Level!"))
        sale_instruction_line = self.order_line.mapped('sale_instruction_line').filtered(lambda service :service.mark_reviewed ==False)
        if sale_instruction_line:
            raise ValidationError(_("Please check the instructions and select accordingly before Sending Quotation!"))
        if not self.deadline:
            raise ValidationError(
                _("Please enter deadline for this Quotation!"))
        if False in addons_services:
            raise ValidationError(
                _("Please enter Add-ons Services show option!"))
        ctx = self._context.copy()
        if self.checklist_line:
            self.checklist_line.unlink()
        if not self.checklist_line:
            self.update({'checklist_line':
                         [(0, 0, {'checklist_id': checklist.id})
                          for checklist in self.env['checklist'].search(
                          [('type', '=', 'Quotation')])]})
        view_id = self.env.ref('ulatus_cs.quotation_checklist_view').id
        return {
            'name': 'Checklist',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'sale.order',
            'res_id': self.id,
            'view_id': view_id,
            'target': 'new',
            'context': ctx
        }

    # Configure currency for inquiry and quotation
    @api.multi
    def change_currency(self):
        ctx = self._context.copy()
        model = 'file.revision.request.wiz'
        ctx.update({'default_parent_asn_id': self.id,
                    'default_so_currency_id': self.currency_id.id})
        view_id = self.env.ref('ulatus_cs.view_change_currency_wiz').id
        return {
            'name': ('Configure Currency'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    # Configure currency for inquiry and quotation
    @api.multi
    def change_organization(self):
        ctx = self._context.copy()
        model = 'file.revision.request.wiz'
        ctx.update({'default_parent_asn_id': self.id,
                    'default_so_currency_id': self.currency_id.id,
                    'default_partner_id':self.partner_id.id})
        view_id = self.env.ref('ulatus_cs.view_change_organization_wiz').id
        return {
            'name': 'Configure Organization',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    # Send reminder for Pending Quotation
    @api.multi
    def send_reminder(self):
        diff = False
        hour = 0
        if self.send_reminder_datetime:
            now = datetime.now()
            diff = now - self.send_reminder_datetime
        if diff:
            minutes = diff.total_seconds() / 60
            if minutes > 60:
                self.write({'is_reminder_sent': 0})
        message = 'Reminders Sent : ' + str(self.send_reminder_count)
        if self.is_reminder_sent == 1:
            send_reminder_datetime = self.dashboard_convert_to_user_timezone(self.send_reminder_datetime).strftime('%b %d, %Y, %H:%M:%S')
            title = 'Last reminder was sent on ' + str(send_reminder_datetime) + ' (' + self.env.user.tz_abbreviation + ')'
        elif self.send_reminder_count == 0:
            title = 'Do you want to send a reminder?'
        else:
            title = 'Do you want to send another reminder?'
        ctx = self._context.copy()
        model = 'confirmation.message'
        ctx.update({
            'default_message': message,
            'default_send_reminder': True,
            'send_reminder_count': self.send_reminder_count,
            'is_reminder_sent': self.is_reminder_sent,
        })
        view_id = self.env.ref(
            'ulatus_cs.sent_confirmation_message_form_view').id
        return {'name': title,
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': model,
                'view_id': view_id,
                'target': 'new',
                'context': ctx
                }

    # Send revision request from Pending Quotation
    @api.multi
    def quotation_send_for_revision(self):
        ctx = self._context.copy()
        model = 'file.revision.request.wiz'
        ctx.update({'default_parent_asn_id': self.id})
        view_id = self.env.ref(
            'ulatus_cs.quotation_revision_reason_wiz_form_view').id
        return {
            'name': 'Quotation Revision request',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    # Send quotation to client dashboard from quotation inherited.
    @api.multi
    def action_quotation_send(self):
        """
        This function opens a window to compose an email, with the edi sale
        template message loaded by default
        And change template id.
        """
        param = self.env['ir.config_parameter']
        base_url = param.sudo().get_param('web.base.url')
        delivery_url = base_url + "/page/quotations_details/%s" % self.id
        self.ensure_one()
        ir_model_data = self.env['ir.model.data']
        no_checklist = self.checklist_line.filtered(lambda l: not l.option)
        if no_checklist:
            raise ValidationError(_("Please fill all the checklist options!"))
        # try:
            # if self.state == 'draft':
            #     template_id = ir_model_data.get_object_reference(
            #         'dynamic_mail', 'mail_template_quotation_confirmation')[1]
            # elif self.state == 'revision_request':
            #     template_id = ir_model_data.get_object_reference(
            #         'dynamic_mail', 'mail_template_send_revise_quotation')[1]
        # except ValueError:
        #     template_id = False

        # To reset pending since value on quotation
        self.write({'initial_create_inquiry': datetime.now()})
        # To reset pending since value on inquiry which is linked with quotation
        self.inquiry_id.write({'initial_create_inquiry': False})

        # If send email to client is true in client preference then only send email to them
        if not self.partner_id.send_email_to_client:
            return self.send_mail_operation()
        else:
            try:
                compose_form_id = ir_model_data.get_object_reference('mail', 'email_compose_message_wizard_form')[1]
            except ValueError:
                compose_form_id = False
            lang = self.env.context.get('lang')
            temp_config_id = self.env['mail.template.config'].search([('active', '=', True)])
            template_id = self.env['mail.template'].search(
                [('mail_template_config_id', '=', temp_config_id.id), ('is_configured_template', '=', True),
                 ('template_type_id', '=', self.env.ref("dynamic_mail.quote_temp").id),
                 ('quote_type', '=', 'quote_send')])
            if not template_id:
                raise ValidationError("Template not found!! Please configure email template "
                                      "in Configure Mail Templates master to proceed.")
            # template = template_id and self.env['mail.template'].browse(template_id)
            if template_id and template_id.lang:
                lang = template_id._render_template(template_id.lang, 'sale.order', self.ids[0])
            mail_trigger_obj = self.env['mail.trigger']
            if template_id:
                # To get outgoing mail server id
                mail_server_id = mail_trigger_obj.get_mail_server_id(template_id)
                template_id.sudo().write({'mail_server_id': mail_server_id.id if mail_server_id else False})
            target_lang = self.env['mail.trigger'].get_target_lang(self.target_lang_ids)
            ctx = mail_trigger_obj.get_email_ids()
            ctx.update({
                'default_model': 'sale.order',
                'default_res_id': self.ids[0],
                'default_use_template': bool(template_id.id),
                'default_template_id': template_id.id,
                'delivery_url': delivery_url,
                'target_lang': target_lang,
                'default_composition_mode': 'comment',
                'model_description': self.with_context(lang=lang).type_name,
                'force_email': True,
                'custom_mail': True
            })
            return {
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'mail.compose.message',
                'views': [(compose_form_id, 'form')],
                'view_id': compose_form_id,
                'target': 'new',
                'context': ctx,
            }

    # Quotation revision Request assign to me
    @api.multi
    def assign_to_me(self):
        dict = {'user_id': self.env.user.id}
        if self.state == 'draft':
            dict.update({
                'inquiry_state': 'assign',
                'pending_notification_sent': True,
            })
            action_id = self.env.ref('ulatus_cs.action_client_my_inquiry').id

        elif self.state == 'revision_request':
            # For access rights : make inquiry and revision history visible to current working user
            # 1. inquiry form
            revise_dict = {}
            inquiry_id = self.env['sale.order'].sudo().browse(self.inquiry_id.id)
            if not inquiry_id.r_user_id:
                revise_dict.update({'r_user_id': inquiry_id.user_id.id})
            revise_dict.update({'user_id': self.env.user.id})
            self.inquiry_id.sudo().write(revise_dict)
            # 2. revision history
            query = """SELECT id
                       FROM sale_order
                       WHERE main_quotation_id = %s
                    """ % str(self.id)
            self.env.cr.execute(query)
            revise_inq_ids = self.env.cr.fetchall()
            revise_inq_ids = revise_inq_ids and [x[0] for x in revise_inq_ids] or []
            revise_ids = self.env['sale.order'].sudo().browse(revise_inq_ids)
            for revise_id in revise_ids:
                revise_his_dict = {}
                if not revise_id.r_user_id:
                    revise_his_dict.update({'r_user_id': revise_id.user_id.id})
                revise_his_dict.update({'user_id': self.env.user.id})
                revise_id.sudo().write(revise_his_dict)

            dict.update({'inquiry_state': 'process'})
            action_id = self.env.ref(
                'ulatus_cs.action_cs_quotation_revision').id
        param = self.env['ir.config_parameter']
        url_rec = param.search([('key', '=', 'web.base.url')])
        url = url_rec.value + '/web#action=' + \
            str(action_id) + "&model=sale.order" + "&view_type=list"
        self.update(dict)
        return {'name': ' ',
                'res_model': 'ir.actions.act_url',
                'type': 'ir.actions.act_url',
                'target': 'self',
                'url': url,
                }

    # Quotation revision Request assign to others
    @api.multi
    def assign_to_others(self):
        ctx = self._context.copy()
        model = 'assign.others.wiz'
        view_id = self.env.ref('ulatus_cs.assign_to_others_wiz_form_view').id
        return {
            'name': ('Assign To'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'target': 'new',
            'context': ctx,
        }

    # Function for sending inquiry details mail to CS
    @api.multi
    def inquiry_details_mail_to_cs(self, **kw):
        latest_inquiry = self.env['sale.order'].search([], limit=1, order='create_date desc')
        # subject = False
        # email_from = False
        if latest_inquiry:
            self.env['mail.trigger'].inquiry_mail(latest_inquiry, 'inq_notification')
            self.env['mail.trigger'].inquiry_mail(latest_inquiry, 'inq_notification_to_client')
            # existing_user = self.env['res.partner'].sudo().search(
            #     [('email', '=', kw.get('email-address'))])
            #
            # if existing_user:
            #     subject = latest_inquiry.name + '|'
            #     email_from = self.partner_id.email
            # else:
            #     subject = latest_inquiry.name + '|'
            #     email_from = kw.get('email-address')
            #
            # if len(latest_inquiry.target_lang_ids) > 1:
            #     target_lang = ', '.join([lang.name for lang in latest_inquiry.target_lang_ids])
            # else:
            #     target_lang = latest_inquiry.target_lang_ids[0].name
            # subject += latest_inquiry.source_lang_id.name + '|' + target_lang + '|' + str(latest_inquiry.client_deadline)

            # cs_email_id = self.env['ulatus.config.settings'].search([])[-1].cs_email_id

            # mail_template = self.env.ref('dynamic_mail.mail_template_inquiry_details_mail_to_cs')
            # if mail_template:
            #     try:
            #         mail_template.sudo().with_context(subject=subject,target_lang=target_lang,email_from=email_from,cs_email_id=cs_email_id).send_mail(self.id, force_send=True, raise_exception=True)
            #     except Exception:
            #         raise ValidationError(_('Please contact your Admin for Configure your system outging mail server!'))

    @api.multi
    def action_fine_uploader_revise_ref_file(self):
        """
            To open Fine uploader wizard for revise reference files
            :return: Fine uploader wizard action
        """
        context = self.env.context.copy()
        context.update({
            'default_active_id': self.id,
            'default_active_model': 'sale.order',
            'default_field_name': 'client_query_line',
            'default_so_type': 'asn',
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
    def action_fine_uploader_file_revision(self):
        """
            To open Fine uploader wizard for file revision
            :return: Fine uploader wizard action
        """
        context = self.env.context.copy()
        context.update({
            'default_active_id': False,
            'default_active_model': 'sale.order',
            'default_field_name': 'translation_file_line',
            'default_so_type': 'inquiry',
            'default_file_type': 'client',
            'default_file_uploader_no': self.env['file.uploader.wizard'].generate_seq_no(),
            'default_file_revision_backend': 'True',
            'file_revision': True,
        })
        view_id = self.env.ref('fine_uploader.view_file_uploader_wizard').id
        return {
            'name': 'Request For File Revision',
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

    @api.multi
    def open_inquiry_readonly(self):
        """
            To open inquiry readonly view
            :return: Inquiry action
        """
        action = self.env.ref('ulatus_cs.action_client_inquiry_readonly').read()[0]
        form_view = [(self.env.ref('ulatus_cs.client_reject_inquiry_form_view').id, 'form')]
        action['views'] = form_view
        action['res_id'] = self.inquiry_id.id
        return action

    @api.multi
    def open_quotation_readonly(self):
        """
            To open quotation readonly view
            :return: Quotation action
        """
        action = self.env.ref('ulatus_cs.action_pending_quotation_order_form_readonly').read()[0]
        form_view = [(self.env.ref('ulatus_cs.pending_quotation_order_form_view').id, 'form')]
        action['views'] = form_view
        action['res_id'] = self.quotation_ref_id.id
        return action

    # # For Sending ASN to PM Team
    # @api.multi
    # def send_asn_to_pm_team(self):
    #     """
    #     Use for create child assignment from parent assignment.
    #     :return: Child Assignment.
    #     """
    #     param = self.env['ir.config_parameter']
    #     url_rec = param.search([('key', '=', 'web.base.url')])
    #     action_id = self.env.ref('ulatus_cs.action_my_assignment_order').id
    #     url = url_rec.value + '/web#action=' + \
    #         str(action_id) + "&model=sale.order" + "&view_type=list"
    #     original_file_line = []
    #     ref_file_line = []
    #     ins_line = []
    #     self.update({'state': 'asn_work_in_progress'})
    #     if self.original_file_line:
    #         for tra_file_id in self.original_file_line.search(
    #                 [('file_type', '=', 'client'),
    #                  ('parent_asn_id', '=', self.id)]):
    #             original_file_line.append((0, 0, {
    #                 'name': tra_file_id.datas_fname,
    #                 'datas': tra_file_id.datas,
    #                 'datas_fname': tra_file_id.datas_fname,
    #                 'file_type': tra_file_id.file_type,
    #             }))
    #     if self.refrence_file_line:
    #         for ref_file_id in self.refrence_file_line.search(
    #                 [('file_type', '=', 'refrence'),
    #                  ('parent_asn_id', '=', self.id)]):
    #             ref_file_line.append((0, 0, {
    #                 'name': ref_file_id.datas_fname,
    #                 'datas': ref_file_id.datas,
    #                 'datas_fname': ref_file_id.datas_fname,
    #                 'file_type': ref_file_id.file_type,
    #             }))
    #     if self.parent_asn_ins_line:
    #         for asn_ins in self.parent_asn_ins_line:
    #             ins_line.append((0, 0, {
    #                 'name': asn_ins.name,
    #             }))
    #     for quote_id in self.target_lang_ids:
    #         self.env['assignment'].create({
    #             'name': self.name + '-' + str(quote_id.initial_code),
    #             'source_lang_id': self.source_lang_id.id,
    #             'service_level_id': self.service_level_id.id,
    #             'deadline': self.deadline,
    #             'character_count': self.char_count,
    #             'partner_id': self.partner_id.id,
    #             'quotation_id': self.quotation_ref_id.id,
    #             'parent_asn_id': self.id,
    #             'state': 'new',
    #             'target_lang_id': quote_id.id,
    #             'assignment_instruction_line': ins_line,
    #             'assignment_original_file_line': original_file_line,
    #             'asn_reference_line': ref_file_line,
    #         })
    #     return {'name': ' ',
    #             'res_model': 'ir.actions.act_url',
    #             'type': 'ir.actions.act_url',
    #             'target': 'self',
    #             'url': url,
    #             }

    _sql_constraints = [('asn_unique_quote_ref', 'unique (quotation_ref_id,type)', 'Assignment already Exist !')]

    # Invoice generation on confirmation of sale order
    # Create invoice - Core function inherited #
    @api.multi
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
        company_id = self.company_id.id
        journal_id = (self.env['account.invoice'].with_context(
            company_id=company_id or self.env.user.company_id.id).default_get(
            ['journal_id'])['journal_id'])
        if not journal_id:
            raise UserError(_('Please define an accounting sales journal for this company.'))

        sale_line_obj = self.env['sale.order.line']
        current_sale_line = self.env['sale.order.line'].search([('order_id', '=', self.id)])
        if self.deadline and self.confirmation_date:
            adv_payment_time_delta = (self.deadline - self.confirmation_date)/10
        else:
            adv_payment_time_delta = (self.deadline - self.today())/10

        invoice_vals = {
            'name': self.client_order_ref or '',
            'origin': self.name,
            'type': 'out_invoice',
            'inv_type': 'ind' if (self.partner_invoice_id.send_inv_monthly is False) else 'mon',
            'po_number': self.quotation_ref_id.po_number,
            'date_invoice': date.today(),
            'date_due': date.today() + timedelta(days=60) if self.advance_payment == '0'
                        else date.today() + adv_payment_time_delta,
            'deadline': self.deadline,
            'priority': self.priority,
            'account_id': self.partner_invoice_id.property_account_receivable_id.id,
            'partner_id': self.partner_invoice_id.id,
            'payer_name': self.partner_invoice_id.name,
            'portal_street': self.partner_invoice_id.street,
            'portal_street2': self.partner_invoice_id.street2,
            'portal_city': self.partner_invoice_id.city,
            'portal_zip': self.partner_invoice_id.zip,
            'portal_state_id': self.partner_invoice_id.state_id.id,
            'portal_country_id': self.partner_invoice_id.country_id.id,
            'portal_phone': self.partner_invoice_id.phone,
            'portal_mobile': self.partner_invoice_id.mobile,
            'partner_shipping_id': self.partner_shipping_id.id,
            'journal_id': journal_id,
            'currency_id': self.currency_id.id,
            'comment': self.note,
            'payment_term_id': self.payment_term_id.id,
            'fiscal_position_id': self.fiscal_position_id.id or self.partner_invoice_id.property_account_position_id.id,
            'company_id': company_id,
            'user_id': self.user_id and self.user_id.id,
            'team_id': self.team_id.id,
            'product_id': self.product_id.id,
            'service': self.service_level_id.name,
            'transaction_ids': [(6, 0, self.transaction_ids.ids)],
            'advance_payment': self.advance_payment,
            'char_count': self.char_count,
            'advance_payment_value': self.advance_payment_value,
            'advance_payment_amount': self.advance_payment_amount,
            'advance_pending_amount': self.advance_pending_amount,
            'sale_order_id': self.id,
            'add_premium_rate': self.add_premium_rate,
            'add_premium_type': self.add_premium_type,
            'amount_total': self.amount_total,
            # 'invoice_line_ids': [(6, 0, sale_line.id)]
        }

        print(invoice_vals)
        order_line = self.env['sale.order.line']
        # order_line._prepare_invoice_line()
        res_obj = self.env['res.partner'].search(
            [('id', '=', self.partner_invoice_id.id), ('send_inv_monthly', '=', False)])
        if self.send_inv_monthly is False:
            # mail_content = "  Hello  " + str(
            #     res_obj.name) + ",<br> Invoice has been created against your the inquiry " \
            #                + str(self.origin) + "."
            # main_content = {
            #     'subject': _('Invoice Generated Against SO - %s') % self.origin,
            #     'author_id': self.env.user.partner_id.id,
            #     'body_html': mail_content,
            #     'email_to': self.partner_invoice_id.email,
            # }
            inv_created = self.env['account.invoice'].create(invoice_vals)
            for sale_line in current_sale_line:
                invoice_line_vals = {
                    'unit_id': self.unit_id,
                    'invoice_line_ids': [(0, 0, {
                        'name': sale_line.product_id.name,
                        'origin': sale_line.name,
                        'account_id': 31,
                        'price_unit': sale_line.price_unit,
                        'quantity': sale_line.product_uom_qty,
                        'discount': 0.0,
                        'uom_id': sale_line.product_id.uom_id.id,
                        'product_id': sale_line.product_id.id,
                        'invoice_line_tax_ids': [(6, 0, self.tax_percent_ids.ids)],
                    })],
                }

                self.env['account.invoice'].search([('id', '=', inv_created.id)]).update(invoice_line_vals)

            # Update if any Universal discount is added in Quotation
            if self.ks_amount_discount > 0:
                invoice_line_values = {
                    'invoice_line_ids': [(0, 0, {
                        'name': 'Quote level Discount',
                        'origin': self.origin,
                        'account_id': 31,
                        'price_unit': -self.ks_amount_discount,
                        'quantity': 1,
                        'uom_id': 1,
                        'invoice_line_tax_ids': [(6, 0, self.tax_percent_ids.ids)]
                    })],
                }
                self.env['account.invoice'].search([('id', '=', inv_created.id)]).update(invoice_line_values)

            # Update if any premium amount is added in Quotation
            if self.premium_amount > 0:
                invoice_line_values = {
                    'invoice_line_ids': [(0, 0, {
                        'name': 'Quote level Premium Addition',
                        'origin': self.origin,
                        'account_id': 31,
                        'price_unit': self.premium_amount,
                        'quantity': 1,
                        'uom_id': 1,
                        'invoice_line_tax_ids': [(6, 0, self.tax_percent_ids.ids)]
                    })],
                }
                self.env['account.invoice'].search([('id', '=', inv_created.id)]).update(invoice_line_values)

            # Compute Tax values
            inv_created.compute_taxes()

            # Validate Invoice if Invoice Type is individual
            if self.partner_invoice_id.send_inv_monthly is False:
                inv_created.action_invoice_open()
                inv_created.update({'payment_state': 'open'})

            # Update Origin Value
            if self.is_rr_inquiry is False:
                value = {'origin': self.name}
            else:
                value = {'origin': self.env['assignment'].search([('quotation_id', '=', self.id)]).name}
            self.env['account.invoice'].search([('id', '=', inv_created.id)]).update(value)

            # Update Service for Invoice report
            # service_ids = self.order_line.service_level_line
            # for service_rec in service_ids:
            #     print('Service Record*******************', service_rec)
            #     if service_rec.reccommend is True:
            #         service_value = {'service': service_rec.service_level_id.name}
            #         self.env['account.invoice'].search([('id', '=', inv_created.id)]).update(service_value)

            # Update Invoice Sequence
            if self.partner_id.send_inv_monthly is False:
                # if inv_created.origin:
                #     sequence_values = {
                #         'number': inv_created.origin + '-' + self.env['ir.sequence'].next_by_code(
                #             'seq.individual.invoice'),
                #     }
                # else:
                sequence_values = {
                    'number': self.env['ir.sequence'].next_by_code('seq.individual.invoice'),
                }

            else:
                if self.partner_id.active_memid:
                    sequence_values = {
                        'number': self.self.partner_id.active_memid.name + '-' + self.env['ir.sequence'].next_by_code(
                            'seq.monthly.invoice'),
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

            # Create transaction history record after ASN invoice generated
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

                bi_report = self.env['bi.daily.report'].search([('quote_id', '=', self.quotation_ref_id.id)])
                if bi_report:
                    bi_report_vals = {
                        'inv_type': inv_created.inv_type,
                        'invoice_create_date': self.convert_gmt_to_ist_tz(inv_created.create_date)
                    }
                    bi_report.sudo().write(bi_report_vals)

        return invoice_vals

    @api.multi
    def monthly_invoice_cron(self):
        now = time.localtime()
        today = date.today()
        d = today - relativedelta(months=1)

        first_day = str(date(d.year, d.month, 1))

        last_day = str(date(today.year, today.month, 1) - relativedelta(days=1))

        # date_to = datetime.date(now.tm_mon, 1) - datetime.timedelta(1)
        # date_from = date_to.replace(day=1)
        # date_from = '2020-02-01'
        # date_to = '2020-02-10'

        # self.env.cr.execute(""" SELECT partner_id, sum(amount_total),currency_id,sum(char_count) from sale_order
        #                         WHERE invoice_status != 'invoiced' AND send_inv_monthly= 't'
        #                         AND type = 'asn' AND create_date
        #                         BETWEEN %s AND %s GROUP BY partner_id,currency_id""" % (first_day, last_day))

        # Local
        self.env.cr.execute(""" SELECT so.mem_id, sum(amount_total), so.currency_id, sum(char_count),rp.parent_id 
                                FROM sale_order so JOIN res_partner rp ON so.partner_id = rp.id 
                                WHERE invoice_status != 'invoiced' AND so.send_inv_monthly= 't' 
                                AND so.type = 'asn' AND state = 'done' AND  rp.parent_id IS NOT NULL AND 
                                so.create_date BETWEEN '2021-01-01' AND '2021-12-28' 
                                GROUP BY so.mem_id, so.currency_id, rp.parent_id""")

        for list_item in self.env.cr.fetchall():
            # Invoice Value Fetch
            partner_search_id = self.env['res.partner'].search([
                ('id', '=', list_item[4]), ('is_company', '=', True)])

            invoice_vals = {
                'name': '',
                'type': 'out_invoice',
                'inv_type': 'mon',
                'send_inv_monthly': True,
                'date_invoice': date.today(),
                'date_due': date.today() + timedelta(days=60),
                'char_count': list_item[3],
                'partner_id': partner_search_id[0].id,
                'origin': self.env['membership.master'].search([('id', '=', list_item[0])]).name + '-' + str(
                    datetime.today().strftime("%b-%Y")
                ),
                'payer_name': partner_search_id[0].name,
                'portal_street': partner_search_id[0].street,
                'portal_street2': partner_search_id[0].street2,
                'portal_city': partner_search_id[0].city,
                'portal_zip': partner_search_id[0].zip,
                'portal_state_id': partner_search_id[0].state_id.id,
                'portal_country_id': partner_search_id[0].country_id.id,
                'portal_phone': partner_search_id[0].phone,
                'portal_mobile': partner_search_id[0].mobile,
                'partner_shipping_id': partner_search_id[0].id,
                'currency_id': list_item[2],
            }

            # Invoice Creation
            inv_created = self.env['account.invoice'].create(invoice_vals)

            _logger.info('-------------CREATED INVOICE----------------: %s' % inv_created.id)

            # Query to select same so for line items
            self.env.cr.execute("""SELECT id from sale_order WHERE invoice_status != 'invoiced' 
                    AND send_inv_monthly= 't' AND type = 'asn' AND state = 'done' AND create_date 
                    BETWEEN '2021-02-01' AND '2021-12-31'""")

            fetch_ids = tuple(itertools.chain(*self.env.cr.fetchall()))
            asn_ids = self.env['sale.order'].search([('id', 'in', fetch_ids)])
            for asn_id in asn_ids:
                _logger.info('-------------QUERY FETCH-------------: %s %s %s %s %s' %
                             (asn_id, asn_id.mem_id, asn_id.partner_id.parent_id, list_item[0], list_item[4]))
                if asn_id.partner_id.parent_id.id == list_item[4] and asn_id.currency_id.id == list_item[2]:

                    _logger.info('-------------IF CONDITION CHECK------------: %s %s %s %s %s' %
                                 (asn_id, asn_id.mem_id, asn_id.partner_id.parent_id, list_item[0], list_item[4]))

                    # Invoice Line Items - Value Fetch
                    invoice_line_vals = {
                        'invoice_line_ids': [(0, 0, {
                            'name': 'Cost for ' + asn_id.name,
                            'account_id': 31,
                            'price_unit': asn_id.amount_total,
                            'quantity': 1,
                            'discount': 0.0,
                            'uom_id': asn_id.unit_id.id,
                        })],
                    }
                    print('Line Values', invoice_line_vals)

                    # Update Line Items
                    _logger.info('------FIND INVOICE------: %s' % self.env['account.invoice'].search(
                        [('id', '=', inv_created.id)]).id)
                    self.env['account.invoice'].search([('id', '=', inv_created.id)]).update(invoice_line_vals)

                    # Monthly invoice line items
                    monthly_line_vals = {
                        'monthly_invoice_ids': [(0, 0, {
                            'name': asn_id.name,
                            'service_level_id': asn_id.service_level_id.id,
                            'deadline': asn_id.deadline,
                            'char_count': asn_id.char_count,
                            'amount_total': asn_id.amount_total,
                            'unit_id': asn_id.unit_id.id,
                            'po_number': asn_id.po_number,
                        })],
                    }
                    print('Line Values', monthly_line_vals)

                    # Update Line Items
                    self.env['account.invoice'].search([('id', '=', inv_created.id)]).update(monthly_line_vals)

                    asn_id.update({'invoice_status': 'invoiced'})

            # Validate Invoice
            inv_created.action_invoice_open()
            inv_created.update({'payment_state': 'open'})

            # Monthly Sequence Update
            sequence_values = {
                'number': self.env['ir.sequence'].next_by_code('seq.monthly.invoice'),
            }
            self.env['account.invoice'].search([('id', '=', inv_created.id)]).update(sequence_values)

            # Create transaction history record after ASN invoice generated
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
                    'activity': 'Charges for ' + inv_created.number,
                    'date': date.today(),
                    'currency_id': inv_created.currency_id.id
                }
                self.env['transaction.history.line'].sudo().create(vals)

                bi_report = self.env['bi.daily.report'].search([('quote_id', '=', self.quotation_ref_id.id)])
                if bi_report:
                    bi_report_vals = {
                        'inv_type': inv_created.inv_type,
                        'invoice_create_date': self.convert_gmt_to_ist_tz(inv_created.create_date)
                    }
                    bi_report.sudo().write(bi_report_vals)

            # To send invoice generation email to client
            # inv_created.send_email_on_inv_generate()
            return invoice_vals

    @api.onchange('advance_payment')
    def get_other_field(self):
        if self.advance_payment and self.advance_payment == '100':
            self.advance_payment_value = 100
        elif self.advance_payment and self.advance_payment == '0':
            self.advance_payment_value = 0
        else:
            self.advance_payment_value = 1

    @api.model
    def quote_deadline_revise(self):
        """
            Cron: To update revised deadline in quotation
            :return: True
        """
        now = datetime.now()
        rounded_now = revise_date_tool.round_time(now, round_to=60 * 30)
        quote_ids = self.env['sale.order'].search([('state', 'in', ['sent', 'revise'])])
        if quote_ids:
            for quote_id in quote_ids:
                try:
                    working_hr_dict = self.env['working.hours'].get_working_hour()
                    flag = False
                    for line in quote_id.order_line:
                        for line_id in line.service_level_line:
                            if rounded_now == line_id.deadline_revise_day:
                                line_id.write({'deadline': line_id.revised_deadline})
                                flag = True
                                revise_deadline_dict = line_id.revise_deadline_operations(line_id.deadline_revise_day,
                                                                                          working_hr_dict.get(
                                                                                              'biz_open_time'),
                                                                                          working_hr_dict.get(
                                                                                              'biz_close_time'),
                                                                                          working_hr_dict.get(
                                                                                              'holiday_list'),
                                                                                          working_hr_dict.get(
                                                                                              'deadline_revise_percentage'),
                                                                                          line_id.deadline_revise_day, False)
                                line_id.write({
                                    'previous_deadline_revise_day': rounded_now,
                                    'deadline_revise_hrs': revise_deadline_dict.get('deadline_revise_hrs'),
                                    'deadline_revise_day': revise_deadline_dict.get('deadline_revise_day'),
                                    'revised_deadline': revise_deadline_dict.get('revised_deadline')
                                })
                        if flag:
                            line._max_deadline()
                    if flag:
                        quote_id.onchange_final_deadline()
                except Exception as e:
                    _logger.info('----cron---quote_deadline_revise---quote_id---e---: %s %s' % (quote_id, e))
        return True

    @api.multi
    def cal_revise_deadline(self):
        """ Calculate Revise Deadline """
        service_level_line = self.order_line.mapped('service_level_line')
        working_hr_dict = self.env['working.hours'].get_working_hour()
        for service_level_id in service_level_line:
            if service_level_id.deadline:
                revise_deadline_dict = service_level_id.revise_deadline_operations(self.quote_sent_datetime,
                                                                                   working_hr_dict.get('biz_open_time'),
                                                                                   working_hr_dict.get(
                                                                                       'biz_close_time'),
                                                                                   working_hr_dict.get('holiday_list'),
                                                                                   working_hr_dict.get(
                                                                                       'deadline_revise_percentage'),
                                                                                   self.quote_sent_datetime, True)
                service_level_id.write({
                    'previous_deadline_revise_day': self.quote_sent_datetime,
                    'deadline_revise_hrs': revise_deadline_dict.get('deadline_revise_hrs'),
                    'deadline_revise_day': revise_deadline_dict.get('deadline_revise_day'),
                    'revised_deadline': revise_deadline_dict.get('revised_deadline')
                })
        return True

    @api.multi
    def send_mail_operation(self):
        url_rec = self.env['ir.config_parameter'].search([('key', '=', 'web.base.url')])
        action_id = self.env.ref('ulatus_cs.action_pending_quotation_order').id
        url = url_rec.value + '/web#action=' + str(action_id) + "&model=sale.order" + "&view_type=list"
        if self.state == 'draft':
            self.update({
                'state': 'sent',
                'quote_sent_datetime': datetime.now()
            })
        if self.state == 'revision_request':
            self.update({
                'state': 'revise',
                'quote_sent_datetime': datetime.now()
            })
            self.revision_request_line.update({'to_show': False})
        self.cal_revise_deadline()
        self.update_bi_report_data()
        return {
            'name': ' ',
            'res_model': 'ir.actions.act_url',
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': url
        }

    @api.onchange('product_id')
    def onchnage_product_id(self):
        """
            Update fee in translation level's on product change
        """
        if self.order_line:
            service_level_line_ids = self.order_line.mapped("service_level_line")
            if service_level_line_ids:
                end_client, membership_id = '', ''
                if self.end_client_id:
                    end_client = """ AND end_client_id = %s""" % str(self.end_client_id.id)
                else:
                    end_client = """ AND end_client_id is NULL"""
                if self.mem_id:
                    membership_id = """ AND membership_id = %s""" % str(self.mem_id.id)
                else:
                    membership_id = """ AND membership_id is NULL"""

                for line in self.order_line:
                    for service_level_line_id in line.service_level_line:
                        fee = []
                        fee_updated = False
                        fee_query = """SELECT price from fee_master 
                                               WHERE product_id = %s 
                                               AND translation_level_id = %s
                                               AND priority = '%s'
                                               AND source_lang_id = %s 
                                               AND target_lang_id = %s
                                               AND currency_id = %s
                                            """ % (
                            str(self.product_id.id), str(service_level_line_id.service_level_id.id),
                            str(self.priority), str(self.source_lang_id.id),
                            str(line.target_lang_id.id), str(self.currency_id.id))

                        common_query = fee_query
                        fee_query += end_client + membership_id
                        self.env.cr.execute(fee_query)
                        data = self.env.cr.fetchall()
                        fee = [x[0] for x in data]
                        if fee:
                            fee_updated = True
                            service_level_line_id.write({
                                'unit_rate': fee[0] or 0.0
                            })
                        if not fee_updated and self.mem_id and not self.end_client_id:
                            fee_query = common_query + membership_id + """ AND end_client_id is NULL"""
                            self.env.cr.execute(fee_query)
                            data = self.env.cr.fetchall()
                            fee = [x[0] for x in data]
                            if fee:
                                fee_updated = True
                                service_level_line_id.write({
                                    'unit_rate': fee[0] or 0.0
                                })
                        if not fee_updated and self.end_client_id and not self.mem_id:
                            fee_query = common_query + end_client + """AND membership_id is NULL"""
                            self.env.cr.execute(fee_query)
                            data = self.env.cr.fetchall()
                            fee = [x[0] for x in data]
                            if fee:
                                fee_updated = True
                                service_level_line_id.write({
                                    'unit_rate': fee[0] or 0.0
                                })
                        if not fee_updated:
                            fee_query = common_query + """ AND end_client_id is NULL 
                                                                   AND membership_id is NULL"""
                            self.env.cr.execute(fee_query)
                            data = self.env.cr.fetchall()
                            fee = [x[0] for x in data]
                            if fee:
                                service_level_line_id.write({
                                    'unit_rate': fee[0] or 0.0
                                })
                            else:
                                service_level_line_id.write({
                                    'unit_rate': 0.0
                                })
                    # Update fee and it's related field value data
                    for tl in self.order_line.mapped('service_level_line'):
                        tl.onchnage_unit_rate()
                    # To update lowest_fee, recommended_deadline and char_count
                    self.onchange_final_deadline()

    @api.multi
    def quotation_url(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': '/page/quotations_details/%s' % self.id,
        }

    @api.multi
    def update_bi_report_data(self):
        bi_reports = self.env['bi.daily.report'].search([('inquiry_id', '=', self.inquiry_id.id)])
        if bi_reports:
            for bi_report in bi_reports:
                diff = False
                response_time= ''
                if self.inquiry_id.create_date and self.quote_sent_datetime:
                    diff = self.quote_sent_datetime - self.inquiry_id.create_date
                if diff:
                    response_time = str(diff).split(".", maxsplit=1)[0]
                if self.is_rr_inquiry:
                    memsource_line_ids = self.order_line.mapped('memsource_line').filtered(lambda l: l.sale_line_id.target_lang_id.id == bi_report.target_lang_ids.id)
                    char_count = self.order_line.filtered(lambda l: l.target_lang_id.id == bi_report.target_lang_ids.id).character_count
                else:
                    memsource_line_ids = self.order_line.mapped('memsource_line')
                    char_count = self.char_count
                non_editable_count,wc_0_49_count,wc_50_74_count,wc_75_84_count,wc_85_94_count = 0.0,0.0,0.0,0.0,0.0
                wc_95_99_count,wc_100_count,wc_101_count,repetitions_count,machine_translation_count = 0.0,0.0,0.0,0.0,0.0
                if memsource_line_ids:
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
                client_instructions = ''
                client_instructions_line = self.order_line[0].mapped('sale_instruction_line').filtered(lambda l: l.is_original_ins == True)
                if client_instructions_line:
                    client_instructions = ['- ' + line.name for line in client_instructions_line]
                    client_instructions = ', '.join(client_instructions)
                bi_report_vals = {
                    'quote_id': self.id,
                    'char_count': char_count,
                    'response_time': response_time,
                    'non_editable_count': non_editable_count,
                    'wc_0_49_percent': wc_0_49_count,
                    'wc_50_74_percent': wc_50_74_count,
                    'wc_75_84_percent': wc_75_84_count,
                    'wc_85_94_percent': wc_85_94_count,
                    'wc_95_99_percent': wc_95_99_count,
                    'wc_100_percent': wc_100_count,
                    'wc_101_percent': wc_101_count,
                    'repetitions': repetitions_count,
                    'machine_translation': machine_translation_count,
                    'po_number': self.po_number,
                    'client_instructions': client_instructions,
                    'actual_client_deadline': self.convert_gmt_to_ist_tz(self.deadline) if self.deadline else self.deadline,
                }
                bi_report.sudo().write(bi_report_vals)

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

    @api.multi
    def mark_trial(self):
        self.ensure_one()

        if self.trial_flag is not True:
            for child_asn in self.env['assignment'].search([('parent_asn_id', '=', self.id)]):
                if self.state == 'on-hold':
                    child_asn.update({'name': str(child_asn.name).replace('_On-Hold', '_TRIAL_On-Hold')})
                else:
                    child_asn.update({'name': str(child_asn.name) + '_TRIAL'})
            if self.state == 'on-hold':
                self.update({'name': str(self.name).replace('_On-Hold', '_TRIAL_On-Hold')})
            else:
                self.update({'name': str(self.name) + '_TRIAL'})
            self.update({'trial_flag': True})

    @api.multi
    def remove_trial(self):
        self.ensure_one()
        if self.trial_flag is True:
            for child_asn in self.env['assignment'].search([('parent_asn_id', '=', self.id)]):
                child_asn.update({'name': str(child_asn.name).replace('_TRIAL', '')})
            self.update({'trial_flag': False})
            self.update({'name': str(self.name).replace('_TRIAL', '')})

    def suffix(self, d):
        return 'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')

    def date_suffix(self, format, date):
        return date.strftime(format).replace('{S}', str(date.day) + '<sup>' + self.suffix(date.day) + '</sup>')


class ParentAsnInstructionLine(models.Model):
    _name = 'parent.asn.instruction.line'
    _description = 'Parent ASN Instruction Line'

    parent_ins_asn_id = fields.Many2one("sale.order", "Instruction Order Line")
    name = fields.Char("Instruction")


class SaleOrderAddonsLine(models.Model):
    _name = 'sale.order.addons.line'
    _description = "Add-ons Lines"

    sale_addons_id = fields.Many2one('sale.order', 'Sale Addons Id')
    addons_service_id = fields.Many2one(
        'product.product', string="Add-ons Service")
    unit = fields.Float("No. of Unit")
    rate = fields.Float("Rate")
    enter_unit_bool = fields.Boolean(related="addons_service_id.enter_unit")
    show_option = fields.Selection([
        ('reccommend', 'Reccommend to the Client'),
        ('optional', 'Show as Optional'),
        ('hide', 'Hide')], 'Show Option', default='reccommend')
    addons_price = fields.Float("Price")
    unit_id = fields.Many2one('service.unit', string="Unit")

    @api.onchange('addons_service_id')
    def onchange_addons_service_id(self):
        for rec in self:
            if rec.addons_service_id:
                rec.addons_price = rec.addons_service_id.lst_price

    @api.onchange('unit')
    def onchange_unit(self):
        for rec in self:
            rec.addons_price = rec.addons_price * rec.unit


class ReasonHistoryLine(models.Model):
    _name = "reason.history.line"
    _description = 'Reason History Lines'

    quote_id = fields.Many2one('sale.order', 'Quotation Id')
    child_asn_id = fields.Many2one('assignment', 'Child ASN Id')
    user = fields.Many2one('res.users', "User")
    logging_date = fields.Datetime("Date")
    state = fields.Char('Status')
    new_value = fields.Char('New Value')
    comment = fields.Text("Comments")


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    _description = "Language Lines"
    _rec_name = "name"

    is_addons_service = fields.Boolean("Is Addons Service")

    _sql_constraints = [
        ('accountable_required_fields',
         'check(1=1)',
         'Missing required fields on accountable sale order line.'),
        ('non_accountable_null_fields',
         'check(1=1)',
         'Forbidden values on non-accountable sale order line'),
    ]

    # Calculate Word Count
    @api.multi
    @api.depends('sale_original_file_line.character_count')
    def _total_character_count(self):
        for rec in self:
            rec.update(
                {'character_count':
                 sum(rec.sale_original_file_line.mapped('character_count'))})

    # Calculate Original and Reference File Total
    @api.multi
    @api.depends('sale_original_file_line', 'reference_assignment_line')
    def _total_file_count(self):
        for rec in self:
            rec.mainfile_count = len(rec.sale_original_file_line)
            rec.referencefile_count = len(rec.reference_assignment_line)

    # Calculate Max Deadline For single Language
    @api.depends("service_level_line.deadline")
    def _max_deadline(self):
        for rec in self:
            deadline_dict = {}
            for service in rec.service_level_line:
                if service.visible_to_client and service.deadline:
                    deadline_dict.update({service.id: service.deadline})
                    if deadline_dict:
                        max_deadline = max(deadline_dict.keys(),
                                                   key=(lambda k: deadline_dict[k]))
                        rec.deadline = deadline_dict.get(max_deadline)


    deadline = fields.Datetime("Deadline", compute="_max_deadline")
    temp_deadline = fields.Datetime("Temporary Deadline")
    check_deadline = fields.Boolean(string='Check Deadline', default=False)
    client_deadline = fields.Datetime(related="order_id.client_deadline", string="Client Deadline")
    source_lang_id = fields.Many2one('res.lang', string='Source language')
    target_lang_id = fields.Many2one('res.lang', string='Target language')
    character_count = fields.Integer(
        "Total Unit Count", compute="_total_character_count")
    mainfile_count = fields.Integer(
        "Total mainfiles", compute='_total_file_count')
    referencefile_count = fields.Integer(
        "Total reference files", compute='_total_file_count')
    additional_instruction = fields.Text(
        "Add additional instructions for the PM Team")
    fee = fields.Monetary("Fees", copy=True)
    update_rec = fields.Char('Please Update record for other services!')
    # product_id = fields.Many2one('product.product',
    #                              related="order_id.product_id",
    #                              string="Product")

    # All One2Many Lines
    sale_original_file_line = fields.One2many("ir.attachment",
                                              'quotation_id',
                                              'Original File Line',
                                              track_visibility='onchange',
                                              domain=[('file_type', '=',
                                                       'client')], copy=True)
    reference_assignment_line = fields.One2many("ir.attachment",
                                                'quotation_id',
                                                'Refrence File Line',
                                                track_visibility='onchange',
                                                domain=[('file_type', '=',
                                                         'refrence')], copy=True)
    sale_instruction_line = fields.One2many('sale.instruction.line',
                                            'ins_line_id',
                                            'Instruction Order Lines',
                                            copy=True)
    service_level_line = fields.One2many('service.level.line',
                                         'sale_service_line_id',
                                         'Translation Levels', copy=True)
    addons_fee_line = fields.One2many('addons.fee.line', 'sale_order_line_id',
                                      'Add-ons Fee Line', copy=True)

    # Unit of measure for source language
    unit_id = fields.Many2one('service.unit', string="Unit",
                              track_visibility='onchange')
    is_legacy_data = fields.Boolean(string="Is Legacy Data", default=False)

    @api.onchange('sale_original_file_line')
    def onchange_sale_original_file_line(self):
        """
        This onchange is use for restrict duplicate addons in line.
        :return: Warning if found duplicate.
        """
        original_file_dict = {}
        for file in self.sale_original_file_line:
            if file.datas_fname in original_file_dict.keys():
                raise ValidationError(_("File with same name already exits!"))
            else:
                original_file_dict.update({file.datas_fname: False})
        # addons_fee_dict = {}
        # total_unit_count = sum(self.sale_original_file_line.mapped('character_count'))
        # for translation in self.service_level_line:
        #     translation.fee = total_unit_count * translation.unit_rate

    @api.onchange('reference_assignment_line')
    def onchange_reference_assignment_line(self):
        ref_file_dict = {}
        for file in self.reference_assignment_line:
            if file.datas_fname in ref_file_dict.keys():
                raise ValidationError(_("File with same name already exits!"))
            else:
                ref_file_dict.update({file.datas_fname: False})

    @api.multi
    def name_get(self):
        """
            Override : To stop appending sale order name in sale order line name
        """
        result = []
        for so_line in self.sudo():
            name = '%s' % ((so_line.name and so_line.name.split('\n')[0]) or so_line.product_id.name)
            if so_line.order_partner_id.ref:
                name = '%s (%s)' % (name, so_line.order_partner_id.ref)
            result.append((so_line.id, name))
        return result

    def action_show_quotation_details(self):
        """
        Show Quotation Line Details on click this button
        """
        self.ensure_one()
        ctx = self._context.copy()
        ctx.update({
            'product_id': self.order_id.product_id.id,
            'form_view_initial_mode': 'edit'
        })
        if self.state == 'revision_request':
            view = self.env.ref('ulatus_cs.view_quotation_revision_request_line_view')
        else:
            view = self.env.ref('ulatus_cs.view_quotation_line_details')
        return {
            'name': 'Quotation Services',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'sale.order.line',
            'views': [(view.id, 'form')],
            'target': 'current',
            'res_id': self.id,
            'context': ctx,
        }

    def update_files(self):
        """
            This method is use for update/delete translation file to every order line
            whenever user add/remove file on sale order line
        """
        line_ids = self.order_id.order_line - self
        add_list = []
        tmp_add_list = []
        vals = {}
        if line_ids:
            file_name_lst = list(set(line_ids.mapped('sale_original_file_line.datas_fname')))
            current_lst = self.sale_original_file_line.mapped('datas_fname')
            remove_lst = list(set(file_name_lst) - set(current_lst))
            if remove_lst:
                del_lst = line_ids.mapped('sale_original_file_line').filtered(lambda l: l.datas_fname in remove_lst)
                tras_remv_lst = self.order_id.mapped('translation_file_line').filtered(
                    lambda l: l.datas_fname in remove_lst)
                file_remove = tras_remv_lst + del_lst
                vals.update({'file_remove': file_remove})
            add_file_lst = list(set(current_lst) - set(file_name_lst))
            if add_file_lst:
                for rec in self.sale_original_file_line:
                    if rec.name not in file_name_lst:
                        tmp_add_list.append(rec)

                # To prepare attachment one2many records for sale_order
                add_list = self.order_id.prepare_one2many_records(self.name, 'quotation', tmp_add_list,
                                                                  'translation_file_line', False)

                # To prepare attachment one2many records for sale_order_line
                line_original_file_list = self.order_id.prepare_one2many_records(self.name, 'quotation', tmp_add_list,
                                                                                 'sale_original_file_line',
                                                                                 self.target_lang_id.initial_code)

                line_ids.write({'sale_original_file_line': line_original_file_list})
                vals.update({'add_list': add_list})
        return vals

    @api.multi
    def action_update_quotation(self):
        """
            Validations and operations perform on sale order line
        """
        # If the deadline selected by CS is greater then the Client
        # Deadline(selected by client), then show an Alert pop-up
        for rec in self.service_level_line:
            if rec.deadline:
                if rec.deadline > self.client_deadline and not self.check_deadline:
                    update_query = """UPDATE sale_order_line
                                                SET check_deadline=true
                                                 WHERE id=%s""" % (str(self.id))
                    self.env.cr.execute(update_query)
                    self.env.cr.commit()
                    raise UserError(
                        _('The Delivery Deadline is greater than the Client Requested Delivery Deadline.'))

        ins_line = []
        service_level_line = self.service_level_line.filtered(lambda f: not f.deadline and f.visible_to_client)
        instruction_line = set(self.sale_instruction_line.filtered(lambda f: not f.is_original_ins).mapped('name'))
        parent_ins = set(self.order_id.instruction_line.filtered(lambda f: not f.is_original_ins).mapped('name'))
        final_ins = list(instruction_line - parent_ins)
        if final_ins:
            ins_line = [(0, 0, {'name': ins}) for ins in final_ins]
        sale_instruction_line = self.sale_instruction_line.filtered(lambda f: not f.mark_reviewed)

        if sale_instruction_line:
            raise ValidationError(_("Please check the instructions and select accordingly!"))
        if service_level_line:
            raise ValidationError(_("Please enter deadline date for Translation Level's!"))

        self.order_id.onchange_final_deadline()

        if self.order_id.sale_order_addons_line:
            self.order_id.sale_order_addons_line.unlink()
        addons_lines = self.order_id.order_line.mapped('addons_fee_line')
        addons_dict = {}
        for addons in addons_lines:
            addons_id = addons.addons_id.id
            unit_id = addons.unit_id.id
            adoons_key = str(addons_id)+'_'+str(unit_id)
            if adoons_key not in addons_dict.keys():
                addons_dict.update({
                    adoons_key: (0, 0, {
                        'unit': addons.no_of_unit,
                        'rate': addons.price,
                        'addons_price': addons.total_price,
                        'addons_service_id': addons_id,
                        'unit_id': unit_id,
                    })
                })
            else:
                addons_dict[adoons_key][2]['unit'] += addons.no_of_unit
                addons_dict[adoons_key][2]['rate'] += addons.price
                addons_dict[adoons_key][2]['addons_price'] += addons.total_price

        self.order_id.write({
            'sale_order_addons_line': list(addons_dict.values()),
            'instruction_line': ins_line,
        })
        self.order_id.update_bi_report_data()
        view_id = self.env.ref('fine_uploader.message_wiz_form_view').id
        return {
            'name': 'Message',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'message.wiz',
            'views': [[view_id, 'form']],
            'target': 'new',
            'context': {
                'default_message': "Record updated successfully.",
                'order_line': True,
            },
        }

    def update_order_line_files(self):
        """
            This method is use for update/delete translation and reference files to every order line
            whenever user add/remove file on sale order line
        """
        ref_file_list, tmp_ref_file_list, ref_file_dict = [], [], {}
        trans_file_list, tmp_trans_file_list, trans_file_dict = [], [], {}

        # reference file
        ref_file_line = self.order_id.order_line.mapped("reference_assignment_line").filtered(
            lambda f: not f.memsource_file)
        for ref_file in ref_file_line:
            if ref_file.datas_fname not in ref_file_dict.keys():
                tmp_ref_file_list.append(ref_file)
                # To prepare attachment one2many records for sale_order
                ref_file_list = self.order_id.prepare_one2many_records(self.name, 'quotation', tmp_ref_file_list,
                                                                       'refrence_file_line', False)
                ref_file_dict.update({ref_file.datas_fname: ref_file})

        # translation files
        trans_file_line = self.order_id.order_line.mapped("sale_original_file_line")
        for trans_file in trans_file_line:
            if trans_file.datas_fname not in trans_file_dict.keys():
                tmp_trans_file_list.append(trans_file)
                # To prepare attachment one2many records for sale_order
                trans_file_list = self.order_id.prepare_one2many_records(self.name, 'quotation', tmp_trans_file_list,
                                                                         'translation_file_line', False)
                trans_file_dict.update({trans_file.datas_fname: trans_file})

        attachment_ids = self.order_id.translation_file_line
        attachment_ids += self.order_id.refrence_file_line.filtered(lambda f: not f.memsource_file)
        attachment_ids.unlink()

        self.order_id.write({
            'translation_file_line': trans_file_list,
            'refrence_file_line': ref_file_list,
        })
        return True

    # def update_files(self):
    #     """
    #     This method is use for update/delete translation file to every order line
    #     whenever user add/remove file on sale order line on save button.
    #     """
    #     line_ids = self.order_id.order_line - self
    #     add_list = []
    #     tmp_add_list = []
    #     vals = {}
    #     if line_ids:
    #         file_name_lst = list(set(line_ids.mapped('sale_original_file_line.datas_fname')))
    #         current_lst = self.sale_original_file_line.mapped('datas_fname')
    #         remove_lst = list(set(file_name_lst) - set(current_lst))
    #         if remove_lst:
    #             del_lst = line_ids.mapped('sale_original_file_line').filtered(lambda l: l.datas_fname in remove_lst)
    #             tras_remv_lst = self.order_id.mapped('translation_file_line').filtered(
    #                 lambda l: l.datas_fname in remove_lst)
    #             file_remove = tras_remv_lst + del_lst
    #             vals.update({'file_remove': file_remove})
    #         add_file_lst = list(set(current_lst) - set(file_name_lst))
    #         if add_file_lst:
    #             for rec in self.sale_original_file_line:
    #                 if rec.name not in file_name_lst:
    #                     tmp_add_list.append(rec)
    #                     # add_list.append((0, 0, {
    #                     #     'name': rec.datas_fname,
    #                     #     'datas': rec.datas,
    #                     #     'datas_fname': rec.datas_fname,
    #                     #     'file_type': rec.file_type,
    #                     # }))
    #
    #             # To prepare attachment one2many records for sale_order
    #             add_list = self.order_id.prepare_one2many_records(self.name, 'quotation', tmp_add_list,
    #                                                               'translation_file_line', False)
    #
    #             # To prepare attachment one2many records for sale_order_line
    #             line_original_file_list = self.order_id.prepare_one2many_records(self.name, 'quotation', tmp_add_list,
    #                                                                              'sale_original_file_line',
    #                                                                              self.target_lang_id.initial_code)
    #
    #             line_ids.write({'sale_original_file_line': line_original_file_list})
    #             vals.update({'add_list': add_list})
    #     return vals
    #
    # # Save button for sale order line
    # @api.multi
    # def action_update_quotation(self):
    #     # If the deadline selected by CS is greater then the Client
    #     # Deadline(selected by client), then show an Alert pop-up
    #     for rec in self.service_level_line:
    #         if rec.deadline:
    #             if rec.deadline > self.client_deadline and not self.check_deadline:
    #                 update_query = """UPDATE sale_order_line
    #                                     SET check_deadline=true
    #                                      WHERE id=%s""" % (str(self.id))
    #                 self.env.cr.execute(update_query)
    #                 self.env.cr.commit()
    #                 raise UserError(_('The Delivery Deadline is greater than the Client Requested Delivery Deadline.'))
    #
    #     ref_file_list, tmp_ref_file_list, ins_line, ref_file_dict = [], [], [], {}
    #
    #     service_level_line = self.service_level_line.filtered(lambda f: not f.deadline and f.visible_to_client)
    #     instruction_line = set(self.sale_instruction_line.filtered(lambda f: not f.is_original_ins).mapped('name'))
    #     parent_ins = set(self.order_id.instruction_line.filtered(lambda f: not f.is_original_ins).mapped('name'))
    #     final_ins = list(instruction_line - parent_ins)
    #     if final_ins:
    #         ins_line = [(0, 0, {'name': ins}) for ins in final_ins]
    #     sale_instruction_line = self.sale_instruction_line.filtered(lambda f: not f.mark_reviewed)
    #
    #     if sale_instruction_line:
    #         raise ValidationError(_("Please check the instructions and select accordingly!"))
    #     if service_level_line:
    #         raise ValidationError(_("Please enter deadline date for Translation Level's!"))
    #
    #     self.order_id.onchange_final_deadline()
    #     ref_file_line = self.order_id.order_line.mapped("reference_assignment_line").filtered(
    #         lambda f: not f.memsource_file)
    #
    #     for ref_file in ref_file_line:
    #         if ref_file.datas_fname not in ref_file_dict.keys():
    #             tmp_ref_file_list.append(ref_file)
    #             # ref_file_list.append((0, 0, {
    #             #     'name': ref_file.datas_fname,
    #             #     'datas': ref_file.datas,
    #             #     'datas_fname': ref_file.datas_fname,
    #             #     'file_type': ref_file.file_type,
    #             #     'category_type_id': ref_file.category_type_id and ref_file.category_type_id.id or False
    #             # }))
    #
    #             # To prepare attachment one2many records for sale_order
    #             ref_file_list = self.order_id.prepare_one2many_records(self.name, 'quotation', tmp_ref_file_list,
    #                                                                    'refrence_file_line', False)
    #
    #             ref_file_dict.update({ref_file.datas_fname: ref_file})
    #     if self.order_id.sale_order_addons_line:
    #         self.order_id.sale_order_addons_line.unlink()
    #     addons_lines = self.order_id.order_line.mapped('addons_fee_line')
    #     addons_dict = {}
    #     for addons in addons_lines:
    #         addons_id = addons.addons_id.id
    #         unit_id = addons.unit_id.id
    #         adoons_key = str(addons_id)+'_'+str(unit_id)
    #         if adoons_key not in addons_dict.keys():
    #             addons_dict.update({
    #                 adoons_key: (0, 0, {
    #                     'unit': addons.no_of_unit,
    #                     'rate': addons.price,
    #                     'addons_price': addons.total_price,
    #                     'addons_service_id': addons_id,
    #                     'unit_id': unit_id,
    #                 })
    #             })
    #         else:
    #             addons_dict[adoons_key][2]['unit'] += addons.no_of_unit
    #             addons_dict[adoons_key][2]['rate'] += addons.price
    #             addons_dict[adoons_key][2]['addons_price'] += addons.total_price
    #     file_list = self.update_files()
    #     attachment_ids = self.order_id.refrence_file_line.filtered(lambda f: not f.memsource_file)
    #     if file_list.get('file_remove'):
    #         attachment_ids += file_list.get('file_remove')
    #     attachment_ids.unlink()
    #     self.order_id.write({
    #         'sale_order_addons_line': list(addons_dict.values()),
    #         'translation_file_line': file_list.get('add_list'),
    #         'instruction_line': ins_line,
    #         'refrence_file_line': ref_file_list,
    #     })
    #     return {'type': 'ir.actions.act_window_close'}

    @api.multi
    def download_all_translation_files(self):
        """
        Use for download all translation file with help of controller.
        :return: Download file url.
        """
        for rec in self:
            if rec.sale_original_file_line:
                zipname = 'Translation Files'
                url = '/web/binary/download_document?tab_id=%s&zipname=%s' % (
                    [rec.sale_original_file_line.ids], zipname)
                return {
                    'type': 'ir.actions.act_url',
                    'url': url,
                    'target': 'new',
                }
            else:
                raise UserError(_('No Translation files are available.'))

    @api.multi
    def download_all_reference_files(self):
        """
        Use for download all translation file with help of controller.
        :return: Download file url.
        """
        for rec in self:
            if rec.reference_assignment_line:
                zipname = 'Translation Files'
                url = '/web/binary/download_document?tab_id=%s&zipname=%s' % (
                    [rec.sale_original_file_line.ids], zipname)
                return {
                    'type': 'ir.actions.act_url',
                    'url': url,
                    'target': 'new',
                }
            else:
                raise UserError(_('No Translation files are available.'))

    @api.multi
    def download_all_translation_and_reference_files(self):
        """
        Use for download all translation and reference files with help of controller.
        :return: Download file url.
        """
        for rec in self:
            if rec.sale_original_file_line or rec.reference_assignment_line:
                zipname = 'Translation and Reference Files'
                all_ids = [rec.sale_original_file_line.ids + rec.reference_assignment_line.ids]
                url = '/web/binary/download_document?tab_id=%s&zipname=%s' % (all_ids, zipname)
                return {
                    'type': 'ir.actions.act_url',
                    'url': url,
                    'target': 'new',
                }
            else:
                raise UserError(_('No Translation and Reference Files are available.'))

    @api.onchange('addons_fee_line')
    def onchange_addons_fee_line(self):
        """
        This onchange is use for restrict duplicate addons in line.
        :return: Warning if found duplicate.
        """
        addons_fee_dict = {}
        for addons in self.addons_fee_line:
            if addons.addons_id.id in addons_fee_dict.keys() and addons.unit_id.id in addons_fee_dict.values():
                raise ValidationError(
                    _("You can not select duplicate Add-ons!"))
            else:
                addons_fee_dict.update({addons.addons_id.id: addons.unit_id.id})

    # @api.onchange('service_level_line')
    # def onchange_service_level_line(self):
    #     service_dict = {}
    #     for service in self.service_level_line:
    #         ser = service.service_level_id
    #         if ser.id in service_dict.keys():
    #             raise ValidationError(
    #                 _("You can not select duplicate translation level!"))
    #         else:
    #             service_dict.update({ser.id: False})
    #         if service.reccommend:
    #             if service.reccommend in service_dict.values():
    #                 raise ValidationError(
    #                     _("Already recommended on 1 translation level, Please "
    #                         "uncheck if you wish to recommed this one!"))
    #             service_dict.update({ser.id: service.reccommend})

    def update_record(self):
        line_ids = self.order_id.order_line - self
        line_ids.update({'sale_original_file_line': [(6, 0, [])],
                         'reference_assignment_line': [(6, 0, [])],
                         })
        original_file_list = [(0, 0, {
            'datas': original_line.datas,
            'character_count': original_line.character_count,
            'datas_fname': original_line.datas_fname,
            'name': original_line.datas_fname,
            'file_type': original_line.file_type})
            for original_line in self.sale_original_file_line]
        refrence_file_list = [(0, 0, {'datas': ref_line.datas,
                                      'datas_fname': ref_line.datas_fname,
                                      'name': ref_line.datas_fname,
                                      'file_type': ref_line.file_type, })
                              for ref_line in self.reference_assignment_line]
        line_ids.update({'sale_original_file_line': original_file_list,
                         'reference_assignment_line': refrence_file_list})

        # action = self.env.ref('ulatus_cs.action_cs_quotation_order').read()[0]
        # return action
        return {'type': 'ir.actions.client', 'tag': 'history.back'}
        # return {'type': 'ir.actions.act_window_close'}

    @api.multi
    def upload_files(self):
        res = self.env['ir.actions.act_window'].for_xml_id('fine_uploader', 'action_file_uploader')
        ref = self.env.ref('fine_uploader.action_file_uploader')
        res.update({'target': 'new'})
        return res


class AddonsFeeLine(models.Model):
    _name = 'addons.fee.line'
    _description = 'Add-ons Fee Lines'

    sale_order_line_id = fields.Many2one('sale.order.line', 'Sale Order Line')
    addons_id = fields.Many2one('product.product', string="Add-ons")
    no_of_unit = fields.Float('No. of Unit', default=1)
    price = fields.Float("Price")
    total_price = fields.Float("Total Price")
    unit_id = fields.Many2one('service.unit', string="Unit")
    enter_unit_bool = fields.Boolean(related="addons_id.enter_unit")

    @api.onchange('no_of_unit', 'price')
    def onchnage_price(self):
        self.update({'total_price': self.no_of_unit * self.price})

    @api.onchange('addons_id')
    def onchnage_addons_id(self):
        domain = {'domain': {'unit_id': [('id', 'in', [])]}}
        if self.addons_id:
            active_id = self._context.get('active_id')
            active_model = self._context.get('active_model')
            line_id = self.env[active_model].browse(int(active_id))
            query_str = """SELECT unit_id FROM addons_fee_master 
                               WHERE addons_id = %s AND currency_id = %s
                               AND priority = '%s' AND product_id = %s
                               AND source_lang_id = %s
                               AND target_lang_id = %s 
                            """ % (self.addons_id.id, line_id.order_id.currency_id.id,
                                   line_id.order_id.priority, line_id.order_id.product_id.id,
                                   line_id.source_lang_id.id, line_id.target_lang_id.id)
            self.env.cr.execute(query_str)
            unit_lst = [x[0] for x in self.env.cr.fetchall()]
            if unit_lst:
                domain = {'domain': {'unit_id': [('id', 'in', unit_lst)]}}
            else:
                raise UserError(
                    _("No add-ons fee setup please contact CS Admin to configure!"))
            if len(unit_lst) == 1:
                self.unit_id = unit_lst[0]
        return domain

    @api.onchange('unit_id')
    def onchnage_unit_id(self):
        domain = {'domain': {'unit_id': [('id', 'in', [])]}}
        if self.unit_id:
            active_id = self._context.get('active_id')
            active_model = self._context.get('active_model')
            line_id = self.env[active_model].browse(int(active_id))
            query_str = """SELECT unit_id FROM addons_fee_master 
                               WHERE addons_id = %s AND currency_id = %s
                               AND priority = '%s' AND product_id = %s
                               AND source_lang_id = %s
                               AND target_lang_id = %s 
                        """ % (self.addons_id.id, line_id.order_id.currency_id.id,
                               line_id.order_id.priority, line_id.order_id.product_id.id,
                               line_id.source_lang_id.id, line_id.target_lang_id.id)
            self.env.cr.execute(query_str)
            addon_fee_lst = self.env.cr.fetchall()
            unit_lst = [x[0] for x in addon_fee_lst]

            if unit_lst:
                domain = {'domain': {'unit_id': [('id', 'in', unit_lst)]}}

            end_client, membership_id = '', ''
            if line_id.order_id.end_client_id:
                end_client = """ AND end_client_id = %s""" % str(line_id.order_id.end_client_id.id)
            else:
                end_client = """ AND end_client_id is NULL"""
            if line_id.order_id.mem_id:
                membership_id = """ AND membership_id = %s""" % str(line_id.order_id.mem_id.id)
            else:
                membership_id = """ AND membership_id is NULL"""
            updated_fee = []
            fee_query = """SELECT price FROM addons_fee_master 
                           WHERE addons_id = %s 
                           AND currency_id = %s
                           AND priority = '%s' 
                           AND product_id = %s
                           AND source_lang_id = %s
                           AND target_lang_id = %s 
                           AND unit_id = %s 
                        """ % (self.addons_id.id, line_id.order_id.currency_id.id,
                               line_id.order_id.priority, line_id.order_id.product_id.id,
                               line_id.source_lang_id.id, line_id.target_lang_id.id,
                               str(self.unit_id.id))

            common_query = fee_query
            fee_query += end_client + membership_id
            self.env.cr.execute(fee_query)
            data = self.env.cr.fetchall()
            addons_fee = [x[0] for x in data]

            if addons_fee:
                updated_fee = True
                self.update({
                    'price': addons_fee[0],
                    'total_price': self.no_of_unit * addons_fee[0],
                })
            if not updated_fee and line_id.order_id.mem_id:
                fee_query = common_query + membership_id + """AND end_client_id is NULL"""
                self.env.cr.execute(fee_query)
                addon_fee_list = self.env.cr.fetchall()
                addons_fee = [x[0] for x in addon_fee_list]
                if addons_fee:
                    updated_fee = True
                    self.update({
                        'price': addons_fee[0],
                        'total_price': self.no_of_unit * addons_fee[0],
                    })
            if not updated_fee and line_id.order_id.end_client_id:
                fee_query = common_query + end_client + """AND membership_id is NULL"""
                self.env.cr.execute(fee_query)
                addon_fee_list = self.env.cr.fetchall()
                addons_fee = [x[0] for x in addon_fee_list]
                if addons_fee:
                    updated_fee = True
                    self.update({
                        'price': addons_fee[0],
                        'total_price': self.no_of_unit * addons_fee[0],
                    })
            if not updated_fee:
                fee_query = common_query + """ AND end_client_id is NULL 
                                               AND membership_id is NULL """
                self.env.cr.execute(fee_query)
                addon_fee_list = self.env.cr.fetchall()
                addons_fee = [x[0] for x in addon_fee_list]
                if addons_fee:
                    self.update({
                        'price': addons_fee[0],
                        'total_price': self.no_of_unit * addons_fee[0],
                    })
                else:
                    raise ValidationError(_("No add-ons fee setup please contact CS Admin to configure!"))
        return domain


class ServiceLevelLine(models.Model):
    _name = 'service.level.line'
    _description = 'Translation Level Lines'

    sale_service_line_id = fields.Many2one("sale.order.line", "Service Line Id")
    service_level_id = fields.Many2one("service.level", string="Translation Level")
    add_translation_level_id = fields.Many2one('add.translation.level.line', string="Translation Level ID")
    deadline = fields.Datetime("Deadline")
    unit_rate = fields.Float("Unit Rate")
    fee = fields.Float("Fee")
    reccommend = fields.Boolean("Recommended")
    visible_to_client = fields.Boolean("Visible To Client")
    is_original_service_level = fields.Boolean('Is Original Translation Level')

    deadline_revise_hrs = fields.Float("Deadline Revise Hours")
    deadline_revise_day = fields.Datetime("Deadline Revise Day")
    previous_deadline_revise_day = fields.Datetime("Previous Deadline Revise Day")
    revised_deadline = fields.Datetime("Revised Deadline")

    @api.multi
    def revise_deadline_operations(self, start_datetime, biz_open_time, biz_close_time, holiday_list, percentage,
                                   previous_deadline_revise_day, initial):
        # To get Deadline Revise hours
        deadline_revise_hrs = revise_date_tool.get_deadline_revise_hrs(start_datetime, self.deadline,biz_open_time,
                                                                       biz_close_time, holiday_list, percentage,
                                                                       initial)
        # To get deadline revise datetime
        deadline_revise_day = revise_date_tool.deadline_revise_day(deadline_revise_hrs, previous_deadline_revise_day,
                                                                   holiday_list, biz_open_time, biz_close_time)
        # To get Revised Deadline
        revised_deadline = revise_date_tool.get_revised_deadline(deadline_revise_hrs, self.deadline, biz_open_time,
                                                                 biz_close_time, holiday_list)
        return {
            'deadline_revise_hrs': deadline_revise_hrs,
            'deadline_revise_day': deadline_revise_day,
            'revised_deadline': revised_deadline
        }

    @api.onchange('deadline')
    def onchange_deadline(self):
        active_id = self._context.get('active_id')
        active_model = self._context.get('active_model')
        line_id = self.env[active_model].browse(int(active_id))

        if self.deadline:
            update_query = """UPDATE sale_order_line
                                SET check_deadline=false
                                 WHERE id=%s""" % (str(active_id))
            # update_query = self.service_level_id.ids.update({'check_deadline': False})
            self.env.cr.execute(update_query)
            self.env.cr.commit()

            current_date = datetime.strptime(line_id.order_id.dashboard_convert_to_user_timezone(datetime.now()).
                    strftime("%Y-%m-%d %H:00:00"), '%Y-%m-%d %H:00:00')
            deadline = datetime.strptime(line_id.order_id.dashboard_convert_to_user_timezone(self.deadline).
                    strftime("%Y-%m-%d %H:00:00"), '%Y-%m-%d %H:00:00')
            current_date = current_date + timedelta(hours=1, minutes=00, seconds=00)
            if deadline < current_date:
                tz = 'GMT'
                if self.env.context['tz']:
                    tz = self.env.context['tz']
                today_utc = fields.Datetime.to_string(
                    pytz.timezone(tz).localize(
                        fields.Datetime.from_string(current_date),
                        is_dst=None).astimezone(pytz.utc))
                self.deadline = today_utc

    @api.onchange('unit_rate')
    def onchnage_unit_rate(self):
        self.fee = self.unit_rate * self.sale_service_line_id.character_count


class SaleInstructionLine(models.Model):
    _name = 'sale.instruction.line'
    _order = 'create_date desc'
    _description = 'Sale Instruction Line'

    ins_line_id = fields.Many2one("sale.order.line", "Instruction Order Line")
    name = fields.Text("Instruction")
    mark_reviewed = fields.Boolean("Mark as Reviewed")
    send_ins_to_pm = fields.Boolean("Send instruction to PM Team")
    """
    Remove Delete access from original Instruction Fields
    """
    is_original_ins = fields.Boolean('Is Original Instruction')
    is_default_ins = fields.Boolean('Is Default Instruction')
    order_id = fields.Many2one('sale.order', 'Quotation')


class QuotationRevisionInstructionLine(models.Model):
    _name = 'quotation.revision.instruction.line'
    _description = 'Quotation Revision Instruction Line'

    quote_revision_line_id = fields.Many2one(
        "sale.order.line", "Quotation Revision Id")
    name = fields.Char("Instruction")
    mark_reviewed = fields.Boolean("Mark as Reviewed")
    send_ins_to_pm = fields.Boolean("Send instruction to PM Team")
    """
    Remove Delete access from Quotation Revision Instruction Fields
    """
    is_quote_revision_ins = fields.Boolean('Is Quote Revision Instruction')


class CheckListLine(models.Model):
    _name = 'checklist.line'
    _description = 'Checklist Line'

    sale_checklist_id = fields.Many2one('sale.order', 'Sale Checklist Id')
    checklist_id = fields.Many2one('checklist', string="Checklist")
    option = fields.Selection([('yes', 'Yes'), ('no', 'No')], 'Option')


class AddTranslationLevelLine(models.Model):
    _name = 'add.translation.level.line'
    _description = 'Add Translation Level Line'

    sale_order_id = fields.Many2one(
        'sale.order', string="Sale Order Id")
    service_level_id = fields.Many2one('service.level', string="Translation level")
    reccommend = fields.Boolean("Recommended")
    visible_to_client = fields.Boolean("Visible To Client")


class TransactionHistoryLine(models.Model):
    _name = "transaction.history.line"
    _description = 'Transaction History Line'

    # sale_order_id = fields.Many2one('sale.order', string='Sale Order Id')
    # assignment_id = fields.Many2one('assignment', string='Assignment Id')
    partner_id = fields.Many2one('res.partner', string='Client')
    invoice_id = fields.Many2one('account.invoice', string='Invoice')
    payment_id = fields.Many2one('account.payment', string='Payment')
    charges_amount = fields.Float(string='Order Charges', readonly=True)
    adjustment_amount = fields.Float(string='Adjustment Amount', readonly=True)
    payment_amount = fields.Float(string='Payment Amount', readonly=True)
    outstanding_amount = fields.Float(string='Outstanding Amount', readonly=True)
    activity = fields.Text(string="Transaction Activity")
    date = fields.Datetime(string="Transaction Date")
    currency_id = fields.Many2one("res.currency", related=False, required=False,
                                  string="Currency", readonly=False, track_visibility='onchange')


class LegacyDataLine(models.Model):
    _name = "legacy.data.line"
    _description = 'Legacy Data Line'

    serial_no = fields.Char("Serial Number")
    status = fields.Char("ASN Status")
    asn_no = fields.Char("ASN Number")
    target_lang_id = fields.Many2one('res.lang', "Target Language")
    client_deadline = fields.Datetime("Client Deadline")
    actual_delivery_datetime = fields.Datetime("Actual Delivery Deadline")
    word_count = fields.Integer("Word Count")
    weighted_word_count = fields.Integer("Weighted Word Count")
    instruction = fields.Text("Client Instruction")
    total_fee = fields.Float("Total Fee")
    sale_order_id = fields.Many2one('sale.order', 'Sale Order Id')
