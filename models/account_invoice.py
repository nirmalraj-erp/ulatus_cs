# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from datetime import datetime, date, timedelta
import time
from odoo.tools import float_round, float_is_zero
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError


class AccountInvoiceInherit(models.Model):
    _inherit = 'account.invoice'

    advance_payment = fields.Selection(
        [('0', '0%'),
         ('1_99', '1-99%'),
         ('100', '100%')], 'Advance %')
    advance_payment_value = fields.Integer('Advance Payment %', default=100)
    inv_type = fields.Selection(
        [('mon', 'Monthly'),
         ('ind', 'Individual')], 'Invoicing Type')
    send_inv_monthly = fields.Boolean(
        "Send Invoice Monthly", track_visibility='onchange')
    advance_payment_amount = fields.Monetary(string='Advance Amount',
                                   store=True, readonly=True)
    advance_pending_amount = fields.Monetary(string='Advance Pending Amount',
                                             store=True, readonly=True)
    sale_order_id = fields.Many2one("sale.order", "Sale Order Id")
    assignment_id = fields.Many2one("assignment", "Assignment Id")
    advance_payment_done = fields.Boolean("Advance Payment Done", default=False)
    premium_amount = fields.Monetary(string='Premium')
    discount_amount = fields.Monetary(string='Discount')
    ks_amount_discount = fields.Monetary(string='Discount')
    received_amount = fields.Float("Amount Received")
    postpone_date = fields.Date('Date of Postponement', track_visibility='onchange')
    postpone_reason = fields.Selection(
        [('business', 'On a Business Trip'),
         ('others', 'Other Reasons')], string='Reason', track_visibility='onchange')
    postpone_comment = fields.Char('Comments', track_visibility='onchange')
    adjustment_type = fields.Selection(
        [('discount', 'Special Discount'),
         ('premium', 'Special Premium')], string='Adjustment Type', track_visibility='onchange')
    adjustment_amount = fields.Monetary(string='Adjustment Amount')
    adjustment_comment = fields.Char(string='Comment')
    final_amount = fields.Monetary(compute='final_amount_cal', string='Final Amount', readonly=True)
    is_seen = fields.Boolean('Is Seen')
    product_id = fields.Many2one('product.product', string="Product")
    service = fields.Char('Invoice Service')
    so_state = fields.Selection([('draft', 'New Quotation'),
                                 ('sent', 'Quotation Sent'),
                                 ('revision_request', 'Revision Requested'),
                                 ('revise', 'Revised'),
                                 ('on-hold', 'ASN On-Hold'),
                                 ('sale', 'ASN confirmed'),
                                 ('asn_work_in_progress', 'ASN Work-in-progress'),
                                 ('done', 'ASN Completed'),
                                 ('cancel', 'Rejected')],
                                'Status', default='draft',
                                track_visibility='onchange', copy=True, related='sale_order_id.state')

    to_pay = fields.Monetary('To Pay', compute='to_pay_amount', store=True, copy=False)

    monthly_invoice_ids = fields.One2many('monthly.invoice.line', 'invoice_id', string='Monthly Invoice Lines',
                                          readonly=True, copy=True)

    payment_state = fields.Selection(
        [('open', 'Open'),
         ('partial', 'Partial Payment'),
         ('paid', 'Fully Paid')], string='Payment Status')

    asn_stored_ids = fields.Many2many('assignment', string='ASN IDs')

    @api.depends('partner_id')
    def payer_name_update(self):
        if self.partner_id:
            self.update({'payer_name': self.partner_id.name,
                         'portal_street': self.partner_id.street,
                         'portal_street2': self.partner_id.street2,
                         'portal_city': self.partner_id.city,
                         'portal_zip': self.partner_id.zip,
                         'portal_state_id': self.partner_id.state_id,
                         'portal_country_id': self.partner_id.country_id,
                         'portal_phone': self.partner_id.phone,
                         'portal_mobile': self.partner_id.mobile})
        else:
            return None

    payer_name = fields.Char(default=payer_name_update, string='Payer Name')
    portal_street = fields.Char('Portal Street')
    portal_street2 = fields.Char('Portal Street 2')
    portal_city = fields.Char('Portal City')
    portal_zip = fields.Char('Portal Zip', change_default=True)
    portal_state_id = fields.Many2one("res.country.state", string='State')
    portal_country_id = fields.Many2one('res.country', string='Country')
    portal_phone = fields.Char('Phone', track_visibility='onchange', track_sequence=5)
    portal_mobile = fields.Char('Mobile')

    @api.depends('amount_total', 'residual')
    def to_pay_amount(self):
        for record in self:
            record.update({'to_pay': record.amount_total - record.received_amount})
            return record.amount_total - record.received_amount

    @api.depends('adjustment_amount')
    def final_amount_cal(self):
        for record in self:
            if record.adjustment_type == 'discount':
                record.update({'final_amount': record.to_pay - record.adjustment_amount})
            elif record.adjustment_type == 'premium':
                record.update({'final_amount': record.to_pay + record.adjustment_amount})

    # @api.multi
    # @api.depends('invoice_line_ids.price_subtotal', 'tax_line_ids.amount', 'tax_line_ids.amount_rounding',
    #              'currency_id', 'company_id', 'date_invoice', 'type', 'ks_global_discount_type',
    #              'ks_global_discount_rate')
    # def _compute_amount(self):
    #     for rec in self:
    #         res = super(KsGlobalDiscountInvoice, rec)._compute_amount()

    @api.depends('adjustment_amount')
    def adjust_amount(self):
        for record in self:
            if record.adjustment_type == 'discount':
                record.update({'discount_amount': record.discount_amount + record.adjustment_amount})
                if record.to_pay <= 0:
                    raise ValidationError(_("Discount cannot be applied to paid/zero invoices"))

                elif 0 < record.adjustment_amount <= record.amount_total and record.adjustment_amount <= record.to_pay:

                    # Update Invoice Line Items
                    invoice_line_values = {
                        'residual': record.residual + record.adjustment_amount,
                        'residual_signed': record.residual_signed + record.adjustment_amount,
                        'invoice_line_ids': [(0, 0, {
                            'name': 'Special Discount ' + str(record.adjustment_comment),
                            'origin': record.origin,
                            'account_id': 31,
                            'price_unit': -record.adjustment_amount,
                            'quantity': 1,
                            'uom_id': 1,
                        })],
                    }
                    record.update(invoice_line_values)

                    # Monthly Breakup update
                    for line_item in self.monthly_invoice_ids:
                        if line_item.asn_id == self.assignment_id:
                            line_item.amount_total -= record.adjustment_amount
                            line_item.to_pay -= record.adjustment_amount
                            line_item.special_discount += record.adjustment_amount

                    # Residual Calc
                    residual = 0.0
                    residual_company_signed = 0.0
                    sign = record.type in ['in_refund', 'out_refund'] and -1 or 1
                    for line in record._get_aml_for_amount_residual():
                        residual_company_signed += line.amount_residual
                        if line.currency_id == record.currency_id:
                            residual += line.amount_residual_currency if line.currency_id else line.amount_residual
                        else:
                            if line.currency_id:
                                residual += line.currency_id._convert(line.amount_residual_currency, record.currency_id,
                                                                      line.company_id, line.date or fields.Date.today())
                            else:
                                residual += line.company_id.currency_id._convert(line.amount_residual, record.currency_id,
                                                                                 line.company_id,
                                                                                 line.date or fields.Date.today())
                    record.residual_company_signed = abs(residual_company_signed) * sign
                    record.residual_signed = abs(residual) * sign
                    record.residual = abs(residual)

                    digits_rounding_precision = record.currency_id.rounding
                    if float_is_zero(record.residual, precision_rounding=digits_rounding_precision):
                        record.reconciled = True
                    else:
                        record.reconciled = False
                else:
                    raise ValidationError(_("Adjusting Discount Amount must be: \n 1. Greater than Zero \n 2. Less than required or pending amount "))

                # Customer Transaction Line - Update
                last_outstanding_amount = 0
                last_transaction = self.env['transaction.history.line'].search(
                    [('partner_id', '=', record.partner_id.id), ('currency_id', '=', record.currency_id.id)],
                    order='id desc',
                    limit=1
                )
                if last_transaction:
                    last_outstanding_amount = last_transaction.outstanding_amount

                vals = {
                    'partner_id': record.partner_id.id,
                    'adjustment_amount': record.adjustment_amount,
                    'outstanding_amount': float_round((last_outstanding_amount - record.adjustment_amount), 2),
                    'activity': 'Adjustment - Special Discount ' + record.origin[:-8]
                    if record.origin.endswith('_On-Hold')
                    else 'Adjustment - Special Discount for ' + record.origin
                    if record.partner_id.is_company is False
                    else 'Adjustment - Special Discount for ' + record.number,
                    'date': date.today(),
                    'currency_id': record.currency_id.id
                }

                if record.adjustment_amount > 0:
                    self.env['transaction.history.line'].create(vals)

                record.update({'adjustment_amount': 0,
                               'adjustment_type': '',
                               'adjustment_comment': ''
                               })

            elif record.adjustment_type == 'premium':
                record.update({'premium_amount': record.premium_amount + record.adjustment_amount})
                if 0 < record.adjustment_amount:

                    # Update Invoice Line Items
                    invoice_line_values = {
                        'residual': record.residual + record.adjustment_amount,
                        'residual_signed': record.residual_signed + record.adjustment_amount,
                        'invoice_line_ids': [(0, 0, {
                            'name': 'Special Premium ' + str(record.adjustment_comment),
                            'origin': record.origin,
                            'account_id': 31,
                            'price_unit': record.adjustment_amount,
                            'quantity': 1,
                            'uom_id': 1,
                        })],
                    }
                    record.update(invoice_line_values)

                    # Monthly Breakup update
                    for line_item in self.monthly_invoice_ids:
                        if line_item.asn_id == self.assignment_id:
                            line_item.amount_total += record.adjustment_amount
                            line_item.to_pay += record.adjustment_amount
                            line_item.special_premium += record.adjustment_amount

                    # Residual Calc
                    residual = 0.0
                    residual_company_signed = 0.0
                    sign = record.type in ['in_refund', 'out_refund'] and -1 or 1
                    for line in record._get_aml_for_amount_residual():
                        residual_company_signed += line.amount_residual
                        if line.currency_id == record.currency_id:
                            residual += line.amount_residual_currency if line.currency_id else line.amount_residual
                        else:
                            if line.currency_id:
                                residual += line.currency_id._convert(line.amount_residual_currency, record.currency_id,
                                                                      line.company_id, line.date or fields.Date.today())
                            else:
                                residual += line.company_id.currency_id._convert(line.amount_residual, record.currency_id,
                                                                                 line.company_id,
                                                                                 line.date or fields.Date.today())
                    record.residual_company_signed = abs(residual_company_signed) * sign
                    record.residual_signed = abs(residual) * sign
                    record.residual = abs(residual)
                    digits_rounding_precision = record.currency_id.rounding
                    if float_is_zero(record.residual, precision_rounding=digits_rounding_precision):
                        record.reconciled = True
                    else:
                        record.reconciled = False
                else:
                    raise ValidationError(_("Adjusting Premium Amount must be positive"))

                # Customer Transaction Line - Update
                last_outstanding_amount = 0
                last_transaction = self.env['transaction.history.line'].search(
                    [('partner_id', '=', record.partner_id.id), ('currency_id', '=', record.currency_id.id)],
                    order='id desc',
                    limit=1
                )

                if last_transaction:
                    last_outstanding_amount = last_transaction.outstanding_amount

                vals = {
                    'partner_id': record.partner_id.id,
                    'adjustment_amount': record.adjustment_amount,
                    'outstanding_amount': float_round((last_outstanding_amount + record.adjustment_amount), 2),
                    'activity': 'Adjustment - Premium Addition ' + record.origin[:-8]
                    if record.origin.endswith('_On-Hold')
                    else 'Adjustment - Premium Addition for ' + record.origin
                    if record.partner_id.is_company is False
                    else 'Adjustment - Premium Addition for ' + record.number,
                    'date': date.today(),
                    'currency_id': record.currency_id.id
                }

                if record.adjustment_amount > 0:
                    self.env['transaction.history.line'].create(vals)

                record.update({'adjustment_amount': 0,
                               'adjustment_type': '',
                               'adjustment_comment': '',
                               'assignment_id': '',
                               })

            if record.to_pay == 0:
                record.write({'payment_state': 'paid'})
            elif 0 < record.to_pay < record.amount_total:
                record.write({'payment_state': 'partial'})
            elif record.to_pay == record.amount_total:
                record.write({'payment_state': 'open'})

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.multi
    def zero_invoice_adjust(self):
        for inv_record in self:
            if inv_record.amount_total == 0 and inv_record.adjustment_amount > 0:
                inv_record.update({'adjustment_type': 'premium'})
                inv_record.adjust_amount()
                print('IF called')
            else:
                inv_record.adjust_amount()
                print('Else called')

    unit_id = fields.Many2one('service.unit', string="Unit")
    name_seq = fields.Char("Invoice Reference", required=True,
                           readonly=True, index=True, default=lambda self: _('New'))
    # product_id = fields.Many2one('product.product', 'Product')
    priority = fields.Selection([('standard', 'Standard'),
                                 ('express', 'Express'),
                                 ('super_express', 'Super Express')], 'Priority', default='standard')
    po_number = fields.Char('PO Number', track_visibility='onchange')
    deadline = fields.Datetime('Deadline')
    char_count = fields.Char('Character Count')
    reminder_type = fields.Selection([('polite_mail', 'Polite Reminder Mail'),
                                     ('phone_call', 'Phone Call Reminder'),
                                     ('followup_mail', 'Follow-up Reminder Mail'),
                                     ('strict_mail', 'Strict Reminder Mail'),
                                     ('legal_mail', 'Legal Notice Reminder Mail')],
                                     'Remainder Type', default='polite_mail', required=True)

    @api.one
    def update_due_date(self):
        # for record in self:
        if self.postpone_date:
            self.update({'date_due': self.postpone_date})

            # Email to Client to Notify Revised Payment Deadline
            self.env['mail.trigger'].inv_related_mail(self, 'revised_deadline')
        return True

    # Cancel and set invoice to Draft Stage
    @api.one
    def redraft_invoice(self):
        self.action_invoice_cancel()
        self.action_invoice_draft()

    @api.multi
    def _create_payment_transaction(self, vals):
        '''Similar to self.env['payment.transaction'].create(vals) but the values are filled with the
        current invoices fields (e.g. the partner or the currency).
        :param vals: The values to create a new payment.transaction.
        :return: The newly created payment.transaction record.
        '''
        # Ensure the currencies are the same.
        currency = self[0].currency_id
        if any([inv.currency_id != currency for inv in self]):
            raise ValidationError(_('A transaction can\'t be linked to invoices having different currencies.'))

        # Ensure the partner are the same.
        partner = self[0].partner_id
        if any([inv.partner_id != partner for inv in self]):
            raise ValidationError(_('A transaction can\'t be linked to invoices having different partners.'))

        # Try to retrieve the acquirer. However, fallback to the token's acquirer.
        acquirer_id = vals.get('acquirer_id')
        acquirer = None
        payment_token_id = vals.get('payment_token_id')

        if payment_token_id:
            payment_token = self.env['payment.token'].sudo().browse(payment_token_id)

            # Check payment_token/acquirer matching or take the acquirer from token
            if acquirer_id:
                acquirer = self.env['payment.acquirer'].browse(acquirer_id)
                if payment_token and payment_token.acquirer_id != acquirer:
                    raise ValidationError(_('Invalid token found! Token acquirer %s != %s') % (
                        payment_token.acquirer_id.name, acquirer.name))
                if payment_token and payment_token.partner_id != partner:
                    raise ValidationError(_('Invalid token found! Token partner %s != %s') % (
                        payment_token.partner.name, partner.name))
            else:
                acquirer = payment_token.acquirer_id

        # Check an acquirer is there.
        if not acquirer_id and not acquirer:
            raise ValidationError(_('A payment acquirer is required to create a transaction.'))

        if not acquirer:
            acquirer = self.env['payment.acquirer'].browse(acquirer_id)

        # Check a journal is set on acquirer.
        if not acquirer.journal_id:
            raise ValidationError(_('A journal must be specified of the acquirer %s.' % acquirer.name))

        if not acquirer_id and acquirer:
            vals['acquirer_id'] = acquirer.id

        amount = 0
        for rec in self:
            if rec.advance_payment == '1_99':
                round_curr = rec.currency_id.round
                advance_payment_amount = round_curr((rec.amount_total * rec.advance_payment_value) / 100)
                if vals.get('payment_term') == 'full_payment' or rec.advance_payment_done == True:
                    amount += rec.to_pay
                else:
                    amount += advance_payment_amount
            else:
                amount += rec.to_pay

        vals.update({
            'amount': amount,
            'currency_id': currency.id,
            'partner_id': partner.id,
            'invoice_ids': [(6, 0, self.ids)],
        })

        transaction = self.env['payment.transaction'].create(vals)

        # Process directly if payment_token
        if transaction.payment_token_id:
            transaction.s2s_do_transaction()

        return transaction

    # Due date Remainder Function call with template
    def action_send_due_remainder(self):
        """This is called by a cron job, with the email template message loaded by default"""

        open_invoices = self.env['account.invoice'].search([('state', '=', 'open')])
        print(open_invoices)
        payment_reminder_object = self.env['invoice.payment.reminder'].search([])
        for inv in open_invoices:
            # If send email to client is true in client preference then only send email to them
            if not inv.partner_id.send_email_to_client:
                continue
            due_date = inv.date_due
            for record in payment_reminder_object:
                if (date.today()-due_date).days == record.reminder_days:
                    inv.update({'reminder_type': record.name})
                    ir_model_data = self.env['ir.model.data']
                    try:
                        mail_trigger_obj = self.env['mail.trigger']
                        ctx = mail_trigger_obj.get_email_ids()
                        temp_config_id = self.env['mail.template.config'].search([('active', '=', True)])
                        template_id = self.env['mail.template'].search(
                            [('mail_template_config_id', '=', temp_config_id.id), ('is_configured_template', '=', True),
                             ('template_type_id', '=', self.env.ref("dynamic_mail.payment_temp").id),
                             ('inv_operation_type', '=', record.name)])
                        if template_id:
                            # To get outgoing mail server id
                            mail_server_id = mail_trigger_obj.get_mail_server_id(template_id)
                            email_values = {'mail_server_id': mail_server_id.id if mail_server_id else False}
                            template_id.sudo().with_context(ctx).send_mail(inv.id, force_send=True,
                                                                               raise_exception=True,
                                                                               email_values=email_values)

                        if not template_id:
                            raise ValidationError("Template not found!! Please configure email template "
                                                  "in Configure Mail Templates master to proceed.")
                        # template_id = ir_model_data.get_object_reference('ulatus_cs', 'remainder_mail_template')[1]
                    except ValueError:
                        template_id = False


