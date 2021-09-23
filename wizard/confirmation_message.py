# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from datetime import date, datetime
import logging
_logger = logging.getLogger(__name__)


class ConfirmationMessage(models.TransientModel):
    _name = 'confirmation.message'
    _description = 'Confirmation Message'

    message = fields.Char(string="Message", readonly=True)
    mem_id = fields.Many2one('membership.master', string="MEMID")
    send_reminder = fields.Boolean("Send Reminder?", default=False)
    send_reminder_count = fields.Char(string="Reminders sent", readonly=True, default=lambda self: self._context.get('send_reminder_count', False))
    is_reminder_sent = fields.Integer(string="Is Reminder Sent", readonly=True,
                                      default=lambda self: self._context.get('is_reminder_sent', False))

    @api.multi
    def update_memid(self):
        active_id = self._context.get('active_id')
        active_model = self._context.get('active_model')
        res_id = self.env[active_model].browse(active_id)
        org_rec = res_id.partner_id.organization_line.filtered(lambda line: line.is_active)
        if not self.mem_id:
            raise ValidationError(_('Please select MEMID!'))
        if org_rec:
            org_rec.update({'is_active': False})
        # membership_id = self._context.get('membership_id', False)
        # membership_id = self.env['membership.master'].browse(membership_id)
        membership_id = self.mem_id
        if res_id.domain_id.id in membership_id.domain_ids.ids \
                    and res_id.organization_id.id in membership_id.organization_ids.ids:
            _logger.info("Both Matched:::::::%s", res_id.partner_id)
            if self._context.get('domain', False):
                membership_id.update({'organization_ids':[(4,res_id.organization_id.id)]})
                res_id.organization_id.update({'active_memid': membership_id.id})
            elif self._context.get('organization', False):
                membership_id.update({'domain_ids':[(4,res_id.domain_id.id)]})
                
            organization_line = [(0, 0, {'membership_id': membership_id.id,
                                         'organization_id': res_id.organization_id,
                                         'domain_id': res_id.domain_id,
                                         'is_active': True})]
            res_id.partner_id.update({'active_memid': membership_id.id,
                                    'membership_id': membership_id.name,
                                    'parent_id': res_id.organization_id.id,
                                    'organization_line': organization_line})

        elif res_id.domain_id:
            _logger.info("Only domain Matched::::::%s", res_id.partner_id)
            if res_id.organization_name and not res_id.organization_id:
                organization_id = self.env['res.partner'].create({
                    'name': res_id.organization_name,
                    'type': 'contact',
                    'is_portal': True,
                    'is_company': True,
                    'active_memid': membership_id.id,
                    'membership_id': membership_id.name,
                    'website_published':True})
                membership_id.update({'organization_ids':[(4,organization_id.id)]})
            else:
                organization_id = False
            organization_line = [(0, 0, {
                'membership_id': membership_id.id,
                'domain_id': res_id.domain_id.id,
                'organization_id': organization_id.id if organization_id else False,
                'is_active': True})]
            res_id.partner_id.update({'active_memid': membership_id.id,
                                    'membership_id': membership_id.name,
                                    'parent_id': organization_id.id if organization_id else False,
                                    'organization_line': organization_line})

        elif res_id.organization_id:
            _logger.info("Only organization Matched::::%s", res_id.partner_id)
            if res_id.domain_id:
                domain_id = res_id.domain_id
            else:
                domain_id = self.env['org.domain'].create(
                    {'name': res_id.partner_id.email.split('@')[1].lower()})
                membership_id.update({'domain_ids':[(4,domain_id.id)]})
            organization_line = [(0, 0, {'membership_id': membership_id.id,
                                         'domain_id': domain_id.id,
                                         'organization_id': res_id.organization_id.id,
                                         'is_active': True})]
            res_id.partner_id.update({'active_memid': membership_id.id,
                                    'membership_id': membership_id.name,
                                    'parent_id': res_id.organization_id.id if res_id.organization_id else False,
                                    'organization_line': organization_line})

        # To fetch billing details from organization
        if res_id.partner_id.parent_id:
            res_id.partner_id.update_billing_details(res_id.partner_id.parent_id)

        return res_id.process()

    @api.multi
    def create_memid(self):
        active_id = self._context.get('active_id')
        active_model = self._context.get('active_model')
        res_id = self.env[active_model].browse(active_id)
        # org_rec = res_id.partner_id.organization_line.filtered(lambda line: line.is_active)
        # if org_rec:
        #     org_rec.update({'is_active': False})
        # membership_id = self._context.get('membership_id', False)
        # membership_id = self.env['membership.master'].browse(membership_id)
        # permanent_memid = res_id.partner_id.membership_id[1:]
        # membership_id = self.env['membership.master'].create({
        #     'name': permanent_memid,
        #     'client_id': res_id.partner_id.id})
        # organization_line = [(0, 0, {'membership_id': membership_id.id,
        #                              # 'domain_id': domain_id.id,
        #                              # 'organization_id': res_id.organization_id.id,
        #                              'is_active': True})]
        # res_id.partner_id.update({'active_memid': membership_id.id,
        #                           'membership_id': membership_id.name,
        #                           'new_client': False,
        #                           # 'parent_id': res_id.organization_id.id if res_id.organization_id else False,
        #                           'organization_line': organization_line})
        return res_id.process()

    @api.multi
    def sent_confirmation_message(self):
        active_id = self._context.get('active_id')
        active_model = self._context.get('active_model')
        res_id = self.env[active_model].browse(active_id)
        param = self.env['ir.config_parameter']
        url_rec = param.search([('key', '=', 'web.base.url')])
        if active_model == 'sale.order' and res_id.state in ['sent', 'revise']:
            res_id.write({'send_reminder_datetime': datetime.now(),
                          'send_reminder_count': self._context.get('send_reminder_count') + 1,
                          'is_reminder_sent': 1
                        })

            action_id = self.env.ref('ulatus_cs.action_pending_quotation_order').id
            # action_id = self._context.get('params')['action']
            if self._context.get('view_type_flag') == 'pending_quote_form':
                url = url_rec.value + '/web#id=' + str(active_id) + '&action=' + str(
                    action_id) + "&model=sale.order&view_type=form"
            elif self._context.get('view_type_flag') == 'all_quote_form':
                action_id = self.env.ref('ulatus_cs.action_all_quotation_order').id
                url = url_rec.value + '/web#id=' + str(active_id) + '&action=' + str(
                    action_id) + "&model=sale.order&view_type=form"
            else:
                url = url_rec.value + '/web#action=' + str(
                    action_id) + "&model=sale.order" + "&view_type=list"
        self.env['mail.trigger'].quote_mail(res_id, 'quote_reminder', {})
        #     mail_template = self.env.ref(
        #         'dynamic_mail.mail_template_send_quote_pending_reminder_to_client'
        #         )
        # if mail_template:
        #     if res_id.id:
        #         base_url = param.sudo().get_param('web.base.url')
        #         delivery_url = base_url + "/page/quotations_details/%s"\
        #             % res_id.id
        #         try:
        #             mail_template.sudo().with_context(
        #                 delivery_url=delivery_url).send_mail(
        #                 res_id.id, force_send=True, raise_exception=True)
        #         except Exception:
        #             raise ValidationError(_(
        #                 'Please contact your Admin for Configure your system '
        #                 'outging mail server!'))
        return {'name': ' ',
                'res_model': 'ir.actions.act_url',
                'type': 'ir.actions.act_url',
                'target': 'self',
                'url': url,
                }
