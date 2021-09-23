# -*- coding: utf-8 -*-

from odoo import api, fields, models
import xlsxwriter
import xlrd
import base64


class ImportAdjustmentAmount(models.TransientModel):
    _name = "amount.adjustment.import"
    _description = 'Import Invoices for Adjustment'

    upload_file = fields.Binary(string='Upload your file')

    @api.one
    def import_adjustment(self):
        workbook = xlrd.open_workbook(file_contents=base64.decodestring(self.upload_file))
        worksheet_premium = workbook.sheet_by_name('premium')
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

        search_invoice_monthly_line = self.env['monthly.invoice.line'].search([('to_pay', '>', 0)])
        print('Monthly Line---------------------', search_invoice_monthly_line)
        for item in data:
            for invoice_line in search_invoice_monthly_line:
                if item['asn_no'] == invoice_line.asn_id.name:
                    search_invoice = self.env['account.invoice'].search([('id', '=', invoice_line.invoice_id.id),
                                                                         ('state', '=', 'open')])
                    print('IF Cond------------------', invoice_line, search_invoice)
                    search_invoice.update({'adjustment_type': 'premium',
                                           'adjustment_amount': item['adj_amt'],
                                           'assignment_id': invoice_line.asn_id.id,
                                           })
                    search_invoice.adjust_amount()

        worksheet_discount = workbook.sheet_by_name('discount')
        first_row = []  # The row where we stock the name of the column
        for col in range(worksheet_discount.ncols):
            first_row.append(worksheet_discount.cell_value(0, col))
        # transform the workbook to a list of dictionaries
        data = []
        for row in range(1, worksheet_discount.nrows):
            elm = {}
            for col in range(worksheet_discount.ncols):
                elm[first_row[col]] = worksheet_discount.cell_value(row, col)
            data.append(elm)

        for item in data:
            for invoice_line in search_invoice_monthly_line:
                if item['asn_no'] == invoice_line.asn_id.name:
                    non_zero_invoice = self.env['account.invoice'].search([('id', '=', invoice_line.invoice_id.id),
                                                                           ('amount_total', '>', 0),
                                                                           ('state', '=', 'open')])
                    non_zero_invoice.update({'adjustment_type': 'discount',
                                             'adjustment_amount': item['adj_amt'],
                                             'assignment_id': invoice_line.asn_id.id,
                                             })
                    non_zero_invoice.adjust_amount()

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
