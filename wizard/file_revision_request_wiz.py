# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from datetime import datetime, timedelta
from datetime import datetime, date
from odoo.exceptions import ValidationError
import pytz
from odoo.tools import float_round


class FileRevisionRequestWiz(models.TransientModel):
    _name = 'file.revision.request.wiz'
    _description = 'File Revision Request Wizard'

    parent_asn_id = fields.Many2one("sale.order", "Parent ASN")
    child_asn_id = fields.Many2one("assignment", "Child ASN")
    file_revision_ids = fields.Many2many('ir.attachment',
                                         'file_revision_request_ref',
                                         'file_revision_id',
                                         'attachment_id',
                                         string="File Revision Request")
    note = fields.Text("Note")
    deadline_date = fields.Datetime("Deadline Date")
    currency_id = fields.Many2one('res.currency', string="Currency")
    so_currency_id = fields.Many2one('res.currency', string="Currency")
    organization_id = fields.Many2one("res.partner", "Organization")
    partner_id = fields.Many2one("res.partner", "client")
    rejection_reason_id = fields.Many2one('rejection.reason', string="Rejection Reason")
    wiz_message = fields.Char(string="Message", readonly=True,default=lambda self: self._context.get('message', False))

    @api.onchange('deadline_date')
    def onchange_deadline_date(self):
        if self.deadline_date:
            current_date = datetime.strptime(
                self.dashboard_convert_to_user_timezone(datetime.now()).
                    strftime("%Y-%m-%d %H:00:00"), '%Y-%m-%d %H:00:00')
            deadline = datetime.strptime(
                self.dashboard_convert_to_user_timezone(self.deadline_date).
                    strftime("%Y-%m-%d %H:00:00"), '%Y-%m-%d %H:00:00')
            current_date = current_date + timedelta(hours=1, minutes=00,
                                                    seconds=00)
            if deadline < current_date:
                tz = 'GMT'
                if self.env.context['tz']:
                    tz = self.env.context['tz']
                today_utc = fields.Datetime.to_string(
                    pytz.timezone(tz).localize(
                        fields.Datetime.from_string(current_date),
                        is_dst=None).astimezone(pytz.utc))
                self.deadline_date = today_utc

    # Use for client portal user time zone change
    def dashboard_convert_to_user_timezone(self, datetime):
        """
        Convert datetme into user timezone to print in report.
        :param datetime:
        :return:
        """
        if not datetime:
            return True
        tz = self.env.user.tz
        if tz:
            date_order = fields.Datetime.from_string(datetime)
            today_utc = pytz.UTC.localize(date_order)
            date_order = today_utc.astimezone(pytz.timezone(tz))
            # date_order = fields.Datetime.to_string(date_order)
            return date_order
        return datetime

    def change_currency(self):
        quote_dict = {}
        service_level_line = self.parent_asn_id.order_line.\
            mapped('service_level_line')
        addons_fee_line = self.parent_asn_id.order_line. \
            mapped('addons_fee_line')
        tax_ids = self.env['account.tax'].search(
                          [('currency_id', '=', self.currency_id.id),
                          ('type_tax_use','=','sale')])
        service_level_line.unlink()
        addons_fee_line.unlink()
        self.parent_asn_id.add_translation_level_line.unlink()
        self.parent_asn_id.sale_order_addons_line.unlink()
        self.parent_asn_id.order_line.\
            update({'currency_id':self.currency_id.id,
                    })
        quote_dict.update({'ks_global_discount_rate': 0.0,
                           'discount_reason': False,
                           'deadline': False,
                           'project_management_cost':
                        self.parent_asn_id.partner_id.project_management_cost,
                           'tax_percent_ids': [(6, 0, tax_ids.ids)],
                           'premium_reason': False,
                           'currency_id': self.currency_id.id,
                           'add_premium_rate': 0.0, })
        self.parent_asn_id.write(quote_dict)
        bi_report = self.env['bi.daily.report'].search(['|', ('inquiry_id', '=', self.parent_asn_id.id), ('quote_id', '=', self.parent_asn_id.id)])
        if bi_report:
            bi_report.sudo().write({'currency_id': self.currency_id.name})

    def change_organization(self):
        org_dict = {}
        if self.organization_id:
            org_dict.update({'organization_name': False,
                             'organization_id': self.organization_id.id,
                             'new_org':False,
                             })
            self.parent_asn_id.write(org_dict)
            bi_report = self.env['bi.daily.report'].search(['|',('inquiry_id', '=', self.parent_asn_id.id),('quote_id', '=', self.parent_asn_id.id)])
            if bi_report:
                bi_report.sudo().write({'organisation_name': self.organization_id.name})

    def cancel_process(self):
        invoice = False
        history_obj = self.env['reason.history.line']
        vals = {
            'user': self._uid,
            'logging_date': datetime.now(),
            'comment': self.rejection_reason_id.reason,
         }
        # For sale.order
        if self.parent_asn_id:
            if self.parent_asn_id.type == 'asn':
                if self.parent_asn_id.state == 'on-hold':
                    self.parent_asn_id.on_hold_cancelled = True
                else:
                    self.parent_asn_id.asn_previous_state = self.parent_asn_id.state

                self.parent_asn_id.write({'state': 'cancel',
                                         'reject_reason': self.rejection_reason_id.reason,
                                         'reject_date': datetime.now()})
                parent_asn_data = self.env['sale.order'].search([('name', 'like', self.parent_asn_id.quotation_ref_id.name)])
                if parent_asn_data:
                    for rec in parent_asn_data:
                        rec.write({'state': 'cancel',
                                   'reject_reason': self.rejection_reason_id.reason,
                                   'reject_date': datetime.now()})
                for child in self.parent_asn_id.child_asn_line:
                    child.write({'state': 'cancel',
                                 'note': self.rejection_reason_id.reason,
                                 'reject_date': datetime.now()})

                    # send email to pm team to inform child asn is cancelled
                    self.env['mail.trigger'].with_context().pm_mail(child, 'asn_cancelled')

                    # To hide custom delete attachment with related S3 file button in One2many field
                    child.asn_reference_line.sudo().write({'line_delete_btn': True})
                if self.parent_asn_id:
                    invoice = self.env['account.invoice'].sudo().search([("sale_order_id", "=", self.parent_asn_id.id)])
                self.update_bi_report_asn_status(self.parent_asn_id, 'cancel', self.rejection_reason_id.reason)
            else:
                # To get value for progress bar
                if self.parent_asn_id.type == 'quotation':
                    self.parent_asn_id.inquiry_id.quote_previous_state = self.parent_asn_id.state

                parent_asn_data = self.env['sale.order'].search([('name', 'like', self.parent_asn_id.name)])
                if parent_asn_data:
                    for rec in parent_asn_data:
                        rec.write({'state': 'cancel',
                                   'line_delete_btn': True,
                                   'reject_reason': self.rejection_reason_id.reason,
                                   'reject_date': datetime.now()})
                self.update_bi_report_asn_status(self.parent_asn_id, 'cancel', self.rejection_reason_id.reason)
            vals.update({
                'quote_id': self.parent_asn_id.id,
                'state': self.parent_asn_id.state,
            })
            # send email to inform asn is cancelled
            self.env['mail.trigger'].sudo().asn_mail(self.parent_asn_id, False, 'cancel')

        # For assignment
        elif self.child_asn_id:
            # Update state, rejection reason and reject date in child asn
            self.child_asn_id.write({
                'state': 'cancel',
                'asn_previous_state': self.child_asn_id.state,
                'note': self.rejection_reason_id.reason,
                'reject_date': datetime.now()
            })

            # Cancel inquiry and quotation
            inq_quote_ids = self.env['sale.order'].search([('name', 'like', self.child_asn_id.quotation_id.name)])
            if inq_quote_ids:
                for data_id in inq_quote_ids:
                    data_id.write({
                        'state': 'cancel',
                        'reject_reason': self.rejection_reason_id.reason,
                        'reject_date': datetime.now()
                    })

            # To hide custom delete attachment with related S3 file button in One2many field
            self.child_asn_id.asn_reference_line.sudo().write({'line_delete_btn': True})

            if self.child_asn_id and self.child_asn_id.is_revision_asn:
                invoice = self.env['account.invoice'].sudo().search([("assignment_id", "=", self.child_asn_id.id)])

            vals.update({
                'child_asn_id': self.child_asn_id.id,
                'state': self.child_asn_id.state,
            })
            # send email to inform revision asn is cancelled
            self.env['mail.trigger'].sudo().asn_mail(False, self.child_asn_id, 'cancel')
            # send email to pm team to inform revision asn is cancelled
            self.env['mail.trigger'].with_context().pm_mail(self.child_asn_id, 'asn_cancelled')
            self.update_bi_report_asn_status(self.child_asn_id, 'cancel', self.rejection_reason_id.reason)
        # Create history record
        history_obj.create(vals)

        # Create transaction history record after ASN Cancelled
        if invoice:
            invoice.action_invoice_cancel()
            last_outstanding_amount = 0
            last_transaction = self.env['transaction.history.line'].sudo().search(
                [('partner_id', '=', invoice.partner_id.id), ('currency_id', '=', invoice.currency_id.id)],
                order='create_date desc',
                limit=1
            )
            if last_transaction:
                last_outstanding_amount = last_transaction.outstanding_amount

            vals = {
                'partner_id': invoice.partner_id.id,
                'invoice_id': invoice.id,
                'charges_amount': invoice.amount_total,
                'outstanding_amount': float_round((last_outstanding_amount - invoice.amount_total), 2),
                'activity': 'Sales return for Order# ' + invoice.origin[:-8] if invoice.origin.endswith('_On-Hold') else invoice.origin,
                'date': date.today(),
                'currency_id': invoice.currency_id.id
            }
            self.env['transaction.history.line'].sudo().create(vals)

        return True

    def hold_process(self):
        history_obj = self.env['reason.history.line']
        vals = {
            'user': self._uid,
            'logging_date': datetime.now(),
            'comment': self.note,
        }
        # For sale.order
        if self.parent_asn_id:
            invoice_id = self.env['account.invoice'].search([('origin', '=', self.parent_asn_id.name)])
            name = str(self.parent_asn_id.name) + '_' + str('On-Hold')
            self.parent_asn_id.write({
                'state': 'on-hold',
                'asn_previous_state': self.parent_asn_id.state,
                'name': name,
                'reject_reason': self.note,
                'received_on_pm': False
            })
            # Invoice update
            if invoice_id:
                invoice_id.write({'origin': name})

            vals.update({
                'quote_id': self.parent_asn_id.id,
                'state': self.parent_asn_id.state,
            })

            # Create history record
            history_id = history_obj.create(vals)

            for child in self.parent_asn_id.child_asn_line:
                cname = str(child.name) + '_' + str('On-Hold')
                child.write({
                    'state': 'on-hold',
                    'previous_state': child.state,
                    'name': cname,
                    'note': self.note,
                    'received_on_pm': False
                })
                # send email to pm team to inform child asn is on_hold
                self.env['mail.trigger'].with_context(history_id=history_id).pm_mail(child, 'on_hold')

            # send email to inform asn is on-hold
            self.env['mail.trigger'].asn_mail(self.parent_asn_id, False, 'on_hold')
            self.update_bi_report_asn_status(self.parent_asn_id, 'on-hold')
        # For assignment
        elif self.child_asn_id:
            name = str(self.child_asn_id.name) + '_' + str('On-Hold')
            self.child_asn_id.write({
                'state': 'on-hold',
                'previous_state': self.child_asn_id.state,
                'asn_previous_state': self.child_asn_id.state,
                'name': name,
                'note': self.note,
                'received_on_pm': False
            })
            vals.update({
                'child_asn_id': self.child_asn_id.id,
                'state': self.child_asn_id.state,
            })
            # Create history record
            history_id = history_obj.create(vals)

            # send email to inform revision asn is on-hold
            self.env['mail.trigger'].asn_mail(False, self.child_asn_id, 'on_hold')
            # send email to pm team to inform revision asn is on_hold
            self.env['mail.trigger'].with_context(history_id=history_id).pm_mail(self.child_asn_id, 'on_hold')
            self.update_bi_report_asn_status(self.child_asn_id, 'on-hold')
        return True

    def off_hold_process(self):
        received_on_pm = datetime.now()
        history_obj = self.env['reason.history.line']
        vals = {
            'user': self._uid,
            'logging_date': datetime.now(),
            'comment': self.note,
        }
        # For sale.order
        if self.parent_asn_id:
            invoice_id = self.env['account.invoice'].search([('origin', '=', self.parent_asn_id.name)])
            name = str(self.parent_asn_id.name)
            if name.endswith('_On-Hold'):
                name = name[:-8]
            self.parent_asn_id.write({
                'state': 'asn_work_in_progress',
                'asn_previous_state': self.parent_asn_id.state,
                'name': name,
                'reject_reason': self.note,
                'received_on_pm': received_on_pm
            })

            # Invoice update
            if invoice_id:
                invoice_id.write({'origin': name})

            vals.update({
                'quote_id': self.parent_asn_id.id,
                'state': self.parent_asn_id.state,
            })

            # Create history record
            history_id = history_obj.create(vals)

            for child in self.parent_asn_id.child_asn_line:
                child_vals = {}
                cname = str(child.name)
                if child.name.endswith('_On-Hold'):
                    cname = cname[:-8]
                child_vals.update({
                    'state': child.previous_state,
                    'name': cname,
                    'note': self.note,
                    'received_on_pm': received_on_pm
                })

                # To set initial_received_on_pm
                if not child.initial_received_on_pm:
                    child_vals.update({'initial_received_on_pm': datetime.now()})

                child.write(child_vals)

                # send email to pm team to inform child asn is off_hold
                self.env['mail.trigger'].with_context(history_id=history_id).pm_mail(child, 'off_hold')

            # send email to inform asn is off_hold
            self.env['mail.trigger'].asn_mail(self.parent_asn_id, False, 'off_hold')
            # # send email to inform asn is in_progress
            # self.env['mail.trigger'].asn_mail(self.parent_asn_id, False, 'in_progress')
            self.update_bi_report_asn_status(self.parent_asn_id, 'asn_work_in_progress')
        # For assignment
        elif self.child_asn_id:
            cname = str(self.child_asn_id.name)
            if self.child_asn_id.name.endswith('_On-Hold'):
                cname = cname[:-8]
            child_vals = {
                'state': self.child_asn_id.previous_state,
                'asn_previous_state': self.child_asn_id.state,
                'name': cname,
                'note': self.note,
                'received_on_pm': received_on_pm,
            }

            # To set initial_received_on_pm
            if not self.child_asn_id.initial_received_on_pm:
                child_vals.update({'initial_received_on_pm': datetime.now()})

            self.child_asn_id.write(child_vals)

            vals.update({
                'child_asn_id': self.child_asn_id.id,
                'state': self.child_asn_id.state,
            })
            # Create history record
            history_id = history_obj.create(vals)

            # send email to inform revision asn is off_hold
            self.env['mail.trigger'].asn_mail(False, self.child_asn_id, 'off_hold')
            # # send email to inform revision asn is in_progress
            # self.env['mail.trigger'].sudo().asn_mail(False, self.child_asn_id, 'in_progress')
            # send email to pm team to inform revision asn is off_hold
            self.env['mail.trigger'].with_context(history_id=history_id).pm_mail(self.child_asn_id, 'off_hold')
            self.update_bi_report_asn_status(self.child_asn_id, self.child_asn_id.previous_state)
        return True

    def quotation_revision_request(self):
        if self.parent_asn_id.id:
            revise_ins = [(0, 0, {'name': self.note, 'is_original_ins': True})]
            param = self.env['ir.config_parameter']
            url_rec = param.search([('key', '=', 'web.base.url')])
            action_id = self.env.ref(
                'ulatus_cs.action_pending_quotation_order').id
            url = url_rec.value + '/web#action=' + \
                  str(action_id) + "&model=sale.order" + "&view_type=list"
            count = str(len(self.parent_asn_id.revision_request_line) +
                        1) if self.parent_asn_id.revision_request_line else '1'

            revise_name = self.parent_asn_id.name + '-' + count

            # To prepare attachment one2many records for sale_order
            quote_original_file = self.parent_asn_id.prepare_one2many_records(revise_name, 'quotation',
                                                                self.parent_asn_id.translation_file_line,
                                                                'translation_file_line', False)

            quote_ref_file = self.parent_asn_id.prepare_one2many_records(revise_name, 'quotation',
                                                           self.parent_asn_id.refrence_file_line, 'refrence_file_line',
                                                           False)

            dict = {'has_revision': True,
                    'state': 'revision_request',
                    'deadline': self.parent_asn_id.deadline,
                    'main_quotation_id': self.parent_asn_id.id,
                    'name': self.parent_asn_id.name + '-' + count,
                    'user_id': self.env.user.id,
                    'to_show': True,
                    'translation_file_line': quote_original_file,
                    'refrence_file_line': quote_ref_file,
                    }
            revise_quot_copy = self.parent_asn_id.copy(dict)
            for line in revise_quot_copy.order_line:
                # To prepare attachment one2many records for sale_order_line
                line_original_file = self.parent_asn_id.prepare_one2many_records(revise_name, 'quotation',
                                                                   line.sale_original_file_line,
                                                                   'sale_original_file_line',
                                                                   line.target_lang_id.initial_code)

                line_ref_file = self.parent_asn_id.prepare_one2many_records(revise_name, 'quotation',
                                                              line.reference_assignment_line,
                                                              'reference_assignment_line',
                                                              line.target_lang_id.initial_code)
                line.sale_original_file_line.unlink()
                line.reference_assignment_line.unlink()
                line.write({
                    'sale_original_file_line': line_original_file,
                    'reference_assignment_line': line_ref_file,
                })

            if self.parent_asn_id.order_line:
                service_level_line = self.parent_asn_id.order_line.mapped('service_level_line')
                service_level_list = [(1, line.id, {
                    'previous_deadline_revise_day': False,
                    'deadline_revise_hrs': 0.0,
                    'deadline_revise_day': False,
                    'revised_deadline': False
                }) for line in service_level_line]

                self.parent_asn_id.order_line.write({
                    'sale_instruction_line': revise_ins,
                    'service_level_line': service_level_list,
                })
            self.parent_asn_id.update(
                {'state': 'revision_request', 'user_id': False,
                 'inquiry_state': 'un_assign',
                 'instruction_line': revise_ins,
                 'note': self.note,
                 'pending_notification_sent': False,
                 'additional_comments': '',
                 'initial_create_inquiry': datetime.now()})
            self.parent_asn_id.checklist_line.unlink()
            for record in self.parent_asn_id.revision_request_line:
                record.update({'initial_create_inquiry': False})
            self.parent_asn_id.inquiry_id.update({'initial_create_inquiry': False})

            # Send email for Client requests for Revised Quotation to CS group
            self.env['mail.trigger'].quote_mail(self.parent_asn_id, 'quote_revised', {})

            return {'name': ' ',
                    'res_model': 'ir.actions.act_url',
                    'type': 'ir.actions.act_url',
                    'target': 'self',
                    'url': url,
                    }

    def add_reference_file(self):
        if self.file_revision_ids:
            query_line = [(0, 0, {
                'name': query_id.datas_fname,
                'datas': query_id.datas,
                'datas_fname': query_id.datas_fname,
            }) for query_id in self.file_revision_ids]
            self.env['client.query'].create({
                'query_type': 'reference',
                'parent_asn_id': self.parent_asn_id.id,
                'client_id': self.parent_asn_id.partner_id.id,
                'query': self.note,
                'client_query_line': query_line,
            })

    def add_instruction(self):
        vals = {
            'query_type': 'instruction',
            'query': self.note,
        }
        if self.parent_asn_id:
            target_lang_ids = [(4, lang_id) for lang_id in self.parent_asn_id.target_lang_ids.ids]
            vals.update({
                'client_id': self.parent_asn_id.partner_id.id,
                'parent_asn_id': self.parent_asn_id.id,
                'target_lang_ids': target_lang_ids,
            })
        elif self.child_asn_id:
            vals.update({
                'client_id': self.child_asn_id.partner_id.id,
                'child_asn_id': self.child_asn_id.id,
                'child_asn_target_lang_id': self.child_asn_id.target_lang_id.id,
            })
        client_query_id = self.env['client.query'].create(vals)
        self.env['mail.trigger'].client_revision_mail(client_query_id)

    def update_delivery_deadline(self):
        vals = {
            'query_type': 'deadline',
            'delivery_deadline_date': self.deadline_date,
        }
        if self.parent_asn_id:
            target_lang_ids = [(4, lang_id) for lang_id in self.parent_asn_id.target_lang_ids.ids]
            vals.update({
                'client_id': self.parent_asn_id.partner_id.id,
                'parent_asn_id': self.parent_asn_id.id,
                'target_lang_ids': target_lang_ids,
            })
        elif self.child_asn_id:
            vals.update({
                'client_id': self.child_asn_id.partner_id.id,
                'child_asn_id': self.child_asn_id.id,
                'child_asn_target_lang_id': self.child_asn_id.target_lang_id.id,
            })
        client_query_id = self.env['client.query'].create(vals)
        self.env['mail.trigger'].client_revision_mail(client_query_id)

    def client_response(self):
        active_id = self._context.get('active_id')
        active_model = self._context.get('active_model')
        res_id = self.env[active_model].browse(active_id)
        res_id.state = 'respond'
        res_id.update({'state': 'respond',
                       'client_response': self.note})

    @api.multi
    def update_bi_report_asn_status(self, model_id, asn_status, reject_reason=None):
        if model_id._name == 'sale.order':
            bi_reports = self.env['bi.daily.report'].search(['|','|',('inquiry_id', '=', self.parent_asn_id.id),
                                                            ('inquiry_id', '=', self.parent_asn_id.inquiry_id.id),
                                                            ('parent_asn_id', '=', self.parent_asn_id.id)])
            if bi_reports:
                for rec in bi_reports:
                    if asn_status == 'asn_work_in_progress':
                        asn_number = rec.asn_number[:-8]
                    elif asn_status == 'on-hold':
                        asn_number = str(rec.asn_number) + '_' + str('On-Hold')
                    else:
                        asn_number = rec.asn_number
                    bi_report_vals = {
                        'asn_number': asn_number,
                        'asn_state': asn_status
                    }
                    if asn_status == 'cancel':
                        if reject_reason == 'Repeat Entry':
                            assignment_current_status = 'Repeat'
                        else:
                            assignment_current_status = 'Reject'
                        if model_id.type != 'asn':
                            bi_report_vals.update({'is_parent_or_child': 'Child'})
                        bi_report_vals.update({
                            'reject_reason': reject_reason,
                            'reject_date': model_id.convert_gmt_to_ist_tz(datetime.now()),
                            'assignment_current_status': assignment_current_status
                        })
                    rec.sudo().write(bi_report_vals)
        elif model_id._name == 'assignment':
            bi_report = self.env['bi.daily.report'].search([('asn_id', '=', self.child_asn_id.id)])
            if bi_report:
                bi_report_vals = {
                    'asn_number': self.child_asn_id.name,
                    'asn_state': asn_status
                }
                if asn_status == 'cancel':
                    if reject_reason == 'Repeat Entry':
                        assignment_current_status = 'Repeat'
                    else:
                        assignment_current_status = 'Reject'
                    bi_report_vals.update({
                        'reject_reason': reject_reason,
                        'reject_date': model_id.convert_gmt_to_ist_tz(datetime.now()),
                        'assignment_current_status': 'Reject'
                    })
                bi_report.sudo().write(bi_report_vals)