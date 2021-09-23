# -*- coding: utf-8 -*-

from odoo import api, fields, models


class UpdatePONumber(models.TransientModel):
    _name = "update.po.number"
    _description = "Update PO Number"

    new_po = fields.Char('New PO#')

    @api.multi
    def update_po(self):
        """ Updates PO# in account_invoice """
        self.ensure_one()
        inv_object = self.env['account.invoice'].search([('id', '=', self._context.get('active_ids', [])[0])])
        inv_object.update({'po_number': self.new_po})

        # send email if po number is required set in client preference
        inv_object.send_email_on_inv_generate()
        bi_report = self.env['bi.daily.report'].search(['|', ('parent_asn_id', '=', inv_object.sale_order_id.id), ('asn_id', '=', inv_object.assignment_id.id)])
        if bi_report:
            bi_report.sudo().write({'po_number': self.new_po})

        return {'type': 'ir.actions.act_window_close'}
