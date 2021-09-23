# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from itertools import groupby
from datetime import date, datetime, timedelta
from odoo.tools.float_utils import float_round

import logging
_logger = logging.getLogger(__name__)


def all_equal(iterable):
    g = groupby(iterable)
    return next(g, True) and not next(g, False)


class CreateMonthlyInvoice(models.TransientModel):
    _name = "create.monthly.invoice"
    _description = 'Monthly Invoice Creation'

    @api.multi
    def generate_invoice(self):
        print('SELF Context*********', self._context.get('active_ids', []))
        child_asn_ids = self.env['assignment'].search([('id', 'in', self._context.get('active_ids', []))])
        print('Child ASN************', child_asn_ids.ids)

        # loop through to restrict pending and already invoiced asn in tree view selection
        for child_asn in child_asn_ids:
            if child_asn.invoice_status == 'pending':
                raise ValidationError(
                    _("PO Information is missing in selected ASN List"))
            elif child_asn.invoice_status == 'invoiced':
                raise ValidationError(
                    _("The selected ASN list consists of already invoiced ASN"))
            else:
                print('ASN List', child_asn)
                continue

        # To check if same org's clients are selected for invoicing
        check_org_list = []
        for child_asn in child_asn_ids:
            check_org_list.append(child_asn.partner_id.parent_id.id)

        if all_equal(check_org_list) is False:
            raise ValidationError(
                _("Invoicing can be generated for Clients under same Organisation only"))

        self.env.cr.execute(""" SELECT asn.membership_id, sum(total_fees), asn.currency_id, sum(character_count),rp.parent_id 
                                FROM assignment asn JOIN res_partner rp ON asn.partner_id = rp.id 
                                WHERE invoice_status != 'invoiced' AND asn.send_inv_monthly= 't' 
                                AND state = 'deliver' AND  rp.parent_id IS NOT NULL AND
                                asn.id in %s 
                                GROUP BY asn.membership_id, asn.currency_id, rp.parent_id""" % (tuple(child_asn_ids.ids),))

        for list_item in self.env.cr.fetchall():
            # Invoice Value Fetch
            print("Query***********************", list_item)
            partner_search_id = self.env['res.partner'].search([
                ('id', '=', list_item[4]), ('is_company', '=', True)])

            asn_ids = self.env['assignment'].search([('id', 'in', child_asn_ids.ids)])

            invoice_values = {
                'name': '',
                'type': 'out_invoice',
                'inv_type': 'mon',
                'send_inv_monthly': True,
                'date_invoice': date.today(),
                'date_due': date.today() + timedelta(days=60),
                'char_count': list_item[3],
                'partner_id': partner_search_id[0].id,
                'origin': self.env['membership.master'].search([('id', '=', list_item[0])]).name + '-' + str(
                    datetime.today().strftime("%b-%Y")
                ),
                'payer_name': partner_search_id[0].name,
                'portal_street': partner_search_id[0].street,
                'portal_street2': partner_search_id[0].street2,
                'portal_city': partner_search_id[0].city,
                'portal_zip': partner_search_id[0].zip,
                'portal_state_id': partner_search_id[0].state_id.id,
                'portal_country_id': partner_search_id[0].country_id.id,
                'portal_phone': partner_search_id[0].phone,
                'portal_mobile': partner_search_id[0].mobile,
                'partner_shipping_id': partner_search_id[0].id,
                'currency_id': list_item[2],
                'asn_stored_ids': [(6, 0, asn_ids.ids)],
            }

            # Invoice Creation
            inv_created = self.env['account.invoice'].create(invoice_values)

            _logger.info('-------------CREATED INVOICE----------------: %s' % inv_created.id)

            for asn_id in asn_ids:
                _logger.info('-------------QUERY FETCH-------------: %s %s %s %s %s' %
                             (asn_id, asn_id.membership_id, asn_id.partner_id.parent_id, list_item[0], list_item[4]))
                if asn_id.partner_id.parent_id.id == list_item[4] and asn_id.currency_id.id == list_item[2]:
                    _logger.info('-------------IF CONDITION CHECK------------: %s %s %s %s %s' %
                                 (asn_id, asn_id.membership_id, asn_id.partner_id.parent_id, list_item[0], list_item[4]))

                    # Invoice Line Items - Value Fetch
                    invoice_line_vals = {
                        'invoice_line_ids': [(0, 0, {
                            'name': 'Cost for ' + asn_id.name,
                            'asn_id': asn_id.id,
                            'account_id': 31,
                            'price_unit': asn_id.total_fees,
                            'quantity': 1,
                            'discount': 0.0,
                            'uom_id': asn_id.unit_id.id,
                        })],
                    }
                    print('Line Values', invoice_line_vals)

                    # Update Line Items
                    _logger.info('------FIND INVOICE------: %s' % self.env['account.invoice'].search(
                        [('id', '=', inv_created.id)]).id)
                    self.env['account.invoice'].search([('id', '=', inv_created.id)]).update(invoice_line_vals)

                    # Monthly invoice line items
                    monthly_line_values = {
                        'monthly_invoice_ids': [(0, 0, {
                            'name': asn_id.name,
                            'asn_id': asn_id.id,
                            'partner_id': asn_id.partner_id.id,
                            'partner_name': asn_id.partner_id.name,
                            'service_level_id': asn_id.service_level_id.id,
                            'language_pair': str(asn_id.source_lang_id.name) + ' to ' + str(asn_id.target_lang_id.name),
                            'deadline': asn_id.deadline,
                            'delivery_date': asn_id.delivered_on,
                            'char_count': asn_id.character_count,
                            'translation_fee': asn_id.translation_fee,
                            'total_addons_fee': asn_id.total_addons_fee,
                            'amount_total': asn_id.total_fees,
                            'to_pay': asn_id.total_fees,
                            'unit_id': asn_id.unit_id.id,
                            'po_number': asn_id.po_number,
                            'currency_id': asn_id.currency_id.id,
                        })],
                    }
                    print('Line Values', monthly_line_values)

                    # Update Line Items
                    self.env['account.invoice'].search([('id', '=', inv_created.id)]).update(monthly_line_values)
                    asn_id.update({'invoice_status': 'invoiced'})

            # Validate Invoice
            inv_created.action_invoice_open()
            inv_created.update({'payment_state': 'open'})

            # Monthly Sequence Update
            sequence_values = {
                'number': self.env['ir.sequence'].next_by_code('seq.monthly.invoice'),
            }
            self.env['account.invoice'].search([('id', '=', inv_created.id)]).update(sequence_values)

            # Create transaction history record after ASN invoice generated
            if inv_created:
                last_outstanding_amount = 0
                last_transaction = self.env['transaction.history.line'].sudo().search(
                    [('partner_id', '=', inv_created.partner_id.id), ('currency_id', '=', inv_created.currency_id.id)],
                    order='create_date desc',
                    limit=1
                )
                if last_transaction:
                    last_outstanding_amount = last_transaction.outstanding_amount

                vals = {
                    'partner_id': inv_created.partner_id.id,
                    'invoice_id': inv_created.id,
                    'charges_amount': inv_created.amount_total,
                    'outstanding_amount': float_round((last_outstanding_amount + inv_created.amount_total), 2),
                    'activity': 'Charges for ' + inv_created.number,
                    'date': date.today(),
                    'currency_id': inv_created.currency_id.id
                }
                self.env['transaction.history.line'].sudo().create(vals)

            # To send invoice generation email to client
            # inv_created.send_email_on_inv_generate()
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
