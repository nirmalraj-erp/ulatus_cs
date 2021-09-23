# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError


class UpdateServiceLevelWiz(models.TransientModel):
    _name = 'update.service.level.wiz'
    _description = 'Update Translation Level Wiz'

    service_level_wiz_line = fields.One2many("update.service.level.wiz.line",
                                             "service_level_wiz_id",
                                             "Translation Level Wiz Line")

    @api.model
    def default_get(self, fields):
        res = super(UpdateServiceLevelWiz, self).default_get(fields)
        lines = []
        active_id = self._context.get('active_id')
        active_model = self._context.get('active_model')
        quotation_id = self.env[active_model].browse(active_id)
        # if 'service_level_wiz_line' in fields:
        #     lines.append((0, 0, {
        #         'quality_assurance_id': 23,
        #     }))
        #     res.update({'service_level_line': lines})
        return res

    @api.onchange('service_level_wiz_line')
    def onchange_service_level_wiz_line(self):
        service_dict = {}
        visible_service_count = len(list(filter(lambda service:
                                                service.visible_to_client,
                                                self.service_level_wiz_line)))
        if visible_service_count > 3:
            raise UserError(_("You cannot select more than 3 Translation Services!"))
        for service in self.service_level_wiz_line:
            ser = service.service_level_id
            if ser:
                service.visible_to_client = True
            if ser.id in service_dict.keys():
                raise ValidationError(_("You can not select duplicate translation level!"))
            else:
                service_dict.update({ser.id: False})
            if service.reccommend:
                if service.reccommend in service_dict.values():
                    raise ValidationError(_(
                        "Already recommended on 1 translation level,"
                        " Please uncheck other if you wish to recommend this"
                        " one!"))
                service_dict.update({ser.id: service.reccommend})

    @api.multi
    def update_service_level(self):
        translation_list = list(filter(lambda service:
                    service.visible_to_client,
                    self.service_level_wiz_line))
        visible_service_count = len(translation_list)
        if visible_service_count > 3:
            raise UserError(_("You can not select more than 3 Translation Level!"))
        if visible_service_count < 1:
            raise UserError(_("Please select at least 1 Translation Level!"))
        active_id = self._context.get('active_id')
        active_model = self._context.get('active_model')
        quotation_id = self.env[active_model].browse(active_id)
        # quotation_id.order_line.update({'service_level_line': [(6, 0, [])]})
        quotation_id.order_line.mapped('service_level_line').unlink()
        service_lines = [(0, 0, {'service_level_id': rec.service_level_id.id,
                                 'reccommend': rec.reccommend,
                                 # 'fee': rec.service_level_id.price,
                                 'visible_to_client': rec.visible_to_client})
                         for rec in self.service_level_wiz_line]
        quotation_id.order_line.update({'service_level_line': service_lines})
        end_client = ''
        membership_id = ''
        if quotation_id.end_client_id:
            end_client = """ AND end_client_id = """ + str(quotation_id.end_client_id.id)
        if quotation_id.mem_id:
            membership_id = """ AND membership_id = """ + str(quotation_id.mem_id.id)
        # else:
        #     org_id = "is null"
        # + """ AND target_lang_id in """ + (
        #     ",".join(map(str, [quotation_id.target_lang_ids.ids]))) \
        # + """ AND translation_level_id in """ + (",".join(
        #     map(str, [x.service_level_id.id for x in translation_list]))) \
        translation_fee_query = """select id from fee_master where
            source_lang_id=""" + str(quotation_id.source_lang_id.id)\
            + """ AND currency_id = """ + str(quotation_id.currency_id.id)\
            + """ AND priority = '""" + str(quotation_id.priority) + """'"""\
            + """ AND product_id = """ + str(quotation_id.product_id.id)
        self.env.cr.execute(translation_fee_query)
        fee_ids = [x[0] for x in self.env.cr.fetchall()]
        # if not fee_ids:
        #     raise UserError(
        #         _("No fee master setup please contact CS Admin to configure!"))
        if fee_ids:
            ids_str = ' AND id IN ' + str(tuple(fee_ids))
            if len(fee_ids) == 1:
                ids_str = ' AND id = ' + str(fee_ids[0])
            for line in quotation_id.order_line.mapped('service_level_line'):
                translation_fee = """select price from fee_master where
                    target_lang_id=""" + str(line.sale_service_line_id.target_lang_id.id) \
                    + """ AND translation_level_id = """ + str(line.service_level_id.id) \
                    + ids_str + end_client + membership_id
                self.env.cr.execute(translation_fee)
                fee = self.env.cr.fetchone()
                if not fee:
                    translation_fee = """select price from fee_master where
                    target_lang_id=""" + str(line.sale_service_line_id.target_lang_id.id) \
                    + """ AND translation_level_id = """ + str(line.service_level_id.id) \
                    + ids_str + \
                    """ AND end_client_id is Null AND organization_id is Null """
                    self.env.cr.execute(translation_fee)
                    fee = self.env.cr.fetchone()
                    # if not fee:
                    #     raise UserError(
                    #         _("No fee master setup please contact CS Admin to configure!"))
                if fee:
                    line.update({'unit_rate': fee[0] or 0.0,
                                 'fee': fee[0] *
                                 line.sale_service_line_id.character_count})
        quotation_id.onchange_final_deadline()
        return True


class UpdateServiceLevelWizLine(models.TransientModel):
    _name = 'update.service.level.wiz.line'
    _description = 'Update Translation Level Wiz Line'

    service_level_wiz_id = fields.Many2one(
        'update.service.level.wiz', string="Translation Level Wiz")
    service_level_id = fields.Many2one('service.level', string="Translation level")
    reccommend = fields.Boolean("Recommended")
    visible_to_client = fields.Boolean("Visible To Client")
