# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError, UserError

class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100,
                     name_get_uid=None):
        product = super(ProductProduct, self)._name_search(
            name, args, operator=operator, limit=limit,
            name_get_uid=name_get_uid)
        ctx = self._context.copy()
        if ctx.get('product_id', False):
            query = """select addons_id from product_addons_ref where
                                 product_id = '%s'
                               """ % ctx.get('product_id')
            self.env.cr.execute(query)
            addons_ids = [res_id[0] for res_id in self.env.cr.fetchall()]
            domain = [('id', 'in', addons_ids)]
            res = self.search(domain + args, limit=limit)
            return res.name_get()
        return product

    product_bool = fields.Boolean("Product Bool")
    addons_service_bool = fields.Boolean("Add-ons Services")
    enter_unit = fields.Boolean("Enter Unit")
    unit_id = fields.Many2one('service.unit', string="Unit")
    translation_level_ids = fields.Many2many('service.level',
                                             'product_trans_ref', 'product_id',
                                             'translation_id',
                                             string="Translation Level")
    addons_ids = fields.Many2many('product.product', 'product_addons_ref',
                                  'product_id', 'addons_id', string="Add-ons")
    tooltip = fields.Text("Tool Tip")
    static_content_in_email = fields.Text("Static Content In Email")
    addons_technical_field = fields.Char("Technical field for BI Report")

    @api.model
    def create(self, vals):
        if (vals.get('addons_service_bool',False) or vals.get('product_bool', False)) and vals.get('name',''):
            duplicate = self.search([('name','ilike',vals.get('name')),
                ('addons_service_bool','=',vals.get('addons_service_bool',False)),
                ('product_bool', '=', vals.get('product_bool', False))])
            if duplicate:
                raise ValidationError("Record already exists!")
        vals['taxes_id'] = vals['supplier_taxes_id'] = [(6, 0, [])]
        return super(ProductProduct, self).create(vals)

    @api.multi
    def write(self, vals):
        res = super(ProductProduct, self).write(vals)
        for rec in self:
            if (rec.addons_service_bool or rec.product_bool) and vals.get('name',''):
                duplicate = self.search([('name','ilike',vals.get('name')),
                ('addons_service_bool','=',rec.addons_service_bool),
                ('product_bool', '=', rec.product_bool),('id','!=', rec.id)])
            
                if duplicate:
                    raise ValidationError("Record already exists!")
        return res


    @api.model
    def fields_view_get(self, view_id=None, view_type='tree', toolbar=False,
                        submenu=False):
        toolbar = False
        return super(ProductProduct, self).fields_view_get(view_id=view_id,
                                                           view_type=view_type,
                                                           toolbar=toolbar,
                                                           submenu=submenu)
