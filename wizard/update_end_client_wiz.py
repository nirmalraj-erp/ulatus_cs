# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import math


class UpdateEndClientWiz(models.TransientModel):
    _name = 'update.end.client.wiz'
    _description = 'Update End-client Wizard'

    order_id = fields.Many2one("sale.order", "Sale Order")
    end_client_id = fields.Many2one('res.partner', string="End Client")

    @api.onchange('end_client_id')
    def onchange_as_service_ids(self):
        """
            Apply domain on end_client_id field
            :return: domain
        """
        domain = {}
        if self.order_id.partner_id.active_memid.end_client_ids:
            domain.update({
                'end_client_id': [('id', 'in', self.order_id.partner_id.active_memid.end_client_ids.ids)]
            })
        else:
            domain.update({
                'end_client_id': [('id', '=', False)]
            })
        return {
            'domain': domain
        }

    def update_end_client(self):
        """
            1. Update end client value on inquiry or quotation
            2. Update instructions when end client is added/updated/removed
            3. Update weighted % in language pairs when end client is added/updated/removed
            4. Update fee in translation level's when end client is added/updated/removed
            5. Update add-ons fee when end client is added/updated/removed
            :return: True
        """
        # 1. Update end client
        if self.end_client_id:
            self.order_id.write({'end_client_id': self.end_client_id.id})
        else:
            self.order_id.write({'end_client_id': False})
        # 2. Update instructions
        self.update_instructions()
        # 3. Update weighted %
        self.update_weighted_percent()
        # 4. Update fee in translation level's
        self.update_fee()
        # 5. Update add-ons fee
        self.update_addons_fee()
        # # 6. Update area type, subject areas, product
        self.update_area_type()
        return True

    def update_instructions(self):
        """
            Update instructions when end client is added/updated/removed
            :return: True
        """
        if self.order_id.order_line:
            # Remove previous instructions
            self._cr.execute("""DELETE FROM sale_instruction_line 
                                WHERE (order_id = %s OR ins_line_id in %s) AND is_default_ins = true""",
                             (str(self.order_id.id), self.order_id.order_line._ids))

            # To add default instructions in inquiry
            ins_config_ids = self.env['instruction.config'].search([])
            if ins_config_ids:
                default_ins = self.order_id.default_instruction()
                order_line = [(1, line.id, {'sale_instruction_line': default_ins}) for line in self.order_id.order_line]
                self.order_id.write({
                    'order_line': order_line,
                    'instruction_line': default_ins
                })
        return True

    def update_weighted_percent(self):
        """
            Update weighted % in language pairs
            :return: True
        """
        memsource_line_ids = self.order_id.order_line.mapped('memsource_line')
        if memsource_line_ids:
            weighted_per = False
            # To get endclient weightage ids
            endclient_wt_rec = self.get_endclient_weightage_ids()

            if endclient_wt_rec:
                end_client_wt_per = self.env['endclient.weightage'].browse(endclient_wt_rec)
                weighted_per = end_client_wt_per.endclient_weightage_line
            default_weighted_per = self.env['analyse.percent.type'].search([])
            if weighted_per:
                available_analyse_type = weighted_per.mapped('code')
            else:
                available_analyse_type = default_weighted_per.mapped('code')
            default_type = default_weighted_per.mapped('code')

            missing_type = list(set(default_type) - set(available_analyse_type))
            if missing_type:
                raise ValidationError(_('Missing Analysis type in end client weighted configuration. '
                                        'Please contact CS admin to configure!'))

            seq = default_weighted_per.mapped('sequence')
            sequence = seq[-1]
            for line in self.order_id.order_line:
                memsource_type = [mem_line.percent_type.code for mem_line in line.memsource_line]
                new_type = list(set(memsource_type) - set(available_analyse_type))
                if new_type:
                    not_config = list(set(new_type) - set(default_type))
                    not_config.remove('all')
                    not_config.remove('match99')
                    if not_config:
                        self.order_id.new_connection(not_config, sequence)
                        raise ValidationError(_('Analysis type %s not configured please '
                                                'contact CS admin to configure!') % new_type)

                for memsource_line_id in line.memsource_line:
                    weighted_percent, percent_type_id = 0.0, False
                    if weighted_per:
                        weighted_rec = weighted_per.filtered(lambda l: l.code == memsource_line_id.percent_type.code)
                        percent_type_id = weighted_rec.percent_type_id
                        weighted_percent = weighted_rec.percentage
                    else:
                        percent_type_id = default_weighted_per.filtered(
                            lambda l: l.code == memsource_line_id.percent_type.code)
                        weighted_percent = percent_type_id.percentage

                    weighted_count = (memsource_line_id.unit_count * weighted_percent) / 100
                    if percent_type_id and percent_type_id.code not in ['all', 'match99']:
                        memsource_line_id.write({
                            'weighted_percent': weighted_percent,
                            'weighted_count': math.ceil(weighted_count)
                        })

                # Calculate Memsource Total word count cost
                line._total_word_count_and_amount()
                # Calculate Word Count
                line._total_character_count()

            # To update values in excel sheet
            self.order_id.analyse_file_export()
            # To update weighted related fields value
            self.update_related_data()
        else:
            return True

    def get_endclient_weightage_ids(self):
        """
            Fetch endclient weightage ids
            :return: endclient_wt_rec: endclient weightage ids
        """
        memid_query, end_client_query = '', ''
        if self.order_id.mem_id:
            memid_query = '=' + str(self.order_id.mem_id.id)
        else:
            memid_query = 'IS NULL'

        if self.order_id.end_client_id:
            end_client_query = '=' + str(self.order_id.end_client_id.id)
        else:
            end_client_query = 'IS NULL'

        self.env.cr.execute("""SELECT id FROM endclient_weightage 
                                WHERE end_client_id %s
                                AND membership_id %s""" % (end_client_query, memid_query))
        endclient_wt_rec = [x[0] for x in self.env.cr.fetchall()]
        return endclient_wt_rec

    def update_related_data(self):
        """
            To update weighted related fields value
            :return: True
        """
        # Update fee and it's related field value data
        for tl in self.order_id.order_line.mapped('service_level_line'):
            tl.onchnage_unit_rate()
        # To update lowest_fee, recommended_deadline and char_count
        self.order_id.onchange_final_deadline()
        return True

    def update_fee(self):
        """
            Update fee in translation level's
            :return: True
        """
        if self.order_id.order_line:
            service_level_line_ids = self.order_id.order_line.mapped("service_level_line")
            if service_level_line_ids:
                end_client, membership_id = '', ''
                if self.order_id.end_client_id:
                    end_client = """ AND end_client_id = %s""" % str(self.order_id.end_client_id.id)
                else:
                    end_client = """ AND end_client_id is NULL"""
                if self.order_id.mem_id:
                    membership_id = """ AND membership_id = %s""" % str(self.order_id.mem_id.id)
                else:
                    membership_id = """ AND membership_id is NULL"""

                ew_query = """SELECT * FROM endclient_weightage WHERE"""

                if self.order_id.end_client_id:
                    ew_query += """ end_client_id = %s""" % (self.order_id.end_client_id.id)
                else:
                    ew_query += " end_client_id is Null"
                if self.order_id.mem_id:
                    ew_query += """ AND membership_id = %s""" % (self.order_id.mem_id.id)
                else:
                    ew_query += " AND membership_id is Null"

                self.env.cr.execute(ew_query)
                ew_data = self.env.cr.fetchall()
                product_id = self.order_id.product_id.id
                if ew_data:
                    if ew_data[0][13]:
                        product_id = ew_data[0][13]

                for line in self.order_id.order_line:
                    for service_level_line_id in line.service_level_line:
                        fee = []
                        fee_updated = False
                        fee_query = """SELECT price from fee_master 
                                       WHERE product_id = %s 
                                       AND translation_level_id = %s
                                       AND priority = '%s'
                                       AND source_lang_id = %s 
                                       AND target_lang_id = %s
                                       AND currency_id = %s
                                    """ % (
                            str(product_id), str(service_level_line_id.service_level_id.id),
                            str(self.order_id.priority), str(self.order_id.source_lang_id.id),
                            str(line.target_lang_id.id), str(self.order_id.currency_id.id))

                        common_query = fee_query
                        fee_query += end_client + membership_id
                        self.env.cr.execute(fee_query)
                        data = self.env.cr.fetchall()
                        fee = [x[0] for x in data]
                        if fee:
                            fee_updated = True
                            service_level_line_id.write({
                                'unit_rate': fee[0] or 0.0
                            })
                        if not fee_updated and self.order_id.mem_id and not self.order_id.end_client_id:
                            fee_query = common_query + membership_id + """ AND end_client_id is NULL"""
                            self.env.cr.execute(fee_query)
                            data = self.env.cr.fetchall()
                            fee = [x[0] for x in data]
                            if fee:
                                fee_updated = True
                                service_level_line_id.write({
                                    'unit_rate': fee[0] or 0.0
                                })
                        if not fee_updated and self.order_id.end_client_id and not self.order_id.mem_id:
                            fee_query = common_query + end_client + """AND membership_id is NULL"""
                            self.env.cr.execute(fee_query)
                            data = self.env.cr.fetchall()
                            fee = [x[0] for x in data]
                            if fee:
                                fee_updated = True
                                service_level_line_id.write({
                                    'unit_rate': fee[0] or 0.0
                                })
                        if not fee_updated:
                            fee_query = common_query + """ AND end_client_id is NULL 
                                                           AND membership_id is NULL"""
                            self.env.cr.execute(fee_query)
                            data = self.env.cr.fetchall()
                            fee = [x[0] for x in data]
                            if fee:
                                service_level_line_id.write({
                                    'unit_rate': fee[0] or 0.0
                                })
                            else:
                                service_level_line_id.write({
                                    'unit_rate': 0.0
                                })
                    # To update weighted related fields value
                    self.update_related_data()
        return True

    def update_addons_fee(self):
        """
            Update addons fee
            :return: True
        """
        if self.order_id.order_line:
            addons_fee_line_ids = self.order_id.order_line.mapped("addons_fee_line")
            if addons_fee_line_ids:
                end_client, membership_id = '', ''
                if self.order_id.end_client_id:
                    end_client = """ AND end_client_id = %s""" % str(self.order_id.end_client_id.id)
                else:
                    end_client = """ AND end_client_id is NULL"""
                if self.order_id.mem_id:
                    membership_id = """ AND membership_id = %s""" % str(self.order_id.mem_id.id)
                else:
                    membership_id = """ AND membership_id is NULL"""

                for sale_line_id in self.order_id.order_line:
                    for addon_line_id in sale_line_id.addons_fee_line:
                        updated_fee = []
                        fee_query = """SELECT price FROM addons_fee_master 
                                       WHERE addons_id = %s 
                                       AND currency_id = %s
                                       AND priority = '%s' 
                                       AND product_id = %s
                                       AND source_lang_id = %s
                                       AND target_lang_id = %s 
                                       AND unit_id = %s 
                                    """ % (addon_line_id.addons_id.id, sale_line_id.order_id.currency_id.id,
                                           sale_line_id.order_id.priority, sale_line_id.order_id.product_id.id,
                                           sale_line_id.source_lang_id.id, sale_line_id.target_lang_id.id,
                                           str(addon_line_id.unit_id.id))

                        common_query = fee_query
                        fee_query += end_client + membership_id
                        self.env.cr.execute(fee_query)
                        data = self.env.cr.fetchall()
                        addons_fee = [x[0] for x in data]

                        if addons_fee:
                            updated_fee = True
                            addon_line_id.write({
                                'price': addons_fee[0],
                                'total_price': addon_line_id.no_of_unit * addons_fee[0],
                            })
                        if not updated_fee and self.order_id.mem_id:
                            fee_query = common_query + membership_id + """ AND end_client_id is NULL"""
                            self.env.cr.execute(fee_query)
                            addon_fee_list = self.env.cr.fetchall()
                            addons_fee = [x[0] for x in addon_fee_list]
                            if addons_fee:
                                updated_fee = True
                                addon_line_id.write({
                                    'price': addons_fee[0],
                                    'total_price': addon_line_id.no_of_unit * addons_fee[0],
                                })
                        if not updated_fee and self.order_id.end_client_id:
                            fee_query = common_query + end_client + """AND membership_id is NULL"""
                            self.env.cr.execute(fee_query)
                            addon_fee_list = self.env.cr.fetchall()
                            addons_fee = [x[0] for x in addon_fee_list]
                            if addons_fee:
                                updated_fee = True
                                addon_line_id.write({
                                    'price': addons_fee[0],
                                    'total_price': addon_line_id.no_of_unit * addons_fee[0],
                                })
                        if not updated_fee:
                            fee_query = common_query + """ AND end_client_id is NULL 
                                                           AND membership_id is NULL """
                            self.env.cr.execute(fee_query)
                            addon_fee_list = self.env.cr.fetchall()
                            addons_fee = [x[0] for x in addon_fee_list]
                            if addons_fee:
                                addon_line_id.write({
                                    'price': addons_fee[0],
                                    'total_price': addon_line_id.no_of_unit * addons_fee[0],
                                })
                            else:
                                raise ValidationError(_("No add-ons fee setup please contact CS Admin to configure!"))

                # Remove Add-ons Price Summary data
                if self.order_id.sale_order_addons_line:
                    self.order_id.sale_order_addons_line.unlink()
                addons_dict = {}
                # Update Add-ons Price Summary data
                for addons in addons_fee_line_ids:
                    addons_id = addons.addons_id.id
                    unit_id = addons.unit_id.id
                    adoons_key = str(addons_id) + '_' + str(unit_id)
                    if adoons_key not in addons_dict.keys():
                        addons_dict.update(
                            {adoons_key: (0, 0, {
                                'unit': addons.no_of_unit,
                                'rate': addons.price,
                                'addons_price': addons.total_price,
                                'addons_service_id': addons_id,
                                'unit_id': unit_id,
                            })})
                    else:
                        addons_dict[adoons_key][2]['unit'] += addons.no_of_unit
                        addons_dict[adoons_key][2]['rate'] += addons.price
                        addons_dict[adoons_key][2]['addons_price'] += addons.total_price
                self.order_id.write({
                    'sale_order_addons_line': list(addons_dict.values())
                })
        return True

    def update_area_type(self):
        # active_id = self._context.get('active_id')
        # active_model = self._context.get('active_model')
        records_to_update = self.order_id
        mem_id = records_to_update.mem_id.id
        end_client_id = records_to_update.end_client_id.id
        store_update_records = self.env['endclient.weightage'].search([('membership_id', '=', mem_id),
                                                                ('end_client_id', '=', end_client_id)])
        if records_to_update and store_update_records:
            values= {
                'product_id': store_update_records.product_id.id,
                'area_type': store_update_records.area_type,
                'subject_industrial_area_level1_id': store_update_records.subject_industrial_area_level1_id.id,
                'subject_industrial_area_level2_id': store_update_records.subject_industrial_area_level2_id.id,
                'subject_industrial_area_level3_id': store_update_records.subject_industrial_area_level3_id.id,
                'level3_other_area_bool': store_update_records.level3_other_area_bool,
                'level3_other_area': store_update_records.level3_other_area,
            }
            records_to_update.write(values)
        else:
            # vals = {}
            values = {
                'product_id': records_to_update.product_id.id,
                'area_type': records_to_update.area_type,
                'subject_industrial_area_level1_id': records_to_update.subject_industrial_area_level1_id.id,
                'subject_industrial_area_level2_id': records_to_update.subject_industrial_area_level2_id.id,
                'subject_industrial_area_level3_id': records_to_update.subject_industrial_area_level3_id.id,
                'level3_other_area_bool': records_to_update.level3_other_area_bool,
                'level3_other_area': records_to_update.level3_other_area,
            }
            records_to_update.write(values)
            # records_to_update = [6, 0, values]

        return True
