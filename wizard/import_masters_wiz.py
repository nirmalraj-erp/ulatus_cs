# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from odoo.tools.translate import _
import csv
import os
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)


class ImportMastersWiz(models.TransientModel):
    _name = 'import.masters.wiz'
    _description = 'Import Masters Wizard'

    location = fields.Char('Directory Location')
    import_data_type = fields.Selection([('fee', 'Fee'),
                                         ('addons_fees', 'Add-ons Fee')], string='Import Masters', required=True)

    @api.multi
    def create_error_log_file(self, error_data, filename, header):
        """
            Creating separate csv file to log issue with data
            :param error_data: list of data with error message
            :param header: Column Headers
            :param filename: Name of the file
            :return: True
        """
        csv_file_path = '/tmp/%s_%s.csv' % (filename, datetime.now().strftime("%d-%m-%Y_%H-%M-%S"))
        header.append('error')
        with open(csv_file_path, 'w') as csvfile:
            # creating a csv writer object
            csvwriter = csv.writer(csvfile)
            # writing the header
            csvwriter.writerow(header)
            # writing the data rows
            for error_dict_data in error_data:
                csvwriter.writerow(list(error_dict_data.values()))
        return True

    @api.multi
    def import_masters(self):
        """
            To import masters records
            :return: True
        """
        if not self.location:
            raise UserError(_('Please add the directory location!'))
        if not self.import_data_type:
            raise UserError(_('Please select the import masters!'))

        # To read files inside the directory
        for f in os.listdir(self.location.strip()):
            file_path = os.path.join(self.location.strip(), f)
            with open(file_path, 'r') as file:
                csv_file = csv.DictReader(file)
                data_list = [dict(row) for row in csv_file]

            # check master type and call importing function
            if self.import_data_type == 'fee':
                self.import_fees(data_list)
            elif self.import_data_type == 'addons_fees':
                self.import_addons_fees(data_list)
        return True

    @api.multi
    def import_fees(self, data_list):
        """
            To import fee master records
            :param data_list: list of fee master data
            :return: True
        """
        error_data = []
        count = 1
        _logger.info('---------len(data_list)---------: %s ' % len(data_list))
        header = list(data_list[0].keys())
        for data in data_list:
            try:
                _logger.info('---------count---------: %s ' % count)
                count += 1

                mem_id, end_client_id = False, False
                if data.get('mem_id').strip():
                    self._cr.execute("""SELECT id FROM membership_master WHERE name=%s""",
                                     (data.get('mem_id').strip(),))
                    memid_record = self.env.cr.fetchall()
                    if not memid_record:
                        data.update({'error': 'Membership ID is not found in the system.'})
                        error_data.append(data)
                        continue

                    mem_id = memid_record[0][0]

                if data.get('endclient_name').strip():
                    self._cr.execute("""SELECT id FROM res_partner WHERE name=%s and type='end_client'""",
                                     (data.get('endclient_name').strip(),))
                    endclient_record = self.env.cr.fetchall()
                    if not endclient_record:
                        data.update({'error': 'End client is not found in the system.'})
                        error_data.append(data)
                        continue

                    end_client_id = endclient_record[0][0]

                self._cr.execute("""SELECT id FROM product_template WHERE name=%s""", (data.get('product').strip(),))
                product_tmpl_id = self.env.cr.fetchall()[0][0]

                self._cr.execute("""SELECT id FROM product_product WHERE product_tmpl_id=%s""", (product_tmpl_id,))
                product_id = self.env.cr.fetchall()[0][0]

                self._cr.execute("""SELECT id FROM service_level WHERE name=%s""",
                                 (data.get('translation_level').strip(),))
                translation_level_id = self.env.cr.fetchall()[0][0]

                self._cr.execute("""SELECT id, unit_id FROM res_lang WHERE name=%s""", (data.get('src_lang').strip(),))
                src_lang_data = self.env.cr.fetchall()
                source_lang_id = src_lang_data[0][0]
                unit_id = src_lang_data[0][1]

                self._cr.execute("""SELECT id FROM res_lang WHERE name=%s""", (data.get('target_lang').strip(),))
                target_lang_id = self.env.cr.fetchall()[0][0]

                self._cr.execute("""SELECT id FROM res_currency WHERE name=%s""", (data.get('currency').strip(),))
                currency_id = self.env.cr.fetchall()[0][0]

                priority = data.get('priority').strip().lower()
                price = float(data.get('price_per_unit').strip())

                flag = self.check_fee_record_exists(product_id, translation_level_id, source_lang_id, target_lang_id,
                                                    currency_id, mem_id, end_client_id, priority, price)

                if not flag:
                    if mem_id and end_client_id:
                        self._cr.execute("""INSERT INTO fee_master(product_id,translation_level_id,membership_id,
                                            end_client_id,priority,source_lang_id,target_lang_id,currency_id,price,
                                            unit_id) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                                         (product_id, translation_level_id, mem_id, end_client_id,
                                          priority, source_lang_id, target_lang_id, currency_id, price, unit_id))
                    elif not mem_id and end_client_id:
                        self._cr.execute("""INSERT INTO fee_master(product_id,translation_level_id,end_client_id,
                                            priority,source_lang_id,target_lang_id,currency_id,price,unit_id) 
                                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                                         (product_id, translation_level_id, end_client_id, priority, source_lang_id,
                                          target_lang_id, currency_id, price, unit_id))
                    elif mem_id and not end_client_id:
                        self._cr.execute("""INSERT INTO fee_master(product_id,translation_level_id,membership_id,
                                            priority,source_lang_id,target_lang_id,currency_id,price,unit_id)
                                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                                         (product_id, translation_level_id, mem_id, priority, source_lang_id,
                                          target_lang_id, currency_id, price, unit_id))
                    elif not mem_id and not end_client_id:
                        self._cr.execute("""INSERT INTO fee_master(product_id,translation_level_id,
                                            priority,source_lang_id,target_lang_id,currency_id,price,
                                            unit_id) values (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                                         (product_id, translation_level_id, priority, source_lang_id, target_lang_id,
                                          currency_id, price, unit_id))
                else:
                    data.update({'error': 'Fee already exists for these combination!'})
                    error_data.append(data)

                self._cr.commit()
            except Exception as e:
                data.update({'error': e})
                error_data.append(data)
        if error_data:
            # Creating separate csv file to log issue with data
            self.create_error_log_file(error_data, 'fee_master', header)
            _logger.info('-------csv_file_created-------')
        return True

    @api.multi
    def check_fee_record_exists(self, product_id, translation_level_id, source_lang_id, target_lang_id, currency_id,
                                mem_id, end_client_id, priority, price):
        """
            To check fee record already exists or not
            :return: flag: true if record already exists else false
        """
        flag = False
        query = """SELECT id 
                   FROM fee_master
                   WHERE currency_id = %s AND translation_level_id = %s 
                   AND priority = '%s' AND product_id = %s 
                   AND source_lang_id = %s AND target_lang_id = %s AND price=%s
                """ % (currency_id, translation_level_id, priority, product_id, source_lang_id, target_lang_id, price)
        if mem_id:
            query += " AND membership_id = %s" % mem_id
        else:
            query += " AND membership_id is Null"
        if end_client_id:
            query += " AND end_client_id = %s LIMIT 1" % end_client_id
        else:
            query += " AND end_client_id is Null LIMIT 1"
        self.env.cr.execute(query)
        record = self.env.cr.fetchone()
        if record:
            flag = True
        return flag

    @api.multi
    def import_addons_fees(self, data_list):
        """
            To import Add-ons Fee master records
            :param data_list: list of Add-ons Fee master data
            :return: True
        """
        error_data = []
        count = 1
        _logger.info('---------len(data_list)---------: %s ' % len(data_list))
        header = list(data_list[0].keys())
        for data in data_list:
            try:
                _logger.info('---------count---------: %s ' % count)
                count += 1

                mem_id, end_client_id = False, False
                if data.get('mem_id').strip():
                    self._cr.execute("""SELECT id FROM membership_master WHERE name=%s""",
                                     (data.get('mem_id').strip(),))
                    memid_record = self.env.cr.fetchall()
                    if not memid_record:
                        data.update({'error': 'Membership ID is not found in the system.'})
                        error_data.append(data)
                        continue

                    mem_id = memid_record[0][0]

                if data.get('endclient_name').strip():
                    self._cr.execute("""SELECT id FROM res_partner WHERE name=%s and type='end_client'""",
                                     (data.get('endclient_name').strip(),))
                    endclient_record = self.env.cr.fetchall()
                    if not endclient_record:
                        data.update({'error': 'End client is not found in the system.'})
                        error_data.append(data)
                        continue

                    end_client_id = endclient_record[0][0]

                self._cr.execute("""SELECT id FROM product_template WHERE name=%s""", (data.get('product').strip(),))
                product_tmpl_id = self.env.cr.fetchall()[0][0]

                self._cr.execute("""SELECT id FROM product_product WHERE product_tmpl_id=%s""", (product_tmpl_id,))
                product_id = self.env.cr.fetchall()[0][0]

                self._cr.execute("""SELECT id FROM product_template WHERE name=%s""",
                                 (data.get('addons_name').strip(),))
                addons_tmpl_id = self.env.cr.fetchall()[0][0]

                self._cr.execute("""SELECT id FROM product_product WHERE product_tmpl_id=%s 
                                    AND addons_service_bool=true""", (addons_tmpl_id,))
                addons_id = self.env.cr.fetchall()[0][0]

                self._cr.execute("""SELECT id FROM res_lang WHERE name=%s""", (data.get('src_lang').strip(),))
                source_lang_id = self.env.cr.fetchall()[0][0]

                self._cr.execute("""SELECT id FROM service_unit WHERE name=%s""", (data.get('unit_name').strip(),))
                unit_id = self.env.cr.fetchall()[0][0]

                self._cr.execute("""SELECT id FROM res_lang WHERE name=%s""", (data.get('target_lang').strip(),))
                target_lang_id = self.env.cr.fetchall()[0][0]

                self._cr.execute("""SELECT id FROM res_currency WHERE name=%s""", (data.get('currency').strip(),))
                currency_id = self.env.cr.fetchall()[0][0]

                priority = data.get('priority').strip().lower()
                price = float(data.get('price_per_unit').strip())

                flag = self.check_addons_fee_record_exists(product_id, addons_id, source_lang_id, target_lang_id,
                                                           currency_id, mem_id, end_client_id, priority, price, unit_id)

                if not flag:
                    if mem_id and end_client_id:
                        self._cr.execute("""INSERT INTO addons_fee_master(product_id,addons_id,membership_id,
                                            end_client_id,priority,source_lang_id,target_lang_id,currency_id,price,
                                            unit_id) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                                         (product_id, addons_id, mem_id, end_client_id, priority,
                                          source_lang_id, target_lang_id, currency_id, price, unit_id))
                    elif not mem_id and end_client_id:
                        self._cr.execute("""INSERT INTO addons_fee_master(product_id,addons_id,end_client_id,
                                            priority,source_lang_id,target_lang_id,currency_id,price,
                                            unit_id) values (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                                         (product_id, addons_id, end_client_id, priority, source_lang_id,
                                          target_lang_id, currency_id, price, unit_id))
                    elif mem_id and not end_client_id:
                        self._cr.execute("""INSERT INTO addons_fee_master(product_id,addons_id,membership_id,
                                            priority,source_lang_id,target_lang_id,currency_id,price,
                                            unit_id) values (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                                         (product_id, addons_id, mem_id, priority, source_lang_id,
                                          target_lang_id, currency_id, price, unit_id))
                    elif not mem_id and not end_client_id:
                        self._cr.execute("""INSERT INTO addons_fee_master(product_id,addons_id,priority,
                                            source_lang_id,target_lang_id,currency_id,price,unit_id)
                                            values (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                                         (product_id, addons_id, priority, source_lang_id, target_lang_id,
                                          currency_id, price, unit_id))
                else:
                    data.update({'error': 'Add-ons Fee already exists for these combination!'})
                    error_data.append(data)

                self._cr.commit()
            except Exception as e:
                data.update({'error': e})
                error_data.append(data)
        if error_data:
            # Creating separate csv file to log issue with data
            self.create_error_log_file(error_data, 'addons_fee_master', header)
            _logger.info('-------csv_file_created-------')
        return True

    @api.multi
    def check_addons_fee_record_exists(self, product_id, addons_id, source_lang_id, target_lang_id, currency_id,
                                       mem_id, end_client_id, priority, price, unit_id):
        """
            To check addons fee record already exists or not
            :return: flag: true if record already exists else false
        """
        flag = False
        query = """SELECT id 
                    FROM addons_fee_master
                    WHERE addons_id = %s 
                    AND currency_id = %s AND priority = '%s'
                    AND product_id = %s AND source_lang_id = %s 
                    AND target_lang_id = %s AND unit_id =%s AND price=%s
                """ % (addons_id, currency_id, priority, product_id, source_lang_id, target_lang_id, unit_id, price)
        if mem_id:
            query += " AND membership_id = %s" % mem_id
        else:
            query += " AND membership_id is Null"
        if end_client_id:
            query += " AND end_client_id = %s LIMIT 1" % end_client_id
        else:
            query += " AND end_client_id is Null LIMIT 1"
        self.env.cr.execute(query)
        record = self.env.cr.fetchone()
        if record:
            flag = True
        return flag