class AccountInvoiceLineInherit(models.Model):
    _inherit = 'account.invoice.line'

    asn_id = fields.Many2one('assignment', 'Assignment Reference')


class ResCompanyInherit(models.Model):
    _inherit = 'res.company'

    invoice_logo = fields.Binary("Logo", store=True)
    due_remainder_mail = fields.Selection([('after_week', 'After a Week'),], 'Remainder Type', default='after_week')
    no_of_days = fields.Integer('No Of Days')


class InvoicePaymentReminder(models.Model):
    _name = 'invoice.payment.reminder'
    _description = 'Invoice Payment Reminder'

    name = fields.Selection([('polite_mail', 'Polite Reminder Mail'),
                             ('phone_call', 'Phone Call Reminder'),
                             ('followup_mail', 'Follow-up Reminder Mail'),
                             ('strict_mail', 'Strict Reminder Mail'),
                             ('legal_mail', 'Legal Notice Reminder Mail')], 'Remainder Type',
                            default='polite_mail', required=True)
    reminder_days = fields.Integer('Reminder Days')


class MonthlyInvoiceLine(models.Model):
    _name = "monthly.invoice.line"
    _description = "Monthly Invoice Line"
    _order = "id"

    name = fields.Text(string='Description', required=True)
    origin = fields.Char(string='Source Document',
                         help="Reference of the document that produced this invoice.")

    order_id = fields.Many2one('sale.order', 'Order Reference')
    asn_id = fields.Many2one('assignment', 'Assignment Reference')

    sequence = fields.Integer(default=10,
                              help="Gives the sequence of this line when displaying the invoice.")

    partner_id = fields.Many2one('res.partner', string='Project Manager Ref')
    partner_name = fields.Char(string='Project Manager')

    invoice_id = fields.Many2one('account.invoice', string='Invoice Reference',
                                 ondelete='cascade', index=True)

    language_pair = fields.Char('Language Pair')
    currency_id = fields.Many2one('res.currency')
    service_level_id = fields.Many2one('service.level', string='Translation Level')
    deadline = fields.Datetime("Delivery Deadline", track_visibility='onchange', copy=True)
    delivery_date = fields.Datetime("Delivery Deadline", track_visibility='onchange', copy=True)
    char_count = fields.Integer("Character Count")

    translation_fee = fields.Monetary('Translation Fee')
    total_addons_fee = fields.Monetary('Total Addons Fee')
    amount_total = fields.Monetary('Total Fee')
    to_pay = fields.Monetary('To Pay')
    special_discount = fields.Monetary('Discount')
    special_premium = fields.Monetary('Premium')

    priority = fields.Selection([('standard', 'Standard'),
                                 ('express', 'Express'),
                                 ('super_express', 'Super Express')], 'Priority', default='standard')
    po_number = fields.Char('PO Number', track_visibility='onchange')
    unit_id = fields.Many2one('service.unit', string="Unit")
