from odoo import api, fields, models, _

class InvoiceTemplate_Report(models.AbstractModel):
    _name = 'report.ulatus_cs.report_invoice_templat'
    _description = 'Invoice Template Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['account.invoice'].browse(docids[0])
        print("docids", docids)
        print("docs", docs)
        inq = self.env['sale.order'].search([('name', '=', docs.origin)])
        print("inq", inq)
        monthly_list = []
        for record in inq:
            vals = {
                'product_id': record.product_id.id,
                'priority': record.priority,
                'po_number': record.po_number,
                'name': record.name,
                'deadline': record.deadline,
                'char_count': record.char_count,
                # 'rate_per_unit': record.rate_per_unit
                'amount_total': record.amount_total,
                # 'inv_type': record.inv_type,
                'currency_id': record.currency_id,
            }
            monthly_list.append(vals)

        # return {
        #     'docs_model': 'account.invoice',
        #     'data': data,
        #     'docs': docs,
        #     'monthly_list': monthly_list,
        # }
        return_stat = {
            'docs_model': 'account.invoice',
            'data': data,
            'docs': docs,
            'monthly_list': monthly_list,
        }
        print("return_stat", return_stat)
        return return_stat

