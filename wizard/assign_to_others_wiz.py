# -*- coding: utf-8 -*-

from odoo import fields, models, api, _


class AssignInquiryWiz(models.TransientModel):
    _name = 'assign.others.wiz'
    _description = 'Assign others Wizard'

    user_id = fields.Many2one('res.users', string="User",
                              domain=lambda self:
                              [("groups_id", "in",
                                (self.env.ref("ulatus_cs.group_cs_user").id,
                                 self.env.ref("ulatus_cs.group_cs_manager").id,
                                 self.env.ref("ulatus_cs.group_cs_admin").id),
                                )])
    inquiry_id = fields.Many2one('sale.order', string="Inquiry")

    @api.multi
    @api.onchange('user_id')
    def onchange_user_id(self):
        title = False
        result = {}
        message = False
        warning = {}
        if self.user_id.partner_id.new_inquiry_count > 10:
            title = _("Warning for %s") % self.user_id.name
            message = "The user already assigned more then 10 Inquiries."
            warning['title'] = title
            warning['message'] = message
            result = {'warning': warning}
        return result

    @api.multi
    def assign_to_user(self):
        active_id = self._context.get('active_id')
        if self._context.get('inquiry_id'):
            active_id = self._context.get('inquiry_id')
        active_model = self._context.get('active_model')
        param = self.env['ir.config_parameter']
        url_rec = param.search([('key', '=', 'web.base.url')])
        rec_id = self.env[active_model].browse(int(active_id))
        values = {'user_id': self.user_id.id}
        if self._context.get('inquiry_id'):
            action_id = self.env.ref(
                'ulatus_cs_dashboard.action_ulatus_dashboard').id
            url = url_rec.value + '/web#action=' + str(action_id)
            values.update({'state': 'draft', 'type': 'inquiry',
                           'inquiry_state': 'assign', 'pending_notification_sent': True,})
        elif active_model == 'sale.order' and rec_id.inquiry_state == \
                'un_assign' and rec_id.type == 'inquiry':
            action_id = self.env.ref('ulatus_cs.action_client_inquiry').id
            url = url_rec.value + '/web#action=' + str(action_id) +\
                "&model=sale.order" + "&view_type=list"
            values.update({'state': 'draft', 'type': 'inquiry',
                           'inquiry_state': 'assign', 'pending_notification_sent': True})
        elif active_model == 'sale.order' and rec_id.state == \
                'revision_request' and rec_id.type == 'quotation':
            # For access rights : make inquiry and revision history visible to current working user
            # 1. inquiry form
            revise_dict = {}
            inquiry_id = self.env['sale.order'].sudo().browse(rec_id.inquiry_id.id)
            if not inquiry_id.r_user_id:
                revise_dict.update({'r_user_id': inquiry_id.user_id.id})
            revise_dict.update({'user_id': self.user_id.id})
            rec_id.inquiry_id.sudo().write(revise_dict)
            # 2. revision history
            query = """SELECT id
                       FROM sale_order
                       WHERE main_quotation_id = %s
                    """ % str(rec_id.id)
            self.env.cr.execute(query)
            revise_inq_ids = self.env.cr.fetchall()
            revise_inq_ids = revise_inq_ids and [x[0] for x in revise_inq_ids] or []
            revise_ids = self.env['sale.order'].sudo().browse(revise_inq_ids)
            for revise_id in revise_ids:
                revise_his_dict = {}
                if not revise_id.r_user_id:
                    revise_his_dict.update({'r_user_id': revise_id.user_id.id})
                revise_his_dict.update({'user_id': self.user_id.id})
                revise_id.sudo().write(revise_his_dict)

            values.update({'inquiry_state': 'process'})
            action_id = self.env.ref(
                'ulatus_cs.action_cs_quotation_revision').id
            url = url_rec.value + '/web#action=' + \
                str(action_id) + "&model=sale.order" + "&view_type=list"
        rec_id.write(values)
        return {'name': ' ',
                'res_model': 'ir.actions.act_url',
                'type': 'ir.actions.act_url',
                'target': 'self',
                'url': url,
                }
