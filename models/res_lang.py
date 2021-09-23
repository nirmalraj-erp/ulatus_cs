# -*- coding: utf-8 -*-

from odoo import fields, models, api


class ResLang(models.Model):
    _inherit = "res.lang"
    _order = 'name asc'

    initial_code = fields.Char("Initial's Code")
    unit_id = fields.Many2one('service.unit', string="Unit",
    	help="Source Language Unit of Measure")
    code = fields.Char(string='Locale Code', required=False, 
    	help='This field is used to set/get locales for user')
    active = fields.Boolean('active', default=True)
    

    _sql_constraints = [
        ('initial_code_uniq', 'unique(initial_code)', 'The Initial code of the language must be unique !')
    ]

    @api.model
    def create(self, vals):
        if vals.get('initial_code',''):
            vals['code'] = vals.get('initial_code','')
        return super(ResLang, self).create(vals)

    # @api.multi
    # def write(self, vals):
    #     if vals.get('initial_code',''):
    #     	vals['code'] = vals.get('initial_code','')
    #     return super(ResLang, self).write(vals)