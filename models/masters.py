# -*- coding: utf-8 -*-

import collections
import re
import base64
from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.addons.amazon_s3_storage.models import s3_tool
import logging
_logger = logging.getLogger("Master Tables: ")


class ServiceLevel(models.Model):
    _name = 'service.level'
    _description = 'Translation Level'

    name = fields.Char(string="Translation Level")
    pm_name = fields.Char(string="PM Name")
    note = fields.Text(string="Notes")
    product_id = fields.Many2one('product.product', string="Product")
    #NOT IN USE
    language_ids = fields.Many2many(
        'res.lang', 'servive_level_ref', 'service_id', 'lang_id',
        string="Languages")

    @api.constrains('name')
    def _check_translation(self):
        for record in self:
            query = """SELECT id 
                       FROM service_level
                       WHERE name ilike '%s' AND id != %s 
                       LIMIT 1
                    """ % (self.name, self.id)
            self.env.cr.execute(query)
            duplicate = self.env.cr.fetchone()
            if duplicate:
                raise ValidationError("Translation level already exists!")

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100,
                     name_get_uid=None):
        args = args or []
        res = super(ServiceLevel, self)._name_search(
            name, args, operator=operator, limit=limit,
            name_get_uid=name_get_uid)
        if self._context.get('product_id', False):
            query = """select translation_id from product_trans_ref
                       where product_id = '%s'
                    """ % self._context.get('product_id', False)
            self.env.cr.execute(query)
            service_ids = [trans_id[0] for trans_id in self.env.cr.fetchall()]
            domain = [('id', 'in', service_ids)]
            res = self.search(domain + args, limit=limit)
            return res.name_get()
        return res

    @api.model
    def create(self, vals):
        if vals.get('name'):
            product = self.env['product.product'].create({
                'name': vals['name'],
                'taxes_id': [(6, 0, [])],
                'type': 'service',
                'supplier_taxes_id': [(6, 0, [])]})
            vals['product_id'] = product.id
        return super(ServiceLevel, self).create(vals)

    @api.multi
    def write(self, vals):
        if vals.get('name') and self.product_id:
            self.product_id.update({'name': vals.get('name'),
                                    'taxes_id': [(6, 0, [])],
                                    'type': 'service',
                                    'supplier_taxes_id': [(6, 0, [])]})
        return super(ServiceLevel, self).write(vals)


