# -*- coding: utf-8 -*-

from odoo import api, fields, models
import os
from datetime import datetime
import base64


class IrAttachement(models.Model):
    _inherit = 'ir.attachment'

    @api.multi
    def name_get(self):
        res = []
        for rec in self:
            if rec.inquiry_id:
                name = str(rec.inquiry_id.name) + ' - ' + str(rec.datas_fname)
            elif rec.quotation_id:
                name = str(rec.quotation_id.name) + \
                    ' - ' + str(rec.datas_fname)
            else:
                name = str(rec.datas_fname)
            res.append((rec.id, name))
        return res

    """
    Client Inquiry Fields
    """
    inquiry_id = fields.Many2one("sale.order", "Client Inquiry")
    file_type = fields.Selection([('client', 'Client File'),
                                  ('refrence', 'Reference File'),
                                  ('complete', 'Completed File'),
                                  ('additional', 'Additional File')], 'File Type')

    """
    Quotation Fields
    """
    quotation_id = fields.Many2one("sale.order.line", "Quotation")
    character_count = fields.Integer('Unit Count')

    """
    Parent ASN Fields
    """
    parent_asn_id = fields.Many2one("sale.order", "Patent ASN")

    """
    Assignment Fields
    """
    assignment_id = fields.Many2one("assignment", "Assignment Line")
    word_count = fields.Integer('Word Count')
    """
    Full Directory Path of file
    """
    file_path = fields.Char('File Path')

    """
    Client Queries Field
    """
    queries_id = fields.Many2one("client.query", "Client Queries Line")

    # Technical field: To hide custom delete attachment with related S3 file button in One2many field
    line_delete_btn = fields.Boolean("Line Delete Button", default=False)

    # Technical field: To identify files added by client while submitting inquiry
    added_by_client = fields.Boolean("Added By Client", default=False)

    """
    To maintain files uploaded by client
    """
    client_inquiry_id = fields.Many2one("sale.order", "Client Inquiry ID")
    client_file_type = fields.Selection([('translation', 'Translation'),
                                        ('reference', 'Reference')], 'Client File Type')

    """
    Fields for doc master
    """
    file_extension_name = fields.Char("File Extension Name")
    doc_type_master_id = fields.Many2one('doc.type.master', "Doc Type Master")

    @api.multi
    def move_to_refrence(self):
        for rec in self:
            rec.update({'file_type': 'refrence'})

    @api.model
    def create(self, vals):
        res = super(IrAttachement, self).create(vals)
        if vals.get("file_type", False):
            res.create_file_directory()
        return res

    def create_file_directory(self):
        dirName = ''
        home_directory = self.env['ulatus.config.settings'].sudo().search([])
        if home_directory[-1].home_directory:
            dirName = home_directory[-1].home_directory
            current_date = datetime.now()
            current_year = current_date.strftime('%Y')
            current_month = current_date.strftime('%B')
            current_date = current_date.strftime('%d%m%Y')
            folder_name = ''
            asn_no = ''
            # sub_folder = {'Original-Files': ('Translation-Files',
            #                                  'Reference-Files')}
            if self.inquiry_id and self.inquiry_id.type == 'inquiry':
                folder_name = "Inquiry"
                asn_no = self.inquiry_id.name
            if self.parent_asn_id and self.parent_asn_id.type == 'quotation':
                folder_name = "Quotation"
                asn_no = self.parent_asn_id.name
            if self.parent_asn_id and self.parent_asn_id.type == 'asn':
                folder_name = "ASN"
                asn_no = self.parent_asn_id.name
            if folder_name and asn_no:
                asn_dir = dirName + current_year + '/' + current_month + '/' \
                    + current_date + '/' + folder_name + '/' + \
                    asn_no + '/' + 'Original-Files'
                if self.file_type == 'client':
                    asn_dir += '/' + 'Translation-Files' + '/'
                if self.file_type == 'refrence':
                    asn_dir += '/' + 'Reference-Files' + '/'
                if self.file_type == 'complete':
                    asn_dir += '/' + 'Completed-Files' + '/'
                if self.file_type == 'additional':
                    asn_dir += '/' + 'Additional-Files' + '/'

                os.makedirs(asn_dir, exist_ok=True)
                self.file_path = asn_dir
                if self.datas:
                    filepath = asn_dir + self.datas_fname
                    file_content = base64.b64decode(self.datas)
                    with open(filepath, "wb") as f:
                        f.write(file_content)
                        f.close()
        return True

    _sql_constraints = [('ir_attach_unique_quote', 'unique (name,inquiry_id,o2m_field_name)', 'Duplicate Files !'),
                        ('ir_attach_unique_inquiry', 'unique (name,quotation_id,o2m_field_name)', 'Duplicate Files !'),
                        ('ir_attach_unique_parent_asn', 'unique (name,parent_asn_id,o2m_field_name)', 'Duplicate Files !'),
                        # ('ir_attach_unique_child_asn', 'unique (name,child_asn_id,o2m_field_name)', 'Duplicate Files !'),
                        ('ir_attach_unique_asn', 'unique (name,assignment_id,o2m_field_name)', 'Duplicate Files !')]

    @api.multi
    def file_extension_icon(self, file_name):
        """
            Get file extension icon
            :param file_name: name of the file
            :return: s3 url of file extension image
        """
        s3_url = ''
        filename, file_extension = os.path.splitext(file_name)
        attach_id = self.env['ir.attachment'].sudo().search(
            [('file_extension_name', '=', file_extension.replace('.', ''))])
        if not attach_id:
            doc_type_id = self.env['doc.type.master'].sudo().search([('no_file_extension', '=', True)])
            if doc_type_id:
                attach_id = self.env['ir.attachment'].sudo().search([('res_id', '=', doc_type_id.id),
                                                                     ('res_model', '=', 'doc.type.master')])
        if attach_id:
            s3_url = attach_id.url
        return s3_url

    @api.multi
    def format_file_name(self, file_name):
        """
            Format the file name if total character more than 30
        """
        formatted_filename = file_name
        if len(formatted_filename) > 30:
            filename, file_extension = os.path.splitext(file_name)
            str_space_left = 30 - (6 + len(file_extension))
            starting_str = filename[0:str_space_left]
            formatted_filename = starting_str + '...' + filename[-2:] + file_extension
        return formatted_filename
