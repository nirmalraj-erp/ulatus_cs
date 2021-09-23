# coding: utf-8

from odoo import _, api, fields, models
import datetime
from odoo.tools import float_round
from odoo.exceptions import ValidationError
import xlsxwriter
import xlrd
import base64

MAP_INVOICE_TYPE_PARTNER_TYPE = {
    'out_invoice': 'customer',
    'out_refund': 'customer',
    'in_invoice': 'supplier',
    'in_refund': 'supplier',
}

# Since invoice amounts are unsigned, this is how we know if money comes in or goes out
MAP_INVOICE_TYPE_PAYMENT_SIGN = {
    'out_invoice': 1,
    'in_refund': -1,
    'in_invoice': -1,
    'out_refund': 1,
}


class AccountPaymentAbstract(models.AbstractModel):
    _inherit = 'account.abstract.payment'

    @api.multi
    def _compute_payment_amount(self, invoices=None, currency=None):
        '''Compute the total amount for the payment wizard.

        :param invoices: If not specified, pick all the invoices.
        :param currency: If not specified, search a default currency on wizard/journal.
        :return: The total amount to pay the invoices.
        '''

        # Get the payment invoices
        if not invoices:
            invoices = self.invoice_ids

        # Get the payment currency
        payment_currency = currency
        if not payment_currency:
            payment_currency = self.currency_id or self.journal_id.currency_id or self.journal_id.company_id.currency_id or invoices and \
                               invoices[0].currency_id

        # Avoid currency rounding issues by summing the amounts according to the company_currency_id before
        # invoice_datas = invoices.read_group(
        #     [('id', 'in', invoices.ids)],
        #     ['currency_id', 'type', 'residual_signed', 'residual_company_signed'],
        #     ['currency_id', 'type'], lazy=False)
        total = 0.0
        for invoice_id in invoices:
            sign = MAP_INVOICE_TYPE_PAYMENT_SIGN[invoice_id.type]
            amount_total = sign * invoice_id.to_pay
            amount_total_company_signed = sign * invoice_id.to_pay
            # invoice_currency = self.env['res.currency'].browse(invoice_data['currency_id'][0])
            # if payment_currency == invoice_currency:
            total += amount_total
            # else:
            #     # Here there is no chance we will reconcile on amount_currency
            #     # Hence, we need to compute with the amount in company currency as the base
            #     total += self.journal_id.company_id.currency_id._convert(
            #         amount_total_company_signed,
            #         payment_currency,
            #         self.env.user.company_id,
            #         self.payment_date or fields.Date.today()
            #     )
        # print('*********************************************', invoice_datas)
        # for invoice_data in invoice_datas:
        #     print(invoice_data)
        #     sign = MAP_INVOICE_TYPE_PAYMENT_SIGN[invoice_data['type']]
        #     print('*********************************************', invoice_data['to_pay'])
        #     amount_total = sign * invoice_data['to_pay']
        #     amount_total_company_signed = sign * invoice_data['to_pay']
        #     invoice_currency = self.env['res.currency'].browse(invoice_data['currency_id'][0])
        #     if payment_currency == invoice_currency:
        #         total += amount_total
        #     else:
        #         # Here there is no chance we will reconcile on amount_currency
        #         # Hence, we need to compute with the amount in company currency as the base
        #         total += self.journal_id.company_id.currency_id._convert(
        #             amount_total_company_signed,
        #             payment_currency,
        #             self.env.user.company_id,
        #             self.payment_date or fields.Date.today()
        #         )

        return total


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    payment_control = fields.Selection([('invoice', 'Invoice Level'),
                                        ('asn', 'ASN Level')
                                        ], string='Payment Control', default='invoice')

    monthly_payment_ids = fields.One2many('monthly.payment.line', 'payment_id', string='Monthly Invoice Lines',
                                          readonly=True, copy=True)

    upload_file = fields.Binary(string='Upload your file')

    def action_validate_invoice_payment(self):
        """ 1. To off-hold asn if asn is put 0n-hold.
        2. To send payment received email to client """
        res = super(AccountPayment, self).action_validate_invoice_payment()
        for record in self:
            for invoice_id in record.invoice_ids:
                # Calculation overwrite
                invoice_id.received_amount = invoice_id.received_amount + self.amount
                if 0 < self.amount <= invoice_id.to_pay:
                    invoice_id.to_pay = invoice_id.amount_total - invoice_id.received_amount
                elif self.amount > invoice_id.to_pay:
                    invoice_id.to_pay = 0
                else:
                    raise ValidationError("Please enter a valid payment value")

                # Residual Update
                invoice_id.update({'residual': invoice_id.to_pay})

                # Update Parent ASN(sale_order) status to wip if asn is on on-hold
                # Update RR ASN(assignment) status to wip if asn is on on-hold

                if invoice_id.sale_order_id:
                    order = self.env['sale.order'].sudo().search([("id", "=", invoice_id.sale_order_id.id)])
                elif invoice_id.assignment_id:
                    order = self.env['assignment'].sudo().search([("id", "=", invoice_id.assignment_id.id)])
                else:
                    order = None

                if order:
                    round_curr = invoice_id.currency_id.round
                    if order.advance_payment == '100' and invoice_id.to_pay == 0:
                        self.off_hold_process(order, invoice_id)
                        invoice_id.write({'advance_payment_done': True})
                    elif order.advance_payment == '1_99':
                        advance_payment_amount = round_curr((invoice_id.amount_total * invoice_id.advance_payment_value) / 100)
                        if advance_payment_amount and invoice_id.received_amount >= advance_payment_amount:
                            self.off_hold_process(order, invoice_id)
                            invoice_id.write({'advance_payment_done': True})

                last_outstanding_amount = 0
                last_transaction = self.env['transaction.history.line'].search(
                    [('partner_id', '=', invoice_id.partner_id.id), ('currency_id', '=', invoice_id.currency_id.id)],
                    order='id desc',
                    limit=1
                )
                if last_transaction:
                    last_outstanding_amount = last_transaction.outstanding_amount

                vals = {
                    'partner_id': self.partner_id.id,
                    'payment_id': self.id,
                    'payment_amount': self.amount,
                    'outstanding_amount': float_round((last_outstanding_amount - self.amount), 2),
                    'activity': 'Payment for ' + (invoice_id.origin[:-8] if invoice_id.origin.endswith('_On-Hold') else invoice_id.origin)
                    if invoice_id.partner_id.is_company is False else invoice_id.number + ' via ' + self.journal_id.name,
                    'date': self.payment_date,
                    'currency_id': self.currency_id.id
                }
                self.env['transaction.history.line'].create(vals)

                if invoice_id.to_pay == 0:
                    invoice_id.write({'payment_state': 'paid'})
                    monthly_line_items = self.env['monthly.invoice.line'].search([('invoice_id', '=', invoice_id.id)])
                    for line_item in monthly_line_items:
                        line_item.update({'to_pay': 0})
                elif 0 < invoice_id.to_pay < invoice_id.amount_total:
                    invoice_id.write({'payment_state': 'partial'})
                # Send email to inform payment is received to client
                self.env['mail.trigger'].sudo().inv_related_mail(invoice_id, 'pay_received')

        if self.payment_control == 'asn':
            # File Handling
            workbook = xlrd.open_workbook(file_contents=base64.decodestring(self.upload_file))
            worksheet_premium = workbook.sheet_by_name('payment')
            first_row = []  # The row where we stock the name of the column
            for col in range(worksheet_premium.ncols):
                first_row.append(worksheet_premium.cell_value(0, col))
            # transform the workbook to a list of dictionaries
            data = []
            for row in range(1, worksheet_premium.nrows):
                elm = {}
                for col in range(worksheet_premium.ncols):
                    elm[first_row[col]] = worksheet_premium.cell_value(row, col)
                data.append(elm)
            search_invoice_monthly_line = self.env['monthly.invoice.line'].search([('to_pay', '>', 0)])
            for item in data:
                for invoice_line in search_invoice_monthly_line:
                    if item['asn_no'] == invoice_line.asn_id.name:
                        if invoice_line.to_pay >= item['payment'] > 0:
                            invoice_line.to_pay -= item['payment']

        return res

    def off_hold_process(self, order, invoice):
        state = 'asn_work_in_progress'
        if order.state == 'on-hold':
            if order._name == 'sale.order':
                state = 'asn_work_in_progress'
            elif order._name == 'assignment':
                state = order.previous_state

            name = str(order.name)
            if name.endswith('_On-Hold'):
                name = name[:-8]
            order.write({
                'state': state,
                'name': name,
                'received_on_pm': datetime.datetime.now()
            })

            bi_report = self.env['bi.daily.report'].search(['|',('parent_asn_id', '=', order.id), ('asn_id', '=', order.id)])
            if bi_report:
                bi_report.sudo().write({'asn_number': name,'asn_state': state})

            # Invoice update
            if invoice:
                invoice.write({'origin': name})

            # Send emails
            self.trigger_mails(order, invoice)

            if order._name == 'sale.order' and order.child_asn_line:
                for child in order.child_asn_line:
                    cname = str(child.name)
                    if child.name.endswith('_On-Hold'):
                        cname = cname[:-8]
                    child.write({
                        'state': child.previous_state,
                        'name': cname,
                        'received_on_pm': datetime.datetime.now()
                    })
                    if invoice.advance_payment != '0' and not invoice.advance_payment_done:
                        child.write({'initial_received_on_pm': datetime.datetime.now()})
                        # Send email to PM team as soon as the child ASN is moved to PM
                        self.env['mail.trigger'].sudo().pm_mail(child, 'asn_last_line')
                    bi_report = self.env['bi.daily.report'].search([('asn_id', '=', child.id)])
                    if bi_report:
                        bi_report.sudo().write({'asn_number': cname, 'asn_state': state})
        return True

    def trigger_mails(self, order, invoice):
        """ To send all order related mails """
        if order._name == 'sale.order':
            # send email to inform asn is off_hold
            self.env['mail.trigger'].sudo().asn_mail(order, False, 'off_hold')
            # # send email to inform asn is in_progress
            # self.env['mail.trigger'].sudo().asn_mail(order, False, 'in_progress')
        elif order._name == 'assignment':
            # send email to inform revision asn is off_hold
            self.env['mail.trigger'].sudo().asn_mail(False, order, 'off_hold')
            # # send email to inform revision asn is in_progress
            # self.env['mail.trigger'].sudo().asn_mail(False, order, 'in_progress')
            if invoice.advance_payment != '0' and not invoice.advance_payment_done:
                order.write({'initial_received_on_pm': datetime.datetime.now()})
                # Send email to PM team as soon as the child ASN is moved to PM
                self.env['mail.trigger'].sudo().pm_mail(order, 'asn_last_line')
        return True
    #
    # @api.multi
    # @api.onchange('payment_control')
    # def fetch_monthly_asn_data(self):
    #     print('Monthly Data----------------------', self.invoice_ids)
    #     for invoice_id in self.invoice_ids:
    #         if invoice_id.state == 'open' and invoice_id.inv_type == 'mon':
    #             print('Monthly Data----------------------', self.invoice_ids.monthly_invoice_ids)
    #             # monthly_ids = self.env['monthly.invoice.line'].search('id', 'in', invoice_id.monthly_invoice_ids.ids)
    #             # print('IDS--------------------', monthly_ids)
    #             for monthly_id in self.invoice_ids.monthly_invoice_ids:
    #                 print('IDS--------------------', monthly_id)
    #                 # Monthly invoice line items
    #                 monthly_line_values = {
    #                     'monthly_payment_ids': [(0, 0, {
    #                         'name': monthly_id.name,
    #                         'asn_id': monthly_id.asn_id.id,
    #                         'partner_id': monthly_id.partner_id.id,
    #                         'amount_total': monthly_id.amount_total,
    #                         'to_pay': monthly_id.to_pay,
    #                         'unit_id': monthly_id.unit_id.id,
    #                         'currency_id': monthly_id.currency_id.id,
    #                     })],
    #                 }
    #                 self.update(monthly_line_values)
    #                 # self.env['account.payment'].search([('id', '=', self.id)]).update(monthly_line_values)


class MonthlyPaymentLine(models.Model):
    _name = "monthly.payment.line"
    _description = "Monthly Invoice Line"
    _order = "id"

    name = fields.Text(string='Description', required=True)

    order_id = fields.Many2one('sale.order', 'Order Reference')
    asn_id = fields.Many2one('assignment', 'Assignment Reference')

    sequence = fields.Integer(default=10,
                              help="Gives the sequence of this line when displaying the invoice.")

    partner_id = fields.Many2one('res.partner', string='Project Manager')

    payment_id = fields.Many2one('account.payment', string='Invoice Reference',
                                 ondelete='cascade', index=True)

    currency_id = fields.Many2one('res.currency')
    amount_total = fields.Monetary('Total Fee')
    to_pay = fields.Monetary('To Pay')
