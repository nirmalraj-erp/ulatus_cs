# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ClientQuery(models.Model):
    _name = 'client.query'
    _rec_name = 'sr_no'
    _order = 'sr_no desc'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = 'Queries sent by the client'

    sr_no = fields.Char('Sr. no.', index=True, default='New',
                        readonly=True, track_visibility='onchange')
    client_id = fields.Many2one(
        'res.partner', string="Client Name", track_visibility='onchange')
    state = fields.Selection([('pending', 'Pending'), ('respond', 'Responded')
                              ], 'Status', default='pending',
                             track_visibility='onchange')
    query = fields.Text("Instruction", track_visibility='onchange')
    client_response = fields.Text("Client Response", track_visibility='onchange')
    delivery_deadline_date = fields.Datetime(string="Delivery Deadline")
    query_type = fields.Selection([('deadline', 'Deadline'),
                                   ('reference', 'Reference file'),
                                   ('instruction', 'Instruction'),
                                   ('general', 'General')], "Query Type",
                                  default='general')
    child_asn_id = fields.Many2one('assignment', string="Child ASN Ref.")
    parent_asn_id = fields.Many2one('sale.order', string="Parent ASN Ref.")
    client_query_line = fields.One2many("ir.attachment", 'queries_id',
                                        'Client Query Line',
                                        track_visibility='onchange')
    target_lang_ids = fields.Many2many('res.lang', 'res_lang_client_query_rel', 'client_query_id', 'res_lang_id', string="Target language", track_visibility='onchange')
    child_asn_target_lang_id = fields.Many2one('res.lang', string="Target language")
    done_revised_lang_ids = fields.Char('Done revised lang ids')

    # Technical field : use to find out existing client query record while creating from backend
    file_uploader_no = fields.Char('File Uploader No.')

    @api.model
    def create(self, vals):
        if vals.get('sr_no', 'New') == 'New':
            vals['sr_no'] = self.env['ir.sequence'].next_by_code(
                'sr.no') or '/'
        return super(ClientQuery, self).create(vals)

    @api.multi
    def cs_respond(self):
        model = 'file.revision.request.wiz'
        view_id = self.env.ref('ulatus_cs.view_client_response_wiz').id
        return {
            'name': ('Client Response'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': model,
            'view_id': view_id,
            'target': 'new',
        }