class DocTypeMaster(models.Model):
    _name = 'doc.type.master'
    _description = 'Document Type Master'

    name = fields.Char(string="Name", required=True)
    # doc_type_master_line = fields.One2many(
    #     "doc.type.master.line", "doc_type_master_id", "Extension File Line")
    doc_type_master_line = fields.One2many("ir.attachment", "doc_type_master_id", "Extension File Line")
    no_file_extension = fields.Boolean("No File Extension?")
    no_file_extension_img = fields.Binary("No File Extension Image")
    filename = fields.Char("Filename")

    @api.constrains('name', 'doc_type_master_line')
    def _check_translation(self):
        for record in self:
            # To check document type exist or not
            query = """SELECT id 
                       FROM doc_type_master
                       WHERE name ilike '%s' AND id != %s 
                       LIMIT 1
                    """ % (record.name, record.id)
            self.env.cr.execute(query)
            duplicate = self.env.cr.fetchone()
            if duplicate:
                raise ValidationError("Document Type already exists!")

            # To restrict creation of duplicate no file extension records
            if record.no_file_extension:
                query = """SELECT id
                           FROM doc_type_master
                           WHERE no_file_extension = true"""
                self.env.cr.execute(query)
                duplicate_no_file_extension = self.env.cr.fetchall()
                if len(duplicate_no_file_extension) > 1:
                    raise ValidationError("No file extension record already exists!")

            if record.doc_type_master_line:
                # To check file extension name is blank
                blank_file_extension_name = record.doc_type_master_line.filtered(lambda l: not l.file_extension_name)
                if blank_file_extension_name:
                    raise ValidationError("Please add file extension name.")

                file_extension_name_list = record.doc_type_master_line.mapped('file_extension_name')

                # To check pattern of the file extension name field
                result = [f_name for f_name in file_extension_name_list if re.findall("[^a-z]+", f_name)]
                if result:
                    raise ValidationError("Please add a valid file extension name for %s." % ', '.join(result))

                # To check file extension already exists or not
                query = """SELECT file_extension_name
                           FROM ir_attachment
                           WHERE file_extension_name IN %s 
                        """
                self.env.cr.execute(query, (tuple(file_extension_name_list),))
                duplicate_file_names = self.env.cr.fetchall()
                if duplicate_file_names:
                    duplicate_file_name_list = [x[0] for x in duplicate_file_names]
                    duplicate_file_name_str = ', '.join(
                        [item for item, count in collections.Counter(duplicate_file_name_list).items() if count > 1])
                    if duplicate_file_name_str:
                        raise ValidationError("%s file extension already exists!" % duplicate_file_name_str)

    @api.multi
    def upload_no_image(self):
        """ To upload no file extension image on s3 """
        param_id = self.env['ir.config_parameter'].sudo().get_param('ir_attachment.location', 'file')
        folder_path = '/'.join([self._cr.dbname, 'file_extension'])
        try:
            # To upload files on S3
            s3_url, s3_key = s3_tool.put(param_id, folder_path, base64.b64decode(self.no_file_extension_img),
                                         self.filename)
            if s3_url:
                # Attachment record with s3 url
                vals = {
                     'name': self.filename,
                     'datas_fname': self.filename,
                     'res_model': self._name,
                     'res_id': self.id,
                     'type': 'url',
                     'datas': self.no_file_extension_img,
                     'url': s3_url,
                     's3_key': s3_key,
                     's3_file_record': True,
                     'f_size': len(self.no_file_extension_img),
                     'file_extension_name': 'no',
                }
                self.env['ir.attachment'].sudo().create(vals)
        except Exception as e:
            logging.error('-------S3: Upload ---------File Extension------------------- : %s' % e)

    @api.model
    def create(self, vals):
        """
            Store image of no file extension on s3
            :param vals: fields with their values
            :return: return super
        """
        res = super(DocTypeMaster, self).create(vals)
        if vals.get('no_file_extension', False) and 'no_file_extension_img' in vals:
            if res.doc_type_master_line:
                updated_record = [attach_id.delete_file_from_s3() for attach_id in res.doc_type_master_line]
            res.upload_no_image()
        return res

    @api.multi
    def write(self, vals):
        """
            Store image of no file extension on s3
            :param vals: updated fields with their values
            :return: return super
        """
        res = super(DocTypeMaster, self).write(vals)
        if vals.get('no_file_extension') and 'no_file_extension_img' in vals:
            if self.doc_type_master_line:
                updated_record = [attach_id.delete_file_from_s3() for attach_id in self.doc_type_master_line]
            self.upload_no_image()
        return res


class DocTypeMasterLine(models.Model):
    _name = 'doc.type.master.line'
    _description = 'Document Type Master Line'

    name = fields.Char(string="File Extension Name", required=True)
    doc_type_master_id = fields.Many2one(
        'doc.type.master', string="Doc Type Master")


