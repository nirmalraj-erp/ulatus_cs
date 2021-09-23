# -*- coding: utf-8 -*-

from odoo import api, models, fields
from odoo.exceptions import UserError
import re


class MailComposer(models.TransientModel):
    _inherit = 'mail.compose.message'
    _description = 'Email composition wizard'

    email_to = fields.Char('To (Emails)', help="Comma-separated recipient addresses (placeholders may be used here)")
    email_cc = fields.Char('Cc', help="Carbon copy recipients (placeholders may be used here)")

    def validate_emails(self):
        """
            Validate emails and confirm that emails are coma separated
        """
        if self.email_to:
            match = re.match(
                '^[\W]*([\w+\-.%]+@[\w\-.]+\.[A-Za-z]{2,4}[\W]*,{1}[\W]*)*([\w+\-.%]+@[\w\-.]+\.[A-Za-z]{2,4})[\W]*$',
                self.email_to)
            if match == None:
                raise UserError('Email-ID is not valid!! OR Only comma separated emails are accepted!!')
        if self.email_cc:
            match = re.match(
                '^[\W]*([\w+\-.%]+@[\w\-.]+\.[A-Za-z]{2,4}[\W]*,{1}[\W]*)*([\w+\-.%]+@[\w\-.]+\.[A-Za-z]{2,4})[\W]*$',
                self.email_cc)
            if match == None:
                raise UserError('Email-ID is not valid!! OR Only comma separated emails are accepted!!')

    @api.multi
    def add_followers(self):
        """ To add partner_id in followers """
        record_id = self.env[self._context.get('active_model')].browse(self._context.get('active_id'))
        mail_invite_id = self.env['mail.wizard.invite'].with_context({
            'default_res_model': self._context.get('active_model'),
            'default_res_id': self._context.get('active_id')
        }).sudo().create({
            'partner_ids': [(4, record_id.partner_id.id)],
            'send_mail': False
        })
        mail_invite_id.add_followers()
        return True

    @api.multi
    def custom_send_mail(self):
        """ Send Quotation Email to the Client and """
        record_id = self.env[self._context.get('active_model')].browse(self._context.get('active_id'))
        # To validate emails
        self.validate_emails()
        email_values = {
            'email_from': self.email_from,
            'email_to': self.email_to,
            'email_cc': self.email_cc,
            'subject': self.subject,
            'body_html': self.body,
        }
        self.env['mail.trigger'].quote_mail(record_id, 'quote_send', email_values)
        return True

    @api.multi
    def action_send_mail(self):
        quote_id = self.env[self._context.get('active_model')].browse(self._context.get('active_id'))
        if self._context.get('custom_mail'):
            vals = quote_id.send_mail_operation()
            self.custom_send_mail()
            self.add_followers()
            quote_id.update_bi_report_data()
            # self.send_mail()
            return vals
        return super(MailComposer, self).action_send_mail()

    @api.multi
    def cancel_send_mail(self):
        quote_id = self.env[self._context.get('active_model')].browse(self._context.get('active_id'))
        return quote_id.send_mail_operation()
