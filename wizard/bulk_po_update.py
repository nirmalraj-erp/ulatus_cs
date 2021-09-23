# -*- coding: utf-8 -*-

from odoo import api, fields, models
import xlsxwriter
import xlrd
import base64


class BulkPoUpdate(models.TransientModel):
    _name = "bulk.po.update"
    _description = 'Bulk PO Update'

    upload_file = fields.Binary(string='Upload your file')

    @api.one
    def import_bulk_po(self):
        workbook = xlrd.open_workbook(file_contents=base64.decodestring(self.upload_file))
        worksheet_premium = workbook.sheet_by_name('po_update')
        first_row = []  # The row where we stock the name of the column
        for col in range(worksheet_premium.ncols):
            first_row.append(worksheet_premium.cell_value(0, col))
        # transform the workbook to a list of dictionaries
        data = []
        for row in range(1, worksheet_premium.nrows):
            elm = {}
            for col in range(worksheet_premium.ncols):
                elm[first_row[col]] = worksheet_premium.cell_value(row, col)
            data.append(elm)

        search_child_asn = self.env['assignment'].search([('state', '=', 'deliver')])
        print('Monthly ASN Delivered Line---------------------', search_child_asn)
        for item in data:
            for asn_line in search_child_asn:
                if item['asn_no'] == asn_line.name:
                    asn_line.update({'po_number': item['po_number']})
                if asn_line.po_number and asn_line.invoice_status == 'pending':
                    asn_line.update({'invoice_status': 'to_invoice'})

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