class FeeMaster(models.Model):
    _name = 'fee.master'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _rec_name = 'product_id'
    _description = 'Fees Master'
    _order = 'product_id asc, membership_id asc'

    organization_id = fields.Many2one(
        'res.partner', string="Organization(MEMID)", track_visibility='onchange')
    end_client_id = fields.Many2one('res.partner', string="End Client",
        track_visibility='onchange')
    currency_id = fields.Many2one('res.currency', 'Currency',
                                  default=lambda self:
                                  self.env.user.company_id.currency_id,
                                  track_visibility='onchange')
    translation_level_id = fields.Many2one(
        'service.level', string="Translation Level",track_visibility='onchange')
    priority = fields.Selection(
        [('standard', 'Standard'), ('express', 'Express'), ('super_express', 'Super Express')], string="Priority",
        track_visibility='onchange')
    product_id = fields.Many2one('product.product', string="Product",
        track_visibility='onchange')
    source_lang_id = fields.Many2one('res.lang', string="Source Languages",
        track_visibility='onchange')
    target_lang_id = fields.Many2one('res.lang', string="Target Languages",
        track_visibility='onchange')
    price = fields.Monetary('Price Per Unit', track_visibility='onchange')
    unit_count = fields.Integer("Unit Count", default="1",
                                track_visibility='onchange')
    unit_id = fields.Many2one('service.unit', string="Unit",
        track_visibility='onchange')
    membership_id = fields.Many2one("membership.master", string="MEMID",
        track_visibility='onchange')

    @api.constrains('membership_id', 'end_client_id', 'currency_id',
        'translation_level_id', 'priority', 'product_id', 'source_lang_id',
        'target_lang_id', 'unit_id')
    def _check_translation(self):
        for record in self:            
            query = """SELECT id 
                       FROM fee_master
                       WHERE currency_id = %s AND translation_level_id = %s 
                       AND priority = '%s' AND product_id = %s 
                       AND source_lang_id = %s AND target_lang_id = %s 
                       AND id != %s
                    """ % (record.currency_id.id,record.translation_level_id.id,
                        record.priority, record.product_id.id,
                        record.source_lang_id.id, record.target_lang_id.id,
                        record.id)
            if record.membership_id:
                query += " AND membership_id = %s" % record.membership_id.id
            else:
                query += " AND membership_id is Null"
            if record.end_client_id:
                query += " AND end_client_id = %s LIMIT 1" % \
                         record.end_client_id.id
            else:
                query += " AND end_client_id is Null LIMIT 1"
            _logger.info("quesry string:::::::::::::%s" % query)
            self.env.cr.execute(query)
            duplicate = self.env.cr.fetchone()
            _logger.info("duplicate:::::::::::::%s" % duplicate)
            if duplicate:
                raise ValidationError("Fee already exists for these combination!")

    @api.onchange('source_lang_id')
    def onchange_source_lang_id(self):
        if self.source_lang_id:
            self.unit_id = self.source_lang_id.unit_id.id
        else:
            self.unit_id = False

    def open_form(self):
        ctx = self._context.copy()
        view_id = self.env.ref('ulatus_cs.view_fee_master_form_view').id
        return {
            'name': ('Checklist'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'fee.master',
            'res_id': self.id,
            'view_id': view_id,
            'target': 'current',
            'context': ctx
        }


class AddonsFeeMaster(models.Model):
    _name = 'addons.fee.master'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _rec_name = 'addons_id'
    _description = 'Add-ons Fees Master'
    _order = 'product_id asc'

    addons_id = fields.Many2one("product.product", string="Add-On Name",
        track_visibility='onchange')
    organization_id = fields.Many2one(
        'res.partner', string="Organization(MEMID)", track_visibility='onchange')
    end_client_id = fields.Many2one('res.partner', string="End Client",
        track_visibility='onchange')
    currency_id = fields.Many2one('res.currency', 'Currency',
                                  default=lambda self:
                                  self.env.user.company_id.currency_id,
                                  track_visibility='onchange')
    priority = fields.Selection(
        [('standard', 'Standard'), ('express', 'Express'), ('super_express', 'Super Express')], string="Priority",
        track_visibility='onchange')
    product_id = fields.Many2one('product.product', string="Product",
        track_visibility='onchange')
    source_lang_id = fields.Many2one('res.lang', string="Source Languages",
        track_visibility='onchange')
    target_lang_id = fields.Many2one('res.lang', string="Target Languages",
        track_visibility='onchange')
    unit_id = fields.Many2one('service.unit', string="Unit",
        track_visibility='onchange')
    price = fields.Monetary('Price Per Unit', track_visibility='onchange')
    membership_id = fields.Many2one("membership.master", string="MEMID",
        track_visibility='onchange')

    @api.constrains('addons_id', 'membership_id','end_client_id','currency_id',
                    'priority', 'product_id', 'source_lang_id', 'target_lang_id'
                    'unit_id')
    def _check_translation(self):
        for record in self:
            query = """SELECT id 
                       FROM addons_fee_master
                       WHERE addons_id = %s AND
                        currency_id = %s AND priority = '%s'
                        AND product_id = %s AND id != %s
                        AND source_lang_id = %s AND target_lang_id = %s
                        AND unit_id =%s
                    """ % (record.addons_id.id,record.currency_id.id,
                           record.priority,
                           record.product_id.id,record.id, record.source_lang_id.id, 
                           record.target_lang_id.id, record.unit_id.id)
            if record.membership_id:
                query += " AND membership_id = %s" % record.membership_id.id
            else:
                query += " AND membership_id is Null"
            if record.end_client_id:
                query += " AND end_client_id = %s LIMIT 1" % \
                         record.end_client_id.id
            else:
                query += " AND end_client_id is Null LIMIT 1"
            _logger.info("quesry string:::::::::::::%s" % query)
            self.env.cr.execute(query)
            duplicate = self.env.cr.fetchone()
            _logger.info("duplicate:::::::::::::%s" % duplicate)
            if duplicate:
                raise ValidationError(
                    "Add-ons Fee already exists for these combination!")

    def open_form(self):
        ctx = self._context.copy()
        view_id = self.env.ref('ulatus_cs.view_addons_fee_master_form_view').id
        return {
            'name': ('Checklist'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'addons.fee.master',
            'res_id': self.id,
            'view_id': view_id,
            'target': 'current',
            'context': ctx
        }

    @api.onchange('addons_id')
    def onchange_addons_id(self):
        if self.addons_id:
            self.unit_id = self.addons_id.unit_id.id
        else:
            self.unit_id = False


class ServiceUnit(models.Model):
    _name = 'service.unit'
    _description = 'Service Unit'

    name = fields.Char(string="Document Unit ", required=True)
    service_unit_line = fields.One2many(
        "service.unit.line", "service_unit_id", "FL Fee Structure Unit")

    @api.constrains('name')
    def _check_translation(self):
        for record in self:
            query = """SELECT id 
                       FROM service_unit
                       WHERE name ilike '%s' AND id != %s 
                       LIMIT 1
                    """ % (record.name, record.id)
            self.env.cr.execute(query)
            duplicate = self.env.cr.fetchone()
            if duplicate:
                raise ValidationError("Document Unit already exists!")


class ServiceUnitLine(models.Model):
    _name = 'service.unit.line'
    _description = 'Service Unit Line'

    name = fields.Char(string="Name", required=True)
    count = fields.Integer('Count', default=1)
    service_unit_id = fields.Many2one('service.unit', string="Service Unit")


class CheckList(models.Model):
    _name = 'checklist'
    _description = 'CheckList Master'

    name = fields.Char(string="Name", required=True)
    type = fields.Selection([('Quotation', 'Quotation'),
                             ('Delivery', 'Delivery')], string="Type",
                             required=True)


class FaqMaster(models.Model):
    _name = "faq.master"
    _description = 'FAQ Master'

    quetion = fields.Text("Question")
    answer = fields.Text("Answer")

    def _append_question_mark_last(self, field_val):
        if field_val and not field_val[-1] == '?':
            field_val = field_val + '?'
        return field_val

    def _append_dot_last(self, field_val):
        if field_val and not field_val[-1] == '.':
            field_val = field_val + '.'
        return field_val

    @api.model
    def create(self, vals):
        if vals.get('quetion'):
            vals['quetion'] = self._append_question_mark_last(vals['quetion'])
        if vals.get('answer'):
            vals['answer'] = self._append_dot_last(vals['answer'])
        return super(FaqMaster, self).create(vals)

    @api.multi
    def write(self, vals):
        if vals.get('quetion'):
            vals['quetion'] = self._append_question_mark_last(vals['quetion'])
        if vals.get('answer'):
            vals['answer'] = self._append_dot_last(vals['answer'])
        return super(FaqMaster, self).write(vals)


class AccountTaxMaster(models.Model):
    _inherit = 'account.tax'

    currency_id = fields.Many2one('res.currency', string="Currency")
    amount_type = fields.Selection(default='percent', string="Tax Computation",
                                   required=True, oldname='type',
                                   selection=[('group', 'Group of Taxes'),
                                              ('fixed', 'Fixed'),
                                              ('percent','Percentage of Price'),
                                             ])

    
    # @api.model
    # def _name_search(self, name, args=None, operator='ilike', limit=100,
    #                  name_get_uid=None):
    #     args = args or []
    #     res = super(AccountTaxMaster, self)._name_search(
    #         name, args, operator=operator, limit=limit,
    #         name_get_uid=name_get_uid)
    #     if self._context.get('currency_id', False):
    #         query = """select id from account_tax
    #                    where currency_id = '%s'
    #                 """ % self._context.get('currency_id', False)
    #         self.env.cr.execute(query)
    #         tax_ids = [trans_id[0] for trans_id in self.env.cr.fetchall()]
    #         domain = [('id', 'in', tax_ids)]
    #         res = self.search(domain + args, limit=limit)
    #         return res.name_get()
    #     return res

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        context = self._context or {}
        if context.get('currency_id'):
            args += [('currency_id', '=', context.get('currency_id'))]

        return super(AccountTaxMaster, self)._search(args, offset, limit, order, count=count, access_rights_uid=access_rights_uid)


class RejectionReason(models.Model):
    _name = 'rejection.reason'
    _description = 'Rejection Reason'
    _rec_name = 'reason'

    reason = fields.Char(string="Reason", required=True)
    type = fields.Selection([('inquiry', 'Inquiry'),
                              ('asn', 'Assignment')], 'Type', default='inquiry', required=True)


# Subject and Industrial Area Master

# Level 1
class SubjectIndustrialAreaLevel1(models.Model):
    _name = 'subject.industrial.area.level1'
    _description = 'Subject and Industrial Area Line Level1'
    _order = 'name asc'

    name = fields.Char(string="Level 1", required=True)
    description = fields.Text(string="Description")
    area_type = fields.Selection([('subject_area', 'Subject Area'),
                                  ('industrial_area', 'Industrial Area')], 'Area Type', required=True)

    @api.constrains('name')
    def _check_duplicate(self):
        for record in self:
            query = """SELECT id 
                           FROM subject_industrial_area_level1
                           WHERE name ilike '%s' AND id != %s AND area_type = '%s'
                           LIMIT 1
                        """ % (record.name, record.id, record.area_type)
            record.env.cr.execute(query)
            duplicate = record.env.cr.fetchone()
            if duplicate:
                raise ValidationError("Level 1 name already exists!")


# Level 2
class SubjectIndustrialAreaLevel2(models.Model):
    _name = 'subject.industrial.area.level2'
    _description = 'Subject and Industrial Area Line Level2'
    _rec_name = 'level1_id'
    _order = 'level1_id asc'

    area_type = fields.Selection([('subject_area', 'Subject Area'),
                                  ('industrial_area', 'Industrial Area')], 'Area Type', required=True)
    level1_id = fields.Many2one('subject.industrial.area.level1', string="Level 1", required=True)
    level2_line = fields.One2many("subject.industrial.area.level2.line", "level2_id",
                                               "Level 2 Line")

    @api.onchange('area_type')
    def get_level1_data(self):
        if self.area_type:
            self.level1_id = [(6, 0, [])]
            level1_ids = self.env["subject.industrial.area.level1"].search([("area_type", "=", self.area_type)])
            if level1_ids:
                return {'domain':{'level1_id':[('id', 'in', [rec.id for rec in level1_ids])]}}
            else:
                return {'domain': {'level1_id': [('id', 'in', [])]}}

    @api.constrains('level1_id')
    def _check_duplicate(self):
        for record in self:
            query = """SELECT id 
                           FROM subject_industrial_area_level2
                           WHERE id != %s AND level1_id = %s AND area_type = '%s'
                           LIMIT 1
                        """ % (record.id, record.level1_id.id, record.area_type)
            record.env.cr.execute(query)
            duplicate = record.env.cr.fetchone()
            if duplicate:
                raise ValidationError("Area Type and Level 1 mapping already exists!")


# Level 2 Line
class SubjectIndustrialAreaLevel2Line(models.Model):
    _name = 'subject.industrial.area.level2.line'
    _description = 'Subject and Industrial Area Level2 Line'
    _order = 'name asc'

    name = fields.Char(string="Level 2", required=True)
    description = fields.Text(string="Description")
    level2_id = fields.Many2one('subject.industrial.area.level2', string="Level 2")

    @api.constrains('name')
    def _check_duplicate(self):
        for record in self:
            query = """SELECT sl.id, s.area_type
                           FROM subject_industrial_area_level2_line sl
                           LEFT JOIN subject_industrial_area_level2 s ON s.id = sl.level2_id
                           WHERE sl.name ilike '%s' AND sl.id != %s AND s.area_type = '%s' AND s.level1_id = %s
                           LIMIT 1
                        """ % (record.name, record.id, record.level2_id.area_type, record.level2_id.level1_id.id)
            record.env.cr.execute(query)
            duplicate = record.env.cr.fetchone()
            if duplicate:
                raise ValidationError("Level 2 name already exists!")


# Level 3
class SubjectIndustrialAreaLevel3(models.Model):
    _name = 'subject.industrial.area.level3'
    _rec_name = 'parent_level2_line_id'
    _description = 'Subject and Industrial Area Level3'
    _order = 'parent_level2_line_id asc'

    area_type = fields.Selection([('subject_area', 'Subject Area'),
                                  ('industrial_area', 'Industrial Area')], 'Area Type', required=True)
    parent_level2_line_id = fields.Many2one('subject.industrial.area.level2.line', string="Level 2", required=True)
    parent_level1_id = fields.Many2one('subject.industrial.area.level1', string="Level 1")
    level3_line = fields.One2many("subject.industrial.area.level3.line", "level3_id",
                                               "Level 3 Line")

    @api.onchange('area_type')
    def get_level1_data(self):
        if self.area_type:
            self.parent_level2_line_id = [(6, 0, [])]
            level2_id = self.env["subject.industrial.area.level2"].search([("area_type", "=", self.area_type)])
            level2_line_ids = self.env["subject.industrial.area.level2.line"].search([("level2_id", "in", level2_id.ids)])
            if level2_line_ids:
                return {'domain': {'parent_level2_line_id': [('id', 'in', [rec.id for rec in level2_line_ids])]}}
            else:
                return {'domain': {'parent_level2_line_id': [('id', 'in', [])]}}

    @api.onchange('parent_level2_line_id')
    def get_level1_area(self):
        if self.parent_level2_line_id:
            self.parent_level1_id = self.parent_level2_line_id.level2_id.level1_id.id

    @api.constrains('parent_level2_line_id')
    def _check_duplicate(self):
        for record in self:
            query = """SELECT id
                           FROM subject_industrial_area_level3
                           WHERE id != %s AND parent_level1_id = %s AND parent_level2_line_id = %s AND area_type = '%s'
                           LIMIT 1
                        """ % (record.id, record.parent_level1_id.id, record.parent_level2_line_id.id, record.area_type)
            record.env.cr.execute(query)
            duplicate = record.env.cr.fetchone()
            if duplicate:
                raise ValidationError("Area Type, Level 1 and Level 2 mapping already exists!")


# Level 3 Line
class SubjectIndustrialAreaLevel3Line(models.Model):
    _name = 'subject.industrial.area.level3.line'
    _description = 'Subject and Industrial Area Level3 Line'

    name = fields.Char(string="Level 3", required=True)
    description = fields.Text(string="Description")
    level3_id = fields.Many2one('subject.industrial.area.level3', string="Level 3")

    @api.constrains('name')
    def _check_duplicate(self):
        for record in self:
            query = """SELECT sl.id, s.area_type
                           FROM subject_industrial_area_level3_line sl
                           LEFT JOIN subject_industrial_area_level3 s ON s.id = sl.level3_id
                           WHERE sl.name ilike '%s' AND sl.id != %s AND s.area_type = '%s' AND s.parent_level2_line_id = %s AND s.parent_level1_id = %s
                           LIMIT 1
                        """ % (record.name, record.id, record.level3_id.area_type, record.level3_id.parent_level2_line_id.id, record.level3_id.parent_level1_id.id)
            record.env.cr.execute(query)
            duplicate = record.env.cr.fetchone()
            if duplicate:
                raise ValidationError("Level 3 name already exists!")