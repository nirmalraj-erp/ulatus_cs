# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class UlatusConfigSettings(models.Model):
    _name = 'ulatus.config.settings'
    _description = 'Ulatus Config Settings'

    _disallowed_datetime_patterns = list(tools.DATETIME_FORMATS_MAP)

    product_id = fields.Many2one('product.product', string="Product")
    project_management_cost = fields.Float("Project Cost", default=5)
    recommended_service = fields.Char("Recommended Tool Tip")
    value_added_service = fields.Char("Value Added Tool Tip")
    recommended_label = fields.Char("Recommended Label")
    recommended_tooltip = fields.Char("Recommended Tooltip")
    value_added_label = fields.Char("Value Added Label")
    home_directory = fields.Char('File Store Directory')
    zendesk_script = fields.Text('Zendesk Script')
    question_validity_date = fields.Integer("Question's Validity Date")
    terms_conditions = fields.Text('Terms and Conditions URL')
    privacy_policy = fields.Text('Privacy Policy URL')
    contact_us = fields.Text('Contact Us URL')
    payment_url = fields.Text('Credit Card/PayPal Payment URL')
    delivery_note = fields.Text('Delivery Date Note')
    header_img = fields.Binary("Header Image")
    footer_img = fields.Binary("Footer Image")
    client_img = fields.Binary("Client Image")
    cs_email_id = fields.Char("CS Email ID", required=True, default='cs@example.com')
    py_email_id = fields.Char("PY Email ID", required=True, default='py@example.com')
    pm_email_id = fields.Char("PM Email ID", required=True, default='pm@example.com')
    business_email_id = fields.Char("Business Email ID", required=True, default='business@example.com')
    donotrly_email_id = fields.Char("Do Not Reply Email ID", required=True, default='donotreply@example.com')
    date_format = fields.Char(string='Date Format', required=True, default='%m/%d/%Y')
    report_date_format = fields.Char(string='Date Format', required=True, default='%b %d, %Y')
    time_format = fields.Char(string='Time Format', required=True, default='%H:%M:%S')

    @api.model
    def default_get(self, fields):
        res = super(UlatusConfigSettings, self).default_get(fields)
        last_id = self.search([])
        if last_id:
            res['product_id'] = last_id[-1].product_id.id
            res['project_management_cost'] = last_id[-1]. \
                project_management_cost
            res['recommended_service'] = last_id[-1].recommended_service
            res['value_added_service'] = last_id[-1].value_added_service
            res['recommended_label'] = last_id[-1].recommended_label
            res['recommended_tooltip'] = last_id[-1].recommended_tooltip
            res['value_added_label'] = last_id[-1].value_added_label
            res['home_directory'] = last_id[-1].home_directory
            res['zendesk_script'] = last_id[-1].zendesk_script
            res['terms_conditions'] = last_id[-1].terms_conditions
            res['privacy_policy'] = last_id[-1].privacy_policy
            res['contact_us'] = last_id[-1].contact_us
            res['payment_url'] = last_id[-1].payment_url
            res['delivery_note'] = last_id[-1].delivery_note
            res['question_validity_date'] = last_id[-1].question_validity_date
            res['header_img'] = last_id[-1].header_img
            res['footer_img'] = last_id[-1].footer_img
            res['client_img'] = last_id[-1].client_img
            res['cs_email_id'] = last_id[-1].cs_email_id
            res['py_email_id'] = last_id[-1].py_email_id
            res['pm_email_id'] = last_id[-1].pm_email_id
            res['business_email_id'] = last_id[-1].business_email_id
            res['donotrly_email_id'] = last_id[-1].donotrly_email_id
            res['date_format'] = last_id[-1].date_format.strip()
            res['time_format'] = last_id[-1].time_format.strip()
        return res

    @api.multi
    def execute(self):
        config = self.env['res.config'].next() or {}
        if config.get('type') not in ('ir.actions.act_window_close',):
            return config
        return {
            'type': 'ir.actions.client',
            'tag': 'reload', }

    @api.multi
    def cancel(self):
        # ignore the current record, and send the action to reopen the view
        actions = self.env['ir.actions.act_window'].search(
            [('res_model', '=', self._name)], limit=1)
        if actions:
            return actions.read()[0]
        return {}

    @api.constrains('time_format', 'date_format')
    def _check_format(self):
        for record in self:
            for pattern in record._disallowed_datetime_patterns:
                if (record.time_format and pattern in record.time_format) or \
                        (record.date_format and pattern in record.date_format):
                    raise ValidationError(_('Invalid date/time format directive specified. '
                                            'Please refer to the list of allowed directives.'))
