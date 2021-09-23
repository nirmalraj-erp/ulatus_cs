import base64
import re
from itertools import groupby
from io import BytesIO
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from odoo.tools.translate import _
import xlrd
import csv
from datetime import datetime, timedelta
import pytz
import logging
_logger = logging.getLogger(__name__)


def get_tz(tz_abbreviation):
    """ To get timezone from timezone abbreviation """
    tz = False
    if tz_abbreviation == 'JST':
        tz = 'Japan'
    elif tz_abbreviation == 'EST':
        tz = 'US/Eastern'
    elif tz_abbreviation == 'IST':
        tz = 'Asia/Kolkata'
    elif tz_abbreviation == 'GMT':
        tz = 'GMT'
    return tz


class LegacyDataImport(models.TransientModel):
    _name = 'legacy.data.import'
    _description = 'Legacy Data Import'

    sheet_data = fields.Binary('Import File')
    import_data_type = fields.Selection([('mem_id', 'Membership ID'),
                                         ('client_type', 'Client Type'),
                                         ('client_preferences', 'Client Preferences'),
                                         ('inquiry', 'Inquires'),
                                         ('quotation', 'Quotations'),
                                         ('asn', 'Assignments'),
                                         ('update_asn_seq', 'Update ASN\'s Sequence'),
                                         ('link_original_n_rr_asn', 'Link Original and RR ASN'),
                                         ('update_active_org_in_client', 'Update Org in Client'),
                                         ('update_org_in_inquiries', 'Update Org in inquiries'),
                                         ('update_org_in_quotations', 'Update Org in Quotations'),
                                         ('import_bi_report_data', 'Import BI Report Data')],
                                        string='Import Data', required=True)
    client_type = fields.Selection([('create_portal_user', 'Create Portal User'),
                                    ('without_portal_user', 'Without Portal User')],
                                   string='Type', default='without_portal_user')

    @api.multi
    def get_sheet_data(self, sheet_data, nested):
        """
            Read excel sheet and get data in dict format
            :param sheet_data: sheet's binary data
            :param nested: if true then create nested dict for child asn data else normal dict for all rows
            :return: dict_list, header: sheet's data in dict and header
        """
        fp = BytesIO()
        fp.write(sheet_data)
        wb = xlrd.open_workbook(file_contents=fp.getvalue())
        sheet = wb.sheet_by_index(0)
        header = [sheet.cell(0, col_index).value for col_index in range(sheet.ncols)]
        dict_list = []
        for row_index in range(1, sheet.nrows):
            d = {}
            for col_index in range(sheet.ncols):
                if col_index in [8, 9, 10, 11, 21] and nested:
                    r_val = sheet.cell(row_index, col_index).value if sheet.cell(row_index,
                                                                                        col_index).value else False
                    if r_val:
                        if type(r_val) == str:
                            d.update({header[col_index]: datetime.strptime(r_val, '%Y-%m-%d %H:%M:%S')})
                        else:
                            d.update({header[col_index]: datetime(*xlrd.xldate_as_tuple(r_val, wb.datemode))})
                    else:
                        d.update({header[col_index]: False})
                else:
                    d.update({header[col_index]: sheet.cell(row_index, col_index).value})
            if d.get('asn_type') == 'Child' and nested:
                # append child
                if 'childs' in dict_list[-1]:
                    child_list = dict_list[-1].get('childs')
                    child_list.append(d)
                else:
                    dict_list[-1].update({'childs': [d]})
                continue
            # append parent
            dict_list.append(d)
        return dict_list, header

    @api.multi
    def create_error_log_file(self, error_data, filename, header, nested):
        """
            Creating separate csv file to log issue with data
            :param error_data: list of data with error message
            :param header: Column Headers
            :param filename: Name of the file
            :param nested: if true then create nested dict for child asn data else normal dict for all rows
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
                temp_data_dict = error_dict_data.copy()
                if 'childs' in temp_data_dict:
                    temp_data_dict.pop('childs')
                csvwriter.writerow(list(temp_data_dict.values()))
                if nested and 'childs' in error_dict_data:
                    for child_error_data in error_dict_data.get('childs'):
                        csvwriter.writerow(list(child_error_data.values()))
        return True

    @api.multi
    def common_validate_data(self, data, check_for_asn):
        error_msg = []
        validated_data = {}
        validated_data = data.copy()
        # membership ID
        if not str(data.get('membership_id')).strip():
            error_msg.append('Membership ID is missing.')
        else:
            if len(str(data.get('membership_id')).strip()) != 6:
                error_msg.append('Length of Membership ID should be 6 character.')
            else:
                validated_data.update({'membership_id': str(data.get('membership_id')).strip()})

        # email
        if not str(data.get('email')).strip():
            error_msg.append('Email is missing.')
        else:
            match = re.match(
                '^[\W]*([\w+\-.%]+@[\w\-.]+\.[A-Za-z]{2,4}[\W]*,{1}[\W]*)*([\w+\-.%]+@[\w\-.]+\.[A-Za-z]{2,4})[\W]*$',
                str(data.get('email')).strip())
            if match is None:
                error_msg.append('Email-ID is not valid')
            else:
                validated_data.update({'email': str(data.get('email')).strip().lower()})

        # currency
        if not str(data.get('currency')).strip():
            error_msg.append('Currency is missing.')
        else:
            currency_id = self.env['res.currency'].search([('name', '=', str(data.get('currency')).strip()),
                                                           ('active', '=', True)])
            if not currency_id:
                error_msg.append('Currency might be inactive in the software.')
            validated_data.update({'currency': currency_id})

        # client's first name
        if not str(data.get('first_name')).strip():
            error_msg.append('Client\'s First Name is missing.')
        else:
            validated_data.update({'first_name': str(data.get('first_name')).strip()})

        # timezone
        if not str(data.get('tz')).strip():
            error_msg.append('Timezone is missing.')
        else:
            tz = get_tz(str(data.get('tz')).strip())
            if not tz:
                error_msg.append('Timezone is not valid.')
            else:
                validated_data.update({'tz': tz})

        # checking while importing asn data
        if check_for_asn:
            # asn_no
            if not str(data.get('asn_no')).strip():
                error_msg.append('ASN number is missing.')
            else:
                res = str(data.get('asn_no')).strip().split('-')
                if res[0] != str(data.get('membership_id')).strip():
                    error_msg.append('Membership ID in ASN number is not matching with Membership ID column.')

            # Source language
            if not str(data.get('src_lang')).strip():
                error_msg.append('Source language is missing.')
            else:
                src_lang_id = self.env['res.lang'].search([('name', '=', str(data.get('src_lang')).strip())])
                if not src_lang_id:
                    error_msg.append('Source language is not found in the software. Please check language master.')
                else:
                    validated_data.update({'src_lang': src_lang_id})

            # Target language
            if not str(data.get('target_lang')).strip():
                error_msg.append('Target language is missing.')
            else:
                if 'childs' not in data:
                    target_lang_id = self.env['res.lang'].search([('name', '=', str(data.get('target_lang')).strip())])
                    if not target_lang_id:
                        error_msg.append('Target language is not found in the software. Please check language master.')
                    else:
                        validated_data.update({'target_lang': target_lang_id})

            # Translation level
            if not str(data.get('translation_level')).strip():
                error_msg.append('Translation level is missing.')
            else:
                translation_level_id = self.env['service.level'].search(
                    [('name', '=', str(data.get('translation_level')).strip())])
                if not translation_level_id:
                    error_msg.append(
                        'Translation level is not found in the software. Please check translation level master.')
                else:
                    validated_data.update({'translation_level': translation_level_id})

            # convert datetime IST to UTC timezone
            user_tz = pytz.timezone('Asia/Kolkata')
            # Date of inquiry
            validated_data.update(
                {'date_of_inq': user_tz.localize(data.get('date_of_inq')).astimezone(pytz.utc)}) if data.get(
                'date_of_inq') else error_msg.append('Date of inquiry is missing.')

            # datetime_of_confirmation
            validated_data.update({'datetime_of_confirmation': user_tz.localize(
                data.get('datetime_of_confirmation')).astimezone(pytz.utc)}) if data.get(
                'datetime_of_confirmation') else error_msg.append('Date of confirmation is missing.')

            # client_delivery_datetime
            validated_data.update({'client_delivery_datetime': user_tz.localize(
                data.get('client_delivery_datetime')).astimezone(pytz.utc)}) if data.get(
                'client_delivery_datetime') else error_msg.append('Client delivery datetime is missing.')

            # actual_delivery_datetime
            validated_data.update({'actual_delivery_datetime': user_tz.localize(
                data.get('actual_delivery_datetime')).astimezone(pytz.utc)}) if data.get(
                'actual_delivery_datetime') else error_msg.append('Actual delivery datetime is missing.')

            # delivery_option
            validated_data.update({'delivery_option': str(data.get('delivery_option')).strip().lower()}) if str(
                data.get('delivery_option')).strip() else error_msg.append('Delivery option is missing.')

            # level data
            # get level 1
            area_type_value = 'subject_area' if data.get(
                'is_subject_area').strip().lower() == 'yes' else 'industrial_area'
            if str(data.get('level_1')).strip():
                level_1_id = self.env['subject.industrial.area.level1'].search(
                    [('name', '=', str(data.get('level_1')).strip()), ('area_type', '=', area_type_value)])
                # get level 2
                if level_1_id:
                    validated_data.update({'level_1': level_1_id})
                    level_2_id = self.env['subject.industrial.area.level2'].search(
                        [('level1_id', '=', level_1_id.id), ('area_type', '=', area_type_value)])
                    if level_2_id:
                        level_2 = self.env['subject.industrial.area.level2.line'].search(
                            [('level2_id', '=', level_2_id.id), ('name', '=', str(data.get('level_2')).strip())])
                        # get level 3
                        if level_2:
                            validated_data.update({'level_2': level_2})
                            level_3_id = self.env['subject.industrial.area.level3'].search(
                                [('parent_level2_line_id', '=', level_2.id), ('area_type', '=', area_type_value),
                                 ('parent_level1_id', '=', level_1_id.id)])
                            if level_3_id:
                                level_3 = self.env['subject.industrial.area.level3.line'].search(
                                    [('name', '=', str(data.get('level_3')).strip()), ('level3_id', '=', level_3_id.id)])
                                if level_3:
                                    validated_data.update({'level_3': level_3})
                                else:
                                    error_msg.append('Level 3 is not mapped in lines.')
                            else:
                                error_msg.append('Linking between level 1, level 2 and level 3 is missing.')
                        else:
                            error_msg.append('Level 2 is not mapped in lines.')
                    else:
                        error_msg.append('Linking between level 1 and level 2 is missing.')
                else:
                    error_msg.append('Level 1 is missing in the masters.')
            else:
                error_msg.append('Level 1 is missing.')

            # product
            if str(data.get('product')).strip():
                product_id = self.env['product.product'].search([('name', '=', str(data.get('product')).strip())])
                validated_data.update({'product': product_id}) if product_id else error_msg.append(
                    'Product is missing in the product master.')
            else:
                error_msg.append('Product is missing in the sheet.')

        return validated_data, error_msg

    @api.multi
    def validate_parent_child_data(self, data, key, error_msg):
        parent = str(data.get(key)).strip()
        child = [str(t.get(key)).strip() for t in data.get('childs') if t.get(key)]
        result = all(elem == parent for elem in child)
        if not result and key != 'po_no':
            msg_key = ''
            if key == 'src_lang':
                msg_key = 'Source language'
            elif key == 'translation_level':
                msg_key = 'Translation level'
            elif key == 'level_1':
                msg_key = 'SubjectArea'
            elif key == 'level_2':
                msg_key = 'Sub-subject area'
            elif key == 'level_3':
                msg_key = 'Specialization'
            elif key == 'email':
                msg_key = 'Email'
            elif key == 'product':
                msg_key = 'Product'
            elif key == 'first_name':
                msg_key = 'Client\'s first name'
            test_msg = '%s of parent and childs should be same. Also please make sure, ' \
                       '%s for all child ASN should be same.' % (msg_key, msg_key)
            error_msg.append(test_msg)
        if key == 'po_no' and child:
            error_msg.append('PO Number are mentioned in child asn. Please add that PO Number in parent ASN.')
        return error_msg

    @api.multi
    def validate_data(self, data, check_for_asn):
        error_flag = False
        validated_data, error_msg = self.common_validate_data(data, check_for_asn)
        if error_msg:
            data.update({'error': '\n'.join(error_msg)})
            error_flag = True
        # Validate asn related data
        if check_for_asn:
            if 'childs' in data:
                # Source language
                error_msg = self.validate_parent_child_data(data, 'src_lang', error_msg)
                # translation_level
                error_msg = self.validate_parent_child_data(data, 'translation_level', error_msg)
                # level 1
                error_msg = self.validate_parent_child_data(data, 'level_1', error_msg)
                # level 2
                error_msg = self.validate_parent_child_data(data, 'level_2', error_msg)
                # level 3
                error_msg = self.validate_parent_child_data(data, 'level_3', error_msg)
                # email
                error_msg = self.validate_parent_child_data(data, 'email', error_msg)
                # product
                error_msg = self.validate_parent_child_data(data, 'product', error_msg)
                # client_first_name
                error_msg = self.validate_parent_child_data(data, 'first_name', error_msg)
                # po_no
                error_msg = self.validate_parent_child_data(data, 'po_no', error_msg)
                if error_msg:
                    data.update({'error': '\n'.join(error_msg)})
                    error_flag = True

            if data.get('childs'):
                child_list, validated_child_data = [], []
                for child in data.get('childs'):
                    validated_data_c, error_msg_c = self.common_validate_data(child, check_for_asn)
                    validated_child_data.append(validated_data_c)
                    if error_msg:
                        error_flag = True
                        child.update({'error': '\n'.join(error_msg_c)})
                    child_list.append(child)

                if child_list:
                    data.pop('childs')
                    data.update({'childs': child_list})

                validated_data.pop('childs')
                validated_data.update({'childs': validated_child_data})

        return validated_data, error_flag

    @api.multi
    def get_mem_id(self, mem_id):
        """
            To create or retrieve Membsership ID
            :param mem_id: Membsership ID
            :return: membership_id: Membership ID's record set
        """
        membership_id_obj = self.env['membership.master']
        membership_id = membership_id_obj.search([('name', '=', mem_id)])
        if not membership_id:
            self._cr.execute(
                """INSERT INTO membership_master(name,is_legacy_data) values ('""" + mem_id + """',true) RETURNING id""")
            record_id = self.env.cr.fetchall()
            membership_id = membership_id_obj.browse(record_id[0][0])
        return membership_id

    @api.multi
    def upload_mem_id(self):
        """
            To import Membership ID
        """
        file_name = self.sheet_data
        if not file_name:
            raise UserError(_('Please Choose The File!'))
        val = base64.decodestring(file_name)
        dict_list, header = self.get_sheet_data(val, False)
        error_data = []
        count = 1
        _logger.info('---------len(dict_list)---------: %s ' % len(dict_list))
        for data in dict_list:
            try:
                _logger.info('---------count---------: %s ' % count)
                count += 1
                mem_id = str(data.get('membership_id')).strip()
                if mem_id:
                    if len(mem_id) != 6:
                        data.update({'error': 'Length of Membership ID should be 6 character.'})
                        error_data.append(data)
                        continue
                    # Get or create Membsership ID
                    membership_id = self.get_mem_id(mem_id)

                    # org. part
                    if str(data.get('org_name')).strip():
                        org_id = self.env['res.partner'].search(
                            [('type', '!=', 'end_client'), ('is_portal', '=', True), ('is_company', '=', True),
                             ('name', 'ilike', str(data.get('org_name')).strip()),
                             ('active_memid', '=', membership_id.id)])
                        org_record_id = False
                        if not org_id:
                            self._cr.execute("""INSERT INTO res_partner(name,type,is_portal,is_company,active_memid,
                                                membership_id,is_legacy_data,active,customer,display_name) 
                                                values (%s,'contact',true,true,%s,%s,true,true,true,%s) 
                                                RETURNING id""", (str(data.get('org_name')).strip(), membership_id.id,
                                                                  membership_id.name,
                                                                  str(data.get('org_name')).strip()))
                            org_record_id = self.env.cr.fetchall()[0][0]
                        else:
                            org_record_id = org_id.id
                        # map org. and mem_id
                        self._cr.execute("""SELECT * FROM membership_org_rel WHERE mem_id=%s AND org_id=%s""",
                                         (membership_id.id, org_record_id))
                        org_ids = self.env.cr.fetchall()
                        if not org_ids:
                            self._cr.execute("""INSERT INTO membership_org_rel(mem_id,org_id) 
                                                values (%s,%s)""", (membership_id.id, org_record_id))

                    # domain part
                    if str(data.get('domain')).strip():
                        domain_id = self.env['org.domain'].search([('name', '=', str(data.get('domain')).strip())])
                        domain_record_id = False
                        if not domain_id:
                            self._cr.execute("""INSERT INTO org_domain(name) values (%s) RETURNING id""",
                                             (str(data.get('domain')).strip(), ))
                            domain_record_id = self.env.cr.fetchall()[0][0]
                        else:
                            domain_record_id = domain_id.id
                        # map domain and mem_id
                        self._cr.execute("""SELECT * FROM memid_domain_rel WHERE memid=%s AND domain_id=%s""",
                                         (membership_id.id, domain_record_id))
                        domain_ids = self.env.cr.fetchall()
                        if not domain_ids:
                            self._cr.execute("""INSERT INTO memid_domain_rel(memid,domain_id) values (%s,%s)""",
                                             (membership_id.id, domain_record_id))

                    self._cr.commit()
                else:
                    data.update({'error': 'Membership ID is missing.'})
                    error_data.append(data)
                    continue
            except Exception as e:
                _logger.info('-------upload_mem_id----e---: %s ' % e)
                data.update({'error': e})
                error_data.append(data)
        if error_data:
            # Creating separate csv file to log issue with data
            self.create_error_log_file(error_data, 'memid_org_domain_import_issue', header, False)
            _logger.info('-------csv_file_created-------')
        return True

    @api.multi
    def upload_client_type(self):
        """
            To import client type
        """
        file_name = self.sheet_data
        if not file_name:
            raise UserError(_('Please Choose The File!'))
        val = base64.decodestring(file_name)
        fp = BytesIO()
        fp.write(val)
        wb = xlrd.open_workbook(file_contents=fp.getvalue())
        wb.sheet_names()
        sheet_name = wb.sheet_names()
        sh = wb.sheet_by_index(0)
        sh = wb.sheet_by_name(sheet_name[0])
        n_rows = sh.nrows
        for row in range(1, n_rows):
            try:
                if sh.row_values(row) and sh.row_values(row)[24]:
                    client_type = str(sh.row_values(row)[24]).strip()
                    client_type_id = self.env['client.type.config'].search([('name', '=', client_type)])
                    if not client_type_id:
                        self._cr.execute("""INSERT INTO client_type_config(name) 
                                                values ('""" + client_type + """') RETURNING id""")
            except Exception as e:
                _logger.info('-------upload_client_type----e---: %s ' % e)
        return True

    @api.multi
    def upload_client_preferences(self):
        """
            To import client preferences
        """
        file_name = self.sheet_data
        if not file_name:
            raise UserError(_('Please Choose The File!'))
        val = base64.decodestring(file_name)
        dict_list, header = self.get_sheet_data(val, False)
        error_data = []
        count = 1
        _logger.info('---------len(dict_list)---------: %s ' % len(dict_list))
        for data in dict_list:
            try:
                _logger.info('---------count---------: %s ' % count)
                count += 1
                validated_data, error_flag = self.validate_data(data, False)
                if error_flag:
                    error_data.append(data)
                    continue

                client_type_id, org_id = False, False
                membership_id = self.get_mem_id(validated_data.get('membership_id'))

                if str(data.get('client_category')).strip():
                    client_type_id = self.env['client.type.config'].search(
                        [('name', '=', str(data.get('client_category')).strip())])

                if str(data.get('org_name')).strip():
                    org_id = self.env['res.partner'].search(
                        [('type', '!=', 'end_client'), ('is_portal', '=', True), ('is_company', '=', True),
                         ('name', '=', str(data.get('org_name')).strip()), ('active_memid', '=', membership_id.id)])

                partner_id = self.env['res.partner'].search(
                    [('type', '!=', 'end_client'), ('is_portal', '=', True), ('is_company', '=', False),
                     ('email', '=', validated_data.get('email'))])

                client_name = validated_data.get('first_name')
                if validated_data.get('last_name').strip():
                    client_name = client_name + ' ' + validated_data.get('last_name').strip()

                phone = False
                if data.get('phone'):
                    if type(data.get('phone')) == str:
                        phone = data.get('phone')
                    elif type(data.get('phone')) == float:
                        phone = str(int(data.get('phone'))).strip()

                vals = {
                    'name': client_name,
                    'type': 'contact',
                    'active': True,
                    'is_portal': True,
                    'is_company': False,
                    'first_name': validated_data.get('first_name'),
                    'last_name': validated_data.get('last_name').strip() if validated_data.get(
                        'last_name').strip() else False,
                    'email': validated_data.get('email'),
                    'phone': phone,
                    'client_currency_id': validated_data.get('currency').id if validated_data.get(
                        'currency_id') else self.env.ref('base.USD').id,
                    'client_type_id': client_type_id.id if client_type_id else False,
                    'membership_id': membership_id.id,
                    'active_memid': membership_id.id,
                    'parent_id': org_id.id if org_id else False,
                    'new_client': False,
                    'website_published': True,
                    'tz': validated_data.get('tz'),
                    'organization_line': [(0, 0, {'membership_id': membership_id.id, 'is_active': True,
                                                  'organization_id': org_id.id})] if org_id else [
                        (0, 0, {'membership_id': membership_id.id, 'is_active': True})],
                    'send_email_to_client': False,
                    'deliver_file_on_email': False,
                    'delete_doc_after': False,
                    'send_invoice_on_mail': False,
                    'po_required': False,
                    'send_inv_monthly': False,
                    'is_legacy_data': True,
                }
                if not partner_id:
                    self.env['res.partner'].create(vals)
                    # Grant Portal Access
                    if self.client_type == 'create_portal_user':
                        partner_id.grant_portal_access()
                else:
                    if partner_id.first_name != validated_data.get(
                            'first_name') and partner_id.last_name != validated_data.get('last_name'):
                        data.update({'error': 'Same email id is already used for %s client.' % partner_id.name})
                        error_data.append(data)
                        continue

                    org_line_id = partner_id.organization_line.filtered(lambda l: l.is_active)
                    if org_line_id:
                        vals.update({
                            'organization_line': [(1, org_line_id.id, {'is_active': False})]
                        })
                    self.env['res.partner'].write(vals)
                membership_id.write({'client_id': partner_id.id})
                self._cr.commit()
            except Exception as e:
                _logger.info('-------upload_client_preferences----e---: %s ' % e)
                data.update({'error': e})
                error_data.append(data)
        if error_data:
            # Creating separate csv file to log issue with data
            self.create_error_log_file(error_data, 'client_import_issue', header, False)
            _logger.info('-------Error file created-------')
        return True

    @api.multi
    def upload_inquiries(self):
        """
            To import inquiries
        """
        file_name = self.sheet_data
        if not file_name:
            raise UserError(_('Please Choose The File!'))
        val = base64.decodestring(file_name)
        dict_list, header = self.get_sheet_data(val, True)
        error_data = []
        _logger.info('---------len(dict_list)---------: %s ' % len(dict_list))
        count = 1
        for data in dict_list:
            try:
                _logger.info('---------count---------: %s ' % count)
                count += 1
                inquire_id = self.env['sale.order'].search(
                    [('type', '=', 'inquiry'), ('legacy_parent_asn_no', '=', data.get('asn_no').strip())])
                if inquire_id:
                    continue
                if data:
                    validated_data, error_flag = self.validate_data(data, True)
                    if error_flag:
                        error_data.append(data)
                        continue
                    if validated_data:
                        inquiry_id = False
                        partner_id = self.env['res.partner'].search([('email', '=', validated_data.get('email'))])

                        tax_ids = self.env['account.tax'].sudo().search(
                            [('currency_id', '=', partner_id.client_currency_id.id), ('type_tax_use', '=', 'sale')])

                        priority = False
                        if validated_data.get('delivery_option').lower() in ['standard', 'express']:
                            priority = validated_data.get('delivery_option').lower()
                        elif validated_data.get('delivery_option').lower() == 'super express':
                            priority = 'super_express'

                        data_dict = {
                            'mem_id': self.get_mem_id(validated_data.get('membership_id')).id,
                            'partner_id': partner_id.id,
                            'type': "inquiry",
                            'inquiry_state': 'assign',
                            'state': 'draft',
                            'user_id': False,
                            'currency_id': validated_data.get('currency').id,
                            'tax_percent_ids': [(6, 0, tax_ids.ids)],
                            'source_lang_id': validated_data.get('src_lang').id,
                            'unit_id': validated_data.get('src_lang').unit_id.id if validated_data.get(
                                'src_lang').unit_id else False,
                            'note': validated_data.get('client_instruction').strip(),
                            'organization_id': partner_id.parent_id.id if partner_id.parent_id else False,
                            'is_legacy_data': True,

                            'service_level_id': validated_data.get('translation_level').id,
                            'product_id': validated_data.get('product').id,
                            'po_number': str(validated_data.get('po_no')) if validated_data.get('po_no') else False,
                            'mark_as_special': True if validated_data.get('special_asn').lower() == 'yes' else False,
                            'mark_as_trial': True if validated_data.get('special_asn').lower() == 'trial' else False,
                            'trial_flag': True if validated_data.get('special_asn').lower() == 'trial' else False,
                            'area_type': 'subject_area' if validated_data.get(
                                'is_subject_area').strip().lower() == 'yes' else 'industrial_area',
                            'subject_industrial_area_level1_id': validated_data.get('level_1').id if validated_data.get(
                                'level_1') else False,
                            'subject_industrial_area_level2_id': validated_data.get('level_2').id if validated_data.get(
                                'level_2') else False,
                            'subject_industrial_area_level3_id': validated_data.get('level_3').id if validated_data.get(
                                'level_3') else False,
                            'priority': priority,
                            'quote_confirmation_datetime': validated_data.get('datetime_of_confirmation'),
                            'legacy_parent_actual_delivery_datetime': validated_data.get('actual_delivery_datetime'),
                            'client_deadline': validated_data.get('client_delivery_datetime'),
                            'legacy_parent_asn_status': validated_data.get('status'),
                            'legacy_parent_asn_no': validated_data.get('asn_no'),
                            'legacy_serial_no': str(int(validated_data.get('serial_no'))),
                            'legacy_parent_total_fees': float(validated_data.get('usd_total_fees')),
                        }

                        if 'childs' not in validated_data:
                            data_dict.update({
                                'legacy_data_line': [(0, 0, {
                                    'serial_no': str(int(validated_data.get('serial_no'))),
                                    'status': validated_data.get('status').strip(),
                                    'asn_no': validated_data.get('asn_no').strip(),
                                    'target_lang_id': validated_data.get('target_lang').id,
                                    'client_deadline': validated_data.get('client_delivery_datetime'),
                                    'actual_delivery_datetime': validated_data.get('actual_delivery_datetime'),
                                    'instruction': validated_data.get('client_instruction').strip(),
                                    'word_count': int(float(validated_data.get('word_count'))),
                                    'weighted_word_count': int(float(validated_data.get('weighted_word_count'))),
                                    'total_fee': float(validated_data.get('usd_total_fees')),
                                })],
                                'target_lang_ids': [(4, validated_data.get('target_lang').id)],
                            })

                        if 'RR' in validated_data.get('asn_no'):
                            data_dict.update({
                                'name': 'RR',
                                'is_rr_inquiry': True,
                                'parent_asn_ref_id': False,
                            })

                        if validated_data.get('reject_date') and validated_data.get('reject_reason'):
                            reject_id = self.env['rejection.reason'].search(
                                [('reason', '=', validated_data.get('reject_reason')), ('type', '=', 'inquiry')])
                            data_dict.update({
                                'reject_date': pytz.timezone('Asia/Kolkata').localize(
                                    validated_data.get('reject_date')).astimezone(pytz.utc),
                                'reject_reason': reject_id.id if reject_id else False,
                            })

                        inquiry_id = self.env['sale.order'].create(data_dict)

                    if validated_data.get('childs'):
                        for child_data in validated_data.get('childs'):
                            temp_client_deadline = validated_data.get('client_delivery_datetime')
                            if temp_client_deadline < child_data.get('client_delivery_datetime'):
                                temp_client_deadline = child_data.get('client_delivery_datetime')
                            inquiry_id.write({
                                'legacy_data_line': [(0, 0, {
                                    'serial_no': str(int(child_data.get('serial_no'))),
                                    'status': child_data.get('status').strip(),
                                    'asn_no': child_data.get('asn_no').strip(),
                                    'target_lang_id': child_data.get('target_lang').id,
                                    'client_deadline': child_data.get('client_delivery_datetime'),
                                    'actual_delivery_datetime': child_data.get('actual_delivery_datetime'),
                                    'instruction': child_data.get('client_instruction').strip(),
                                    'word_count': int(float(child_data.get('word_count'))),
                                    'weighted_word_count': int(float(child_data.get('weighted_word_count'))),
                                    'total_fee': float(child_data.get('usd_total_fees')),
                                })],
                                'target_lang_ids': [(4, child_data.get('target_lang').id)],
                                'client_deadline': temp_client_deadline,
                                'note': inquiry_id.note + '\n' + child_data.get(
                                    'client_instruction').strip() if inquiry_id.note else child_data.get(
                                    'client_instruction').strip(),
                            })
                    self._cr.commit()
                    self._cr.execute("update sale_order set inquiry_date=%s, create_date=%s where id=%s", (
                                        data.get('date_of_inq').strftime('%Y-%m-%d'),
                                        validated_data.get('date_of_inq').strftime('%Y-%m-%d %H:%M:%S'), inquiry_id.id))
            except Exception as e:
                _logger.info('-------upload_inquiries----e---: %s ' % e)
                if 'error' not in data:
                    data.update({'error': e})
                else:
                    error_t = '\n'.join([data.get('error'), e])
                    data.update({'error': error_t})
                error_data.append(data)
        if error_data:
            # Creating separate csv file to log issue with data
            self.create_error_log_file(error_data, 'inquiries_import_issue', header, True)
            _logger.info('-------Error file created----')
        return True

    @api.multi
    def create_quotations(self):
        """
            To create quotations of imported inquiries
        """
        inquiry_ids = self.env['sale.order'].search([('is_legacy_data', '=', True), ('type', '=', 'inquiry')])
        _logger.info('---------len(inquiry_ids)---------: %s ' % len(inquiry_ids))
        if inquiry_ids:
            error_data = []
            count = 1
            for inquiry_id in inquiry_ids:
                try:
                    _logger.info('---------count---------: %s ' % count)
                    count += 1
                    quote_id = self.env['sale.order'].search(
                        [('type', '=', 'quotation'), ('inquiry_id', '=', inquiry_id.id), ('is_legacy_data', '=', True)])
                    if quote_id:
                        continue
                    service_level, order_lines = [], []
                    if inquiry_id.service_level_id:
                        service_level = [(0, 0, {
                            'service_level_id': inquiry_id.service_level_id.id if inquiry_id.service_level_id
                            else False,
                            'visible_to_client': True,
                            'is_original_service_level': True
                        })]
                    analyse_percent_type_lines = self.env['analyse.percent.type'].search([])
                    # sale order line
                    for line in inquiry_id.legacy_data_line:
                        memsource_lines = [(0, 0, {'percent_type': rec.id, 'weighted_count': line.weighted_word_count,
                                                   'unit_count': line.word_count, 'weighted_percent': 0.0})
                                           if rec.name == 'Machine Translation' else (0, 0, {'percent_type': rec.id,
                                                                                             'weighted_percent': 0.0,
                                                                                             'unit_count': 0.0,
                                                                                             'weighted_count': 0.0})
                                           for rec in analyse_percent_type_lines]

                        order_lines.append((0, 0, {
                            'name': inquiry_id.name + '_' + line.target_lang_id.initial_code,
                            'source_lang_id': inquiry_id.source_lang_id.id,
                            'unit_id': inquiry_id.source_lang_id.unit_id.id if inquiry_id.source_lang_id.unit_id
                                else False,
                            'target_lang_id': line.target_lang_id.id,
                            'sale_instruction_line': [(0, 0, {'name': line.instruction, 'is_original_ins': True,
                                                              'mark_reviewed': True, 'send_ins_to_pm': True})],
                            'memsource_line': memsource_lines,
                            'is_legacy_data': True,
                        }))
                    # sale order
                    quote_vals = {
                        'name': inquiry_id.name,
                        'type': 'quotation',
                        'inquiry_state': 'process',
                        'source_lang_id': inquiry_id.source_lang_id.id,
                        'unit_id': inquiry_id.source_lang_id.unit_id.id if inquiry_id.source_lang_id.unit_id else False,
                        'sale_bool': True,
                        'partner_id': inquiry_id.partner_id.id,
                        'state': 'draft',
                        'target_lang_ids': [(6, 0, inquiry_id.target_lang_ids.ids)],
                        'inquiry_date': inquiry_id.inquiry_date,
                        'order_line': order_lines,
                        'service_level_line': service_level,
                        'project_management_cost': 0.0,
                        'tax_percent_ids': [(6, 0, inquiry_id.tax_percent_ids.ids)],
                        'inquiry_id': inquiry_id.id,
                        'is_file_revision': inquiry_id.is_file_revision,
                        'service_level_id': inquiry_id.service_level_id.id if inquiry_id.service_level_id else False,
                        'currency_id': inquiry_id.currency_id.id if inquiry_id.currency_id else False,
                        'client_deadline': inquiry_id.client_deadline,
                        'mem_id': inquiry_id.mem_id.id,
                        'organization_id': inquiry_id.organization_id.id if inquiry_id.organization_id else False,
                        'user_id': inquiry_id.user_id.id if inquiry_id.user_id else False,
                        'instruction_line': [(0, 0, {'name': inquiry_id.note, 'is_original_ins': True})],
                        'advance_payment': '0',
                        'advance_payment_value': 0,
                        'product_id': inquiry_id.product_id.id if inquiry_id.product_id else False,
                        'area_type': inquiry_id.area_type,
                        'subject_industrial_area_level1_id': inquiry_id.subject_industrial_area_level1_id.id
                        if inquiry_id.subject_industrial_area_level1_id else False,
                        'subject_industrial_area_level2_id': inquiry_id.subject_industrial_area_level2_id.id
                        if inquiry_id.subject_industrial_area_level2_id else False,
                        'subject_industrial_area_level3_id': inquiry_id.subject_industrial_area_level3_id.id
                        if inquiry_id.subject_industrial_area_level3_id else False,
                        'mark_as_special': inquiry_id.mark_as_special,
                        'priority': inquiry_id.priority,
                        'po_number': inquiry_id.po_number if inquiry_id.po_number else False,
                        'quote_confirmation_datetime': inquiry_id.quote_confirmation_datetime
                        if inquiry_id.quote_confirmation_datetime else False,
                        'deadline': inquiry_id.legacy_parent_actual_delivery_datetime,
                        'is_legacy_data': True,
                    }
                    if inquiry_id.is_rr_inquiry:
                        quote_vals.update({
                            'is_rr_inquiry': inquiry_id.is_rr_inquiry,
                            'parent_asn_ref_id': False,
                        })

                    if inquiry_id.reject_date and inquiry_id.reject_reason:
                        quote_vals.update({
                            'reject_date': inquiry_id.reject_date,
                            'reject_reason': inquiry_id.reject_reason.id,
                        })

                    quote_id = self.env['sale.order'].create(quote_vals)
                    if quote_id:
                        # translation level on quotation
                        self.env['add.translation.level.line'].create({
                            'sale_order_id': quote_id.id,
                            'service_level_id': inquiry_id.service_level_id.id,
                            'reccommend': True,
                            'visible_to_client': True})

                        # translation level in sale.order.line
                        for line in quote_id.order_line:
                            legacy_data_line = inquiry_id.legacy_data_line.filtered(
                                lambda l: l.target_lang_id.id == line.target_lang_id.id)

                            self.env['service.level.line'].create({
                                'unit_rate': 0.0,
                                'fee': legacy_data_line.total_fee,
                                'deadline': legacy_data_line.client_deadline,
                                'service_level_id': inquiry_id.service_level_id.id,
                                'reccommend': True,
                                'visible_to_client': True,
                                'add_translation_level_id': quote_id.add_translation_level_line[0].id,
                                'sale_service_line_id': line.id,
                            })

                        inquiry_id.write({
                            'inquiry_state': 'process',
                            'write_date': inquiry_id.create_date,
                            'legacy_quotation_created': True,
                        })
                    self._cr.commit()
                except Exception as e:
                    _logger.info('-------create_quotations----e---: %s ' % e)
                    error_data.append({
                        'inquiry_id': inquiry_id,
                        'error': e,
                    })
                    inquiry_id.write({'legacy_quotation_created': False})
            _logger.info('-----create_quotations--error_data-------: %s ' % error_data)
        return True

    @api.multi
    def create_asn(self):
        """
            To create asn of imported inquiries
        """
        quotation_ids = self.env['sale.order'].search([('is_legacy_data', '=', True), ('type', '=', 'quotation')])
        _logger.info('---------len(quotation_ids)---------: %s ' % len(quotation_ids))
        if quotation_ids:
            error_data = []
            count = 1
            for quotation_id in quotation_ids:
                try:
                    _logger.info('---------count---------: %s ' % count)
                    count += 1

                    if not quotation_id.is_rr_inquiry:
                        asn_id = self.env['sale.order'].search([('is_legacy_data', '=', True), ('type', '=', 'asn'),
                                                                ('quotation_ref_id', '=', quotation_id.id)])
                        if asn_id:
                            continue
                    elif quotation_id.is_rr_inquiry:
                        rr_asn_id = self.env['assignment'].search([('is_legacy_data', '=', True),
                                                                ('quotation_id', '=', quotation_id.id)])
                        if rr_asn_id:
                            continue

                    inq_id = quotation_id.inquiry_id
                    if not quotation_id.is_rr_inquiry:
                        vals = {
                            'name': inq_id.legacy_parent_asn_no,
                            'quotation_ref_id': quotation_id.id,
                            'service_level_id': quotation_id.service_level_id.id,
                            'source_lang_id': quotation_id.source_lang_id.id,
                            'unit_id': quotation_id.source_lang_id.unit_id.id if
                            quotation_id.source_lang_id.unit_id else False,
                            'partner_id': quotation_id.partner_id.id,
                            'type': "asn",
                            'instruction_line': [(0, 0, {
                                                    'name': line.name,
                                                    'mark_reviewed': True,
                                                    'is_original_ins': line.is_original_ins,
                                                }) for line in quotation_id.instruction_line],
                            'target_lang_ids': [(6, 0, quotation_id.target_lang_ids.ids)],
                            'state': 'draft',
                            'deadline': quotation_id.deadline,
                            'char_count': sum(quotation_id.order_line.mapped('character_count')) or 0,
                            'order_line': [(0, 0, {
                                'product_id': quotation_id.product_id.id,
                                'price_unit': inq_id.legacy_parent_total_fees or 0.0,
                            })],
                            'currency_id': quotation_id.currency_id.id if quotation_id.currency_id else False,
                            'organization_id': quotation_id.organization_id.id if quotation_id.organization_id
                            else False,
                            'end_client_id': quotation_id.end_client_id.id if quotation_id.end_client_id else False,
                            'client_deadline': quotation_id.client_deadline,
                            'parent_id': quotation_id.parent_id.id if quotation_id.parent_id.id else False,
                            'mem_id': quotation_id.mem_id.id,
                            'tax_percent_ids': [(6, 0, quotation_id.tax_percent_ids.ids)],
                            'ks_global_discount_rate': quotation_id.ks_global_discount_rate,
                            'ks_global_discount_type': quotation_id.ks_global_discount_type,
                            'add_premium_rate': quotation_id.add_premium_rate,
                            'add_premium_type': quotation_id.add_premium_type,
                            'amount_undiscounted': inq_id.legacy_parent_total_fees
                            if inq_id.legacy_parent_total_fees > 0.0 else 0.0,
                            'ks_amount_discount': 0.0,
                            'premium_amount': 0.0,
                            'amount_untaxed': inq_id.legacy_parent_total_fees if inq_id.legacy_parent_total_fees > 0.0
                            else 0.0,
                            'amount_tax': 0.0,
                            'amount_total': inq_id.legacy_parent_total_fees if inq_id.legacy_parent_total_fees > 0.0
                            else 0.0,
                            'priority': quotation_id.priority,
                            'product_id': quotation_id.product_id.id,
                            'area_type': quotation_id.area_type,
                            'subject_industrial_area_level1_id': quotation_id.subject_industrial_area_level1_id.id,
                            'subject_industrial_area_level2_id': quotation_id.subject_industrial_area_level2_id.id,
                            'subject_industrial_area_level3_id': quotation_id.subject_industrial_area_level3_id.id,
                            'level3_other_area_bool': quotation_id.level3_other_area_bool
                            if quotation_id.level3_other_area_bool else False,
                            'level3_other_area': quotation_id.level3_other_area if quotation_id.level3_other_area
                            else False,
                            'advance_payment': quotation_id.advance_payment,
                            'advance_payment_value': quotation_id.advance_payment_value,
                            'advance_payment_amount': 0.0,
                            'advance_pending_amount': 0.0,
                            'parent_asn_complete_date': inq_id.legacy_parent_actual_delivery_datetime,
                            'is_legacy_data': True,
                        }
                        asn_id = self.env['sale.order'].create(vals)
                        if asn_id:
                            asn_id.action_confirm()
                            if inq_id.legacy_parent_asn_status == 'Completed':
                                asn_id.write({
                                    'state': 'done',
                                    'is_delivered': True
                                })
                                quotation_id.write({'state': 'sale'})
                            if inq_id.legacy_parent_asn_status == 'Cancelled':
                                asn_id.write({
                                    'state': 'cancel',
                                    'reject_date': inq_id.reject_date,
                                    'reject_reason': inq_id.reject_reason,
                                })
                                quotation_id.write({'state': 'cancel'})
                                inq_id.write({'state': 'cancel'})
                    for line in inq_id.legacy_data_line:
                        child_asn_vals = {
                            'name': line.asn_no,
                            'source_lang_id': quotation_id.source_lang_id.id,
                            'service_level_id': quotation_id.service_level_id.id,
                            'deadline': line.client_deadline,
                            'character_count': line.word_count,
                            'partner_id': quotation_id.partner_id.id,
                            'quotation_id': quotation_id.id,
                            'currency_id': quotation_id.currency_id.id or False,
                            'state': 'new',
                            'target_lang_id': line.target_lang_id.id,
                            'assignment_instruction_line': [(0, 0, {
                                'name': line.instruction,
                                'ins_for_pm': True,
                                'mark_reviewed': True,
                                'is_original_ins': True,
                            })],
                            'membership_id': quotation_id.mem_id.id,
                            'translation_fee': line.total_fee,
                            'total_addons_fee': 0.0,
                            'project_management_cost': 0.0,
                            'gross_fee': line.total_fee,
                            'discount': 0.0,
                            'premium': 0.0,
                            'subtotal_without_tax': line.total_fee,
                            'tax': 0.0,
                            'mark_as_special': quotation_id.mark_as_special,
                            'mark_as_trial': quotation_id.mark_as_trial,
                            'trial_flag': quotation_id.trial_flag,
                            'total_fees': line.total_fee,
                            'priority': quotation_id.priority,
                            'product_id': quotation_id.product_id.id,
                            'area_type': quotation_id.area_type,
                            'subject_industrial_area_level1_id': quotation_id.subject_industrial_area_level1_id.id,
                            'subject_industrial_area_level2_id': quotation_id.subject_industrial_area_level2_id.id,
                            'subject_industrial_area_level3_id': quotation_id.subject_industrial_area_level3_id.id,
                            'level3_other_area_bool': quotation_id.level3_other_area_bool if
                            quotation_id.level3_other_area_bool else False,
                            'level3_other_area': quotation_id.level3_other_area if quotation_id.level3_other_area
                            else False,
                            'received_on_pm': False,
                            'advance_payment': quotation_id.advance_payment,
                            'advance_payment_value': quotation_id.advance_payment_value,
                            'advance_payment_amount': 0.0,
                            'advance_pending_amount': 0.0,
                            'delivered_on': line.actual_delivery_datetime,
                            'is_legacy_data': True,
                        }
                        if not quotation_id.is_rr_inquiry:
                            child_asn_vals.update({'parent_asn_id': asn_id.id})
                        if quotation_id.is_rr_inquiry:
                            child_asn_vals.update({
                                'is_revision_asn': True,
                                'parent_asn_ref_id': False,
                                'asn_previous_state': 'new',
                            })
                        child_asn_id = self.env['assignment'].create(child_asn_vals)
                        if child_asn_id:
                            if line.status == 'Completed':
                                child_asn_id.write({'state': 'deliver'})
                                quotation_id.write({'state': 'sale'})
                            if line.status == 'Cancelled':
                                child_asn_id.write({
                                    'state': 'cancel',
                                    'reject_date': inq_id.reject_date,
                                    'note': inq_id.reject_reason,
                                })
                                quotation_id.write({'state': 'cancel'})
                                inq_id.write({'state': 'cancel'})
                    inq_id.write({'legacy_asn_created': True})
                    self._cr.commit()
                except Exception as e:
                    _logger.info('-------create_asn----e---: %s ' % e)
                    error_data.append({
                        'quotation_id': quotation_id,
                        'error': e,
                    })
                    inq_id.write({'legacy_asn_created': False})
            _logger.info('-----create_asn--error_data-------: %s ' % error_data)
        return True

    @api.multi
    def link_original_n_rr_asn(self):
        """
            To link original with revision ASNs
        """
        rr_asn_ids = self.env['assignment'].search([('is_legacy_data', '=', True), ('is_revision_asn', '=', True)])
        if rr_asn_ids:
            error_data = []
            count = 1
            for rr_asn_id in rr_asn_ids:
                try:
                    _logger.info('---------count---------: %s ' % count)
                    count += 1
                    original_asn_name = rr_asn_id.name.split('_')[0]
                    asn_id = self.env['sale.order'].search([('is_legacy_data', '=', True), ('type', '=', 'asn'),
                                                            ('name', '=', original_asn_name)])
                    if asn_id:
                        rr_asn_id.write({'parent_asn_ref_id': asn_id.id})
                        rr_asn_id.quotation_id.write({'parent_asn_ref_id': asn_id.id})
                        rr_asn_id.quotation_id.inquiry_id.write({'parent_asn_ref_id': asn_id.id})
                    else:
                        error_data.append({
                            'rr_asn_id': rr_asn_id,
                            'error': 'Original ASN is not found.',
                        })
                except Exception as e:
                    _logger.info('-------link_original_n_rr_asn----e---: %s ' % e)
                    error_data.append({
                        'rr_asn_id': rr_asn_id,
                        'error': e,
                    })
            _logger.info('-----link_original_n_rr_asn--error_data-------: %s ' % error_data)
        return True

    @api.multi
    def update_asn_seq(self):
        """
            To update original and revision asn's sequence
        """
        asn_ids = self.env['sale.order'].search([('is_legacy_data', '=', True), ('type', '=', 'asn')])
        rr_asn_ids = self.env['assignment'].search([('is_legacy_data', '=', True), ('is_revision_asn', '=', True)])
        # For original asn
        if asn_ids:
            asn_name_list = asn_ids.mapped('name')
            asn_name_list.sort()
            group_by_asn = groupby(asn_name_list, lambda string: string.split('-')[0])
            group_by_asn_list = [list(group) for element, group in group_by_asn]
            for asn_list in group_by_asn_list:
                asn_highest_seq_no = max([int(asn_name.split('-')[1]) for asn_name in asn_list])
                membership_id = self.env['membership.master'].search([('name', '=', asn_list[0].split('-')[0])])
                if membership_id:
                    membership_id.write({'sequence': int(asn_highest_seq_no) + 1})

        # For Revision asn
        if rr_asn_ids:
            rr_asn_name_list = rr_asn_ids.mapped('name')
            rr_asn_name_list.sort()
            group_by_rr_asn = groupby(rr_asn_name_list, lambda string: string.split('_')[0])
            group_by_rr_asn_list = [list(group) for element, group in group_by_rr_asn]
            for rr_asn_list in group_by_rr_asn_list:
                rr_asn_highest_seq_no = max([int(rr_asn_name.split('-')[2]) for rr_asn_name in rr_asn_list])
                assignment_id = self.env['sale.order'].search([('name', '=', rr_asn_list[0].split('_')[0]),
                                                               ('type', '=', 'asn')])
                if assignment_id:
                    assignment_id.write({'rr_sequence': int(rr_asn_highest_seq_no) + 1})
        return True

    @api.multi
    def update_active_org_in_client(self):
        """ To update active organization in client preference """
        partner_ids = self.env['res.partner'].search([('type', '!=', 'end_client'), ('is_portal', '=', True),
                                                      ('is_company', '=', False), ('is_legacy_data', '=', True)])
        _logger.info('---------len(partner_ids)---------: %s ' % len(partner_ids))
        if partner_ids:
            error_data = []
            count = 1
            for partner_id in partner_ids:
                try:
                    _logger.info('---------count---------: %s ' % count)
                    count += 1
                    client_org_line_id = self.env['client.org.line'].search(
                        [('client_id', '=', partner_id.id), ('is_active', '=', True)])
                    if client_org_line_id:
                        if client_org_line_id.organization_id:
                            partner_id.write({'parent_id': client_org_line_id.organization_id.id})
                except Exception as e:
                    _logger.info('-------update_active_org_in_client----e---: %s ' % e)
                    error_data.append({
                        'partner_id': partner_id,
                        'error': e,
                    })
            _logger.info('-----update_active_org_in_client--error_data-------: %s ' % error_data)
        return True

    @api.multi
    def update_org_in_inquiries(self):
        """ To update organization in inquiries """
        inquiry_ids = self.env['sale.order'].search([('is_legacy_data', '=', True), ('type', '=', 'inquiry')])
        _logger.info('---------len(inquiry_ids)---------: %s ' % len(inquiry_ids))
        if inquiry_ids:
            error_data = []
            count = 1
            for inquiry_id in inquiry_ids:
                try:
                    _logger.info('---------count---------: %s ' % count)
                    count += 1
                    inquiry_id.write({
                        'organization_id': inquiry_id.partner_id.parent_id.id if inquiry_id.partner_id.parent_id
                        else False
                    })
                except Exception as e:
                    _logger.info('-------update_org_in_inquiries----e---: %s ' % e)
                    error_data.append({
                        'partner_id': inquiry_id,
                        'error': e,
                    })
            _logger.info('-----update_org_in_inquiries--error_data-------: %s ' % error_data)
        return True

    @api.multi
    def update_org_in_quotations(self):
        """ To update organization in quotations """
        quotation_ids = self.env['sale.order'].search([('is_legacy_data', '=', True), ('type', '=', 'quotation')])
        _logger.info('---------len(quotation_ids)---------: %s ' % len(quotation_ids))
        if quotation_ids:
            error_data = []
            count = 1
            for quotation_id in quotation_ids:
                try:
                    _logger.info('---------count---------: %s ' % count)
                    count += 1
                    quotation_id.write({
                        'organization_id': quotation_id.inquiry_id.organization_id.id
                        if quotation_id.inquiry_id.organization_id else False
                    })
                except Exception as e:
                    _logger.info('-------update_org_in_quotations----e---: %s ' % e)
                    error_data.append({
                        'partner_id': quotation_id,
                        'error': e,
                    })
            _logger.info('-----update_org_in_quotations--error_data-------: %s ' % error_data)
        return True

    def convert_gmt_to_ist_tz(self, value):
        """
            Convert datetime GMT to IST
            :param value: datetime to be convert
            :return: Converted IST datetime
        """
        res_datetime_str = fields.Datetime.from_string(value)
        datetime_loc = pytz.UTC.localize(res_datetime_str)
        ist_date_time = datetime_loc.astimezone(pytz.timezone('Asia/Kolkata'))
        return ist_date_time

    @api.multi
    def import_bi_report_data(self):
        sale_order = self.env['sale.order'].search([('is_legacy_data', '=', False)], order='id asc')
        if sale_order:
            for row in sale_order:
                bi_data_id = self.env['bi.daily.report'].sudo().search(['|', '|', ('inquiry_id', '=', row.id), ('quote_id', '=', row.id), ('parent_asn_id', '=', row.id)])
                if not bi_data_id:
                    if row.type == 'inquiry':
                        bi_report_inq_vals = {
                            'inquiry_id': row.id,
                            'website_name': 'Global',
                            'inquiry_date': self.convert_gmt_to_ist_tz(row.create_date),
                            'inquiry_state': row.inquiry_state,
                            'mem_id': row.mem_id.name,
                            'client_name': row.partner_id.name,
                            'target_lang_ids': [(6, 0, row.target_lang_ids.ids)],
                            'service': ', '.join([row.source_lang_id.name + ' - ' + rec.name for rec in row.target_lang_ids]) if row.target_lang_ids else '',
                            'organisation_name': row.organization_id.name if row.organization_id else '',
                            'client_deadline': self.convert_gmt_to_ist_tz(row.client_deadline) if row.client_deadline else row.client_deadline,
                            'currency_id': row.currency_id.name,
                            'client_type': row.partner_id.client_type_id.name,
                            'new_client': 'New' if row.partner_id.new_client == True else 'Existing',
                            'client_instructions': row.note
                        }
                        if row.state == 'cancel':
                            if row.reject_reason == 'Repeat Entry':
                                assignment_current_status = 'Repeat'
                            else:
                                assignment_current_status = 'Reject'
                            bi_report_inq_vals.update({
                                'reject_reason': row.reject_reason,
                                'reject_date': self.convert_gmt_to_ist_tz(row.reject_date) if row.reject_date else row.reject_date,
                                'assignment_current_status': assignment_current_status,
                                'is_parent_or_child': 'Child'
                            })
                        if row.state != 'cancel':
                            bi_report_inq_vals.update({
                                'assignment_current_status': 'Inquiry',
                                'is_parent_or_child': 'Parent'
                            })
                        if row.is_rr_inquiry:
                            for lang in row.target_lang_ids:
                                bi_report_inq_vals.update({
                                    'target_lang_ids': [(4, lang.id)],
                                    'is_rr_inquiry': 'Yes',
                                    'service': row.source_lang_id.name + ' - ' + lang.name if lang.id and row.source_lang_id else '',
                                    'is_parent_or_child': 'RR',
                                })
                                self.env['bi.daily.report'].sudo().create(bi_report_inq_vals)
                        else:
                            self.env['bi.daily.report'].sudo().create(bi_report_inq_vals)
                    if row.type == 'quotation' and row.has_revision == False:
                        bi_reports = self.env['bi.daily.report'].search([('inquiry_id', '=', row.inquiry_id.id)])
                        if bi_reports:
                            for bi_report in bi_reports:
                                diff = False
                                response_time = ''
                                if row.inquiry_id.create_date and row.quote_sent_datetime:
                                    diff = row.quote_sent_datetime - row.inquiry_id.create_date
                                if diff:
                                    response_time = str(diff).split(".", maxsplit=1)[0]
                                if row.is_rr_inquiry:
                                    memsource_line_ids = row.order_line.mapped('memsource_line').filtered(
                                        lambda l: l.sale_line_id.target_lang_id.id == bi_report.target_lang_ids.id)
                                    char_count = row.order_line.filtered(lambda l: l.target_lang_id.id == bi_report.target_lang_ids.id).character_count
                                else:
                                    memsource_line_ids = row.order_line.mapped('memsource_line')
                                    char_count = row.char_count
                                non_editable_count, wc_0_49_count, wc_50_74_count, wc_75_84_count, wc_85_94_count = 0.0, 0.0, 0.0, 0.0, 0.0
                                wc_95_99_count, wc_100_count, wc_101_count, repetitions_count, machine_translation_count = 0.0, 0.0, 0.0, 0.0, 0.0
                                if memsource_line_ids:
                                    for mem_line in memsource_line_ids:
                                        if mem_line.percent_type.name == 'Non-editable Count':
                                            non_editable_count += mem_line.weighted_count
                                        if mem_line.percent_type.name == '0%–49%':
                                            wc_0_49_count += mem_line.weighted_count
                                        if mem_line.percent_type.name == '50%–74%':
                                            wc_50_74_count += mem_line.weighted_count
                                        if mem_line.percent_type.name == '75%–84%':
                                            wc_75_84_count += mem_line.weighted_count
                                        if mem_line.percent_type.name == '85%–94%':
                                            wc_85_94_count += mem_line.weighted_count
                                        if mem_line.percent_type.name == '95%–99%':
                                            wc_95_99_count += mem_line.weighted_count
                                        if mem_line.percent_type.name == '100%':
                                            wc_100_count += mem_line.weighted_count
                                        if mem_line.percent_type.name == '101%':
                                            wc_101_count += mem_line.weighted_count
                                        if mem_line.percent_type.name == 'Repetitions':
                                            repetitions_count += mem_line.weighted_count
                                        if mem_line.percent_type.name == 'Machine Translation':
                                            machine_translation_count += mem_line.weighted_count
                                client_instructions = ''
                                if row.order_line:
                                    client_instructions_line = row.order_line[0].mapped('sale_instruction_line').filtered(lambda l: l.is_original_ins == True)
                                if client_instructions_line:
                                    client_instructions = ['- ' + line.name for line in client_instructions_line]
                                    client_instructions = ', '.join(client_instructions)
                                bi_report_quote_vals = {
                                    'quote_id': row.id,
                                    'char_count': char_count,
                                    'actual_client_deadline': self.convert_gmt_to_ist_tz(row.deadline) if row.deadline else row.deadline,
                                    'area_type': row.area_type,
                                    'subject_industrial_area_level1_id': row.subject_industrial_area_level1_id.name,
                                    'subject_industrial_area_level2_id': row.subject_industrial_area_level2_id.name,
                                    'subject_industrial_area_level3_id': row.subject_industrial_area_level3_id.name,
                                    'client_deadline': self.convert_gmt_to_ist_tz(row.client_deadline) if row.client_deadline else row.client_deadline,
                                    'mark_as_special': row.mark_as_special,
                                    'quotataion_sent_by': row.user_id.name,
                                    'quote_state': row.state,
                                    'response_time': response_time,
                                    'non_editable_count': non_editable_count,
                                    'wc_0_49_percent': wc_0_49_count,
                                    'wc_50_74_percent': wc_50_74_count,
                                    'wc_75_84_percent': wc_75_84_count,
                                    'wc_85_94_percent': wc_85_94_count,
                                    'wc_95_99_percent': wc_95_99_count,
                                    'wc_100_percent': wc_100_count,
                                    'wc_101_percent': wc_101_count,
                                    'repetitions': repetitions_count,
                                    'machine_translation': machine_translation_count,
                                    'po_number': row.po_number,
                                    'client_instructions': client_instructions,
                                }
                                if row.state == 'cancel':
                                    if row.reject_reason == 'Repeat Entry':
                                        assignment_current_status = 'Repeat'
                                    else:
                                        assignment_current_status = 'Reject'
                                    bi_report_quote_vals.update({
                                        'reject_reason': row.reject_reason,
                                        'reject_date': self.convert_gmt_to_ist_tz(row.reject_date) if row.reject_date else row.reject_date,
                                        'assignment_current_status': assignment_current_status,
                                        'is_parent_or_child': 'Child'
                                    })
                                if row.state != 'cancel':
                                    bi_report_quote_vals.update({
                                        'assignment_current_status': 'Inquiry',
                                        'is_parent_or_child': 'Parent'
                                    })
                                bi_report.sudo().write(bi_report_quote_vals)
                        if row.is_rr_inquiry == True:
                            assignments = self.env['assignment'].search([('quotation_id', '=', row.id)])
                            if assignments:
                                for asn in assignments:
                                    bi_report_asn = self.env['bi.daily.report'].search([('quote_id', '=', asn.quotation_id.id),
                                                                                       ('target_lang_ids', 'in',
                                                                                        [asn.target_lang_id.id])])
                                    if asn and bi_report_asn:
                                        is_deadline_met = ''
                                        if (asn.delivered_on and asn.deadline) and (asn.delivered_on <= asn.deadline):
                                            is_deadline_met = 'Yes'
                                        elif (asn.delivered_on and asn.deadline) and (asn.delivered_on >= asn.deadline):
                                            is_deadline_met = 'No'
                                        internal_client_deadline = asn.deadline - timedelta(hours=1)
                                        bi_report_asn_vals = {
                                            'asn_id': asn.id,
                                            'asn_number': asn.name,
                                            'service_level_id': asn.service_level_id.name,
                                            'priority': asn.priority,
                                            'unit_id': row.unit_id.name,
                                            'char_count': asn.character_count,
                                            'asn_state': asn.state,
                                            'gross_fee': asn.gross_fee,
                                            'premium_percentage': row.add_premium_rate if row.add_premium_type == 'percent' else False,
                                            'premium_amount': asn.premium,
                                            'discount_percentage': row.ks_global_discount_rate if row.ks_global_discount_type == 'percent' else False,
                                            'discount_amount': asn.discount,
                                            'total_tax': asn.tax,
                                            'total_fees': asn.total_fees,
                                            'quote_confirmation_date': self.convert_gmt_to_ist_tz(row.quote_confirmation_datetime) if row.quote_confirmation_datetime else row.quote_confirmation_datetime,
                                            'asn_confirmed_by': asn.user_id.name,
                                            'is_deadline_met': is_deadline_met,
                                            'asn_delivery_date': self.convert_gmt_to_ist_tz(asn.delivered_on) if asn.delivered_on else asn.delivered_on,
                                            'is_parent_or_child': 'RR',
                                            'actual_client_deadline': self.convert_gmt_to_ist_tz(asn.deadline) if asn.deadline else asn.deadline,
                                            'internal_client_deadline': self.convert_gmt_to_ist_tz(internal_client_deadline),
                                        }
                                        if asn.state == 'cancel':
                                            if row.reject_reason == 'Repeat Entry':
                                                assignment_current_status = 'Repeat'
                                            else:
                                                assignment_current_status = 'Reject'
                                            bi_report_asn_vals.update({
                                                'reject_reason': asn.note,
                                                'reject_date': self.convert_gmt_to_ist_tz(asn.reject_date) if asn.reject_date else asn.reject_date,
                                                'assignment_current_status': assignment_current_status
                                            })
                                        if asn.state != 'cancel':
                                            bi_report_asn_vals.update({
                                                'assignment_current_status': 'Assignment'
                                            })
                                        invoice = self.env['account.invoice'].search([('assignment_id', '=', asn.id)])
                                        if invoice:
                                            bi_report_asn_vals.update({
                                                'inv_type': invoice[0].inv_type,
                                                'invoice_create_date': self.convert_gmt_to_ist_tz(invoice[0].create_date) if invoice[0].create_date else invoice[0].create_date,
                                                'po_number': invoice[0].po_number
                                            })
                                        bi_report_asn.sudo().write(bi_report_asn_vals)
                    if row.type == 'asn':
                        bi_report1 = self.env['bi.daily.report'].search([('quote_id', '=', row.quotation_ref_id.id)])
                        if bi_report1:
                            is_deadline_met = ''
                            if (row.parent_asn_complete_date and row.deadline) and (row.parent_asn_complete_date <= row.deadline):
                                is_deadline_met = 'Yes'
                            elif (row.parent_asn_complete_date and row.deadline) and (row.parent_asn_complete_date >= row.deadline):
                                is_deadline_met = 'No'
                            trans_unit_rate = sum(row.quotation_ref_id.order_line.mapped('service_level_line').filtered(
                                    lambda l: l.service_level_id.id == row.service_level_id.id).mapped('unit_rate'))
                            bi_report_asn_vals = {
                                'parent_asn_id': row.id,
                                'asn_number': row.name,
                                'service_level_id': row.service_level_id.name,
                                'priority': row.priority,
                                'unit_id': row.unit_id.name,
                                'char_count': row.char_count,
                                'asn_state': row.state,
                                'gross_fee': row.amount_undiscounted,
                                'premium_percentage': row.add_premium_rate if row.add_premium_type == 'percent' else False,
                                'premium_amount': row.premium_amount,
                                'discount_percentage': row.ks_global_discount_rate if row.ks_global_discount_type == 'percent' else False,
                                'discount_amount': row.ks_amount_discount,
                                'total_tax': row.amount_tax,
                                'total_fees': row.amount_total,
                                'quote_confirmation_date': self.convert_gmt_to_ist_tz(row.quotation_ref_id.quote_confirmation_datetime) if row.quotation_ref_id.quote_confirmation_datetime else row.quotation_ref_id.quote_confirmation_datetime,
                                'asn_confirmed_by': row.user_id.name,
                                'is_deadline_met': is_deadline_met,
                                'asn_delivery_date': self.convert_gmt_to_ist_tz(row.parent_asn_complete_date) if row.parent_asn_complete_date else row.parent_asn_complete_date,
                                'project_management_cost': row.order_line.filtered(lambda l: l.name == 'Project Management Cost' and l.order_id.id == row.id).price_subtotal,
                                'final_rate': trans_unit_rate
                            }
                            if row.state == 'cancel':
                                bi_report_asn_vals.update({
                                    'reject_reason': row.reject_reason,
                                    'reject_date': self.convert_gmt_to_ist_tz(row.reject_date) if row.reject_date else row.reject_date,
                                    'assignment_current_status': 'Reject'
                                })
                            if row.state != 'cancel':
                                bi_report_asn_vals.update({
                                    'assignment_current_status': 'Assignment'
                                })
                            bi_report_asn_vals.update({'is_parent_or_child': 'Parent'})
                            invoice = self.env['account.invoice'].search([('sale_order_id', '=', row.id)])
                            if invoice:
                                bi_report_asn_vals.update({
                                    'inv_type': invoice[0].inv_type,
                                    'invoice_create_date': self.convert_gmt_to_ist_tz(invoice[0].create_date) if invoice[0].create_date else invoice[0].create_date,
                                    'po_number': invoice[0].po_number
                                })
                            addons_line = row.order_line.filtered(lambda l: l.is_addons_service == True and l.order_id.id == row.id)
                            if addons_line:
                                for line in addons_line:
                                    addons_technical_field = line.product_id.addons_technical_field
                                    addons_price = line.price_subtotal
                                    if addons_technical_field and addons_price:
                                        bi_report_asn_vals.update({addons_technical_field: addons_price})
                            bi_report1.sudo().write(bi_report_asn_vals)

                            child_asn = self.env['assignment'].search([('parent_asn_id', '=', row.id)])
                            for rec in child_asn:
                                internal_client_deadline = rec.deadline - timedelta(hours=1)
                                trans_id = rec.quotation_id.order_line.mapped('service_level_line').filtered(
                                    lambda l: l.service_level_id.id == rec.service_level_id.id and l.sale_service_line_id.target_lang_id.id == rec.target_lang_id.id)
                                is_deadline_met = ''
                                if (rec.delivered_on and rec.deadline) and (rec.delivered_on <= rec.deadline):
                                    is_deadline_met = 'Yes'
                                elif (rec.delivered_on and rec.deadline) and (rec.delivered_on >= rec.deadline):
                                    is_deadline_met = 'No'
                                bi_report_vals = {
                                    'inquiry_id': bi_report1.inquiry_id.id,
                                    'quote_id': bi_report1.quote_id.id,
                                    'parent_asn_id': bi_report1.parent_asn_id.id,
                                    'asn_id': rec.id,
                                    'inquiry_date': bi_report1.inquiry_date,
                                    'inquiry_state': bi_report1.inquiry_state,
                                    'mem_id': bi_report1.mem_id,
                                    'client_name': bi_report1.client_name,
                                    'target_lang_ids': [(4, rec.target_lang_id.id)],
                                    'service': rec.source_lang_id.name + ' - ' + rec.target_lang_id.name,
                                    'client_deadline': bi_report1.client_deadline,
                                    'currency_id': bi_report1.currency_id,
                                    'client_type': bi_report1.client_type,
                                    'new_client': bi_report1.new_client,
                                    'client_instructions': bi_report1.client_instructions,
                                    'reject_reason': bi_report1.reject_reason,
                                    'reject_date': bi_report1.reject_date,
                                    'assignment_current_status': bi_report1.assignment_current_status,
                                    'actual_client_deadline': self.convert_gmt_to_ist_tz(rec.deadline),
                                    'internal_client_deadline': self.convert_gmt_to_ist_tz(internal_client_deadline),
                                    'area_type': bi_report1.area_type,
                                    'subject_industrial_area_level1_id': bi_report1.subject_industrial_area_level1_id,
                                    'subject_industrial_area_level2_id': bi_report1.subject_industrial_area_level2_id,
                                    'subject_industrial_area_level3_id': bi_report1.subject_industrial_area_level3_id,
                                    'mark_as_special': bi_report1.mark_as_special,
                                    'quotataion_sent_by': bi_report1.quotataion_sent_by,
                                    'quote_state': bi_report1.quote_state,
                                    'response_time': bi_report1.response_time,
                                    'po_number': bi_report1.po_number,
                                    'project_management_cost': rec.project_management_cost,
                                    'final_rate': trans_id.unit_rate,
                                    'organisation_name': bi_report1.organisation_name,
                                    'is_parent_or_child': 'Child',
                                    'asn_delivery_date': self.convert_gmt_to_ist_tz(rec.delivered_on) if rec.delivered_on else rec.delivered_on,
                                    'is_deadline_met': is_deadline_met,
                                }

                                memsource_line_ids = rec.quotation_id.order_line.mapped('memsource_line').filtered(lambda l: l.sale_line_id.target_lang_id.id == rec.target_lang_id.id)
                                non_editable_count, wc_0_49_count, wc_50_74_count, wc_75_84_count, wc_85_94_count = 0.0, 0.0, 0.0, 0.0, 0.0
                                wc_95_99_count, wc_100_count, wc_101_count, repetitions_count, machine_translation_count = 0.0, 0.0, 0.0, 0.0, 0.0
                                for mem_line in memsource_line_ids:
                                    if mem_line.percent_type.name == 'Non-editable Count':
                                        non_editable_count += mem_line.weighted_count
                                    if mem_line.percent_type.name == '0%–49%':
                                        wc_0_49_count += mem_line.weighted_count
                                    if mem_line.percent_type.name == '50%–74%':
                                        wc_50_74_count += mem_line.weighted_count
                                    if mem_line.percent_type.name == '75%–84%':
                                        wc_75_84_count += mem_line.weighted_count
                                    if mem_line.percent_type.name == '85%–94%':
                                        wc_85_94_count += mem_line.weighted_count
                                    if mem_line.percent_type.name == '95%–99%':
                                        wc_95_99_count += mem_line.weighted_count
                                    if mem_line.percent_type.name == '100%':
                                        wc_100_count += mem_line.weighted_count
                                    if mem_line.percent_type.name == '101%':
                                        wc_101_count += mem_line.weighted_count
                                    if mem_line.percent_type.name == 'Repetitions':
                                        repetitions_count += mem_line.weighted_count
                                    if mem_line.percent_type.name == 'Machine Translation':
                                        machine_translation_count += mem_line.weighted_count

                                bi_report_vals.update({'non_editable_count': non_editable_count,
                                                       'wc_0_49_percent': wc_0_49_count,
                                                       'wc_50_74_percent': wc_50_74_count,
                                                       'wc_75_84_percent': wc_75_84_count,
                                                       'wc_85_94_percent': wc_85_94_count,
                                                       'wc_95_99_percent': wc_95_99_count,
                                                       'wc_100_percent': wc_100_count,
                                                       'wc_101_percent': wc_101_count,
                                                       'repetitions': repetitions_count,
                                                       'machine_translation': machine_translation_count,
                                                       'asn_number': rec.name,
                                                       'service_level_id': rec.service_level_id.name,
                                                       'priority': rec.priority,
                                                       'unit_id': rec.parent_asn_id.unit_id.name,
                                                       'char_count': rec.character_count,
                                                       'asn_state': rec.state,
                                                       'gross_fee': rec.gross_fee,
                                                       'premium_percentage': rec.parent_asn_id.add_premium_rate if rec.parent_asn_id.add_premium_type == 'percent' else False,
                                                       'premium_amount': rec.premium,
                                                       'discount_percentage': rec.parent_asn_id.ks_global_discount_rate if rec.parent_asn_id.ks_global_discount_type == 'percent' else False,
                                                       'discount_amount': rec.discount,
                                                       'total_tax': rec.tax,
                                                       'total_fees': rec.total_fees,
                                                       'quote_confirmation_date': bi_report1.quote_confirmation_date,
                                                       'asn_confirmed_by': bi_report1.asn_confirmed_by,
                                                       'inv_type': bi_report1.inv_type,
                                                       'invoice_create_date': bi_report1.invoice_create_date,
                                                       'po_number': bi_report1.po_number
                                                       })
                                addons_line = rec.asn_addons_fee_line.filtered(lambda l: l.asn_id.id == rec.id)
                                if addons_line:
                                    for line in addons_line:
                                        addons_technical_field = line.product_id.addons_technical_field
                                        addons_price = line.price_unit
                                        if addons_technical_field and addons_price:
                                            bi_report_vals.update({addons_technical_field: addons_price})
                                self.env['bi.daily.report'].sudo().create(bi_report_vals)