# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
import re
from random import choice
import random
from odoo.exceptions import ValidationError, Warning
import pytz
import datetime
import logging
_logger = logging.getLogger(__name__)


def random_token():
    # the token has an entropy of about 120 bits (6 bits/char * 20 chars)
    chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    return ''.join(random.SystemRandom().choice(chars) for _ in range(20))


ADDRESS_FIELDS = ('street', 'street2', 'zip', 'city', 'state_id', 'country_id', 'city_id')
BILLING_FIELDS = ('payer_first_name', 'payer_last_name', 'billing_email')


def is_english(value):
    """
        To identify non english characters
        :param value:
        :return: result: return list of non english characters else blank
    """
    result = re.findall("[^a-zA-Z\s]+", value)
    return result


class ResPartner(models.Model):
    _inherit = 'res.partner'
    _description = 'Profile Preferences'

    # @api.depends('tz')
    def _compute_tz_abbreviation(self):
        for user in self:
            if user.tz:
                common_name = pytz.timezone(user.tz)
                common_name.localize(datetime.datetime.now(), is_dst=None)
                abbr = common_name.localize(datetime.datetime.now(),
                                            is_dst=None)
                user.tz_abbreviation = abbr.tzname()
            else:
                user.tz_abbreviation = ''

    @api.multi
    def name_get(self):
        result = []
        ctx = self._context.copy()
        if ctx.get('is_inquiry', False):
            for s in self:
                if s.email:
                    result.append((s.id, s.email))
                else:
                    result.append((s.id, s.name))
            return result
        else:
            return super(ResPartner, self).name_get()
        return result

    @api.multi
    def _get_default_currency_id(self):
        currency_id = self.env.ref('base.USD').id
        return currency_id

    @api.multi
    def _get_project_mag_cost(self):
        pro_cost = 0.0
        cost_id = self.env['ulatus.config.settings'].search([])
        if cost_id:
            pro_cost = cost_id[-1].project_management_cost

        return pro_cost

    tz_abbreviation = fields.Char(compute='_compute_tz_abbreviation',
                                  string="TimeZone Abbreviation")
    client_currency_id = fields.Many2one(
        'res.currency', default=_get_default_currency_id,
        string="Client Currency", help='Custom currency for client only')

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100,
                     name_get_uid=None):
        partner = super(ResPartner, self)._name_search(
            name, args, operator=operator, limit=limit,
            name_get_uid=name_get_uid)
        ctx = self._context.copy()
        domain = []
        client_ids = []
        if ctx.get('end_client_id', False):
            client_query = """select partner_id from end_client_ref where
                             end_client_id = '%s'
                           """ % ctx.get('end_client_id')
            self.env.cr.execute(client_query)
            client_ids = [res_id[0] for res_id in self.env.cr.fetchall()]
            domain = [('id', 'in', client_ids)]
        if ctx.get('end_client', False):
            if ctx.get('partner_id'):
                client_query = """select end_client_id from end_client_ref where
                             partner_id = '%s'
                           """ % ctx.get('partner_id')
                self.env.cr.execute(client_query)
                client_ids = [res_id[0] for res_id in self.env.cr.fetchall()]
            domain = [('id', 'in', client_ids)]
        part_id = []
        if ctx.get('is_company', False):
            if ctx.get('partner_id'):
                partner_rec = self.browse(ctx.get('partner_id'))
                if partner_rec.parent_id:
                    part_id.append(partner_rec.parent_id.id)
                if ctx.get('email', False) and partner_rec.email:
                    domain_rec = partner_rec.email.split('@')[1].lower()
                    get_domains = self.env['org.domain'].sudo().search(
                        [('name', 'ilike', domain_rec)])
                    org = []
                    if get_domains:
                        self._cr.execute("""SELECT memid
                                        FROM memid_domain_rel
                                        WHERE domain_id = %s
                                    """ % (get_domains.id),)
                        mem_ids = [rec[0] for rec in self._cr.fetchall()]
                        if mem_ids:
                            mem_ids_str = "IN %s" % str(tuple(mem_ids))
                            if len(mem_ids) == 1:
                                mem_ids_str = "= %s" % str(mem_ids[0])
                            self._cr.execute("""SELECT org_id
                                        FROM membership_org_rel
                                        WHERE mem_id %s
                                    """ % (mem_ids_str))
                            [part_id.append(rec[0]) for rec in self._cr.fetchall()]
                if part_id:
                    part_id = list(set(part_id))
                domain = [('id', 'in', part_id)]
        if domain:
            res = self.search(domain + args, limit=limit)
            return res.name_get()
        return partner

    @api.constrains('email')
    def _check_translation(self):
        for record in self:
            query = """SELECT id FROM res_partner
                       WHERE id != %s AND email ilike '%s'
                    """ % (record.id,record.email)
            self.env.cr.execute(query)
            duplicate = self.env.cr.fetchone()
            if duplicate:
                raise ValidationError("Profile Preferences already exists with same email.")

    @api.multi
    def send_invoice_mail(self):
        if self.parent_id:
            return self.parent_id.send_invoice_mail

    @api.multi
    def po_required(self):
        if self.parent_id:
            return self.parent_id.po_required
        else:
            return False

    @api.multi
    def send_inv_monthly(self):
        if self.parent_id:
            return self.parent_id.send_inv_monthly

    # Personal Details
    first_name = fields.Char("First Name", track_visibility='onchange')
    last_name = fields.Char("Last Name", track_visibility='onchange')
    alternate_email = fields.Char(
        'Alternate Email', track_visibility='onchange')
    alternate_phone = fields.Char(
        'Alternate Phone No', track_visibility='onchange')
    dob = fields.Date("Date of Birth", track_visibility='onchange')
    city_id = fields.Many2one(
        'res.city', "Personal City", track_visibility='onchange')
    mark_as_work = fields.Boolean('Mark As Work', track_visibility='onchange')
    mark_as_home = fields.Boolean('Mark As Home', track_visibility='onchange')
    project_management_cost = fields.Float("Project Management Cost",
                                           default=_get_project_mag_cost, track_visibility='onchange')

    # Professional Details
    designation_id = fields.Many2one('hr.job', strin="Designation")
    org_name = fields.Char("Org. Name")
    working_since = fields.Datetime("Working Since")
    org_phone_no = fields.Char("Org. Phone Number")
    org_fax_no = fields.Char("Org. Fax Number")
    pro_street = fields.Char("Organization Street")
    pro_street2 = fields.Char("Organization Street2")
    pro_zip = fields.Char(change_default=True, string="Organization Zip")
    pro_city_id = fields.Many2one('res.city', "Organization City")
    pro_state_id = fields.Many2one("res.country.state",
                                   string='Organization State',
                                   ondelete='restrict',
                                   domain="[('country_id', '=?', country_id)]")
    pro_country_id = fields.Many2one(
        'res.country', string='Organization Country', ondelete='restrict')
    general_preference_line = fields.One2many(
        'general.preference.line', 'profile_preference_id',
        'General Preference Lines')
    send_email_to_client = fields.Boolean("Send Email to Client", track_visibility='onchange', default=False)
    deliver_file_on_email = fields.Boolean("Deliver files by attachment on Email")
    send_invoice_on_mail = fields.Boolean("Always send invoice in Mail", default=send_invoice_mail)
    po_required = fields.Boolean('Purchase Order number mandatory on Invoice ?', default=po_required)
    delete_doc_after = fields.Boolean("Delete Documents after 15 days of Order Completion")

    # Set Default Assignment Preferences
    service_level_id = fields.Many2one('service.level', string='Translation Level')
    source_lang_id = fields.Many2one(
        'res.lang', string='Source language', track_visibility='onchange')
    target_lang_ids = fields.Many2many(
        'res.lang', string="Target language", track_visibility='onchange')

    # Set Default Invoice Preferences
    payer_first_name = fields.Char("Payer First Name")
    payer_last_name = fields.Char("Payer Last Name")
    send_inv_monthly = fields.Boolean(
        "Send Invoice Monthly", track_visibility='onchange', default=send_inv_monthly)
    # Set Payment Preference
    payment_option = fields.Selection(
        [('organization', 'Organization'),
         ('individual', 'Individual'),
         ], string='Payment Preference',
        default='individual',
        help="Used to select the payment option")

    # send_inv_per_asn = fields.Boolean(
    #     "Send Invoice Per ASN", track_visibility='onchange')
    inv_street = fields.Char("Invoice Street")
    inv_street2 = fields.Char("Invoice Street2")
    inv_zip = fields.Char(change_default=True, string="Invoice Zip")
    inv_city_id = fields.Many2one('res.city', "Invoice City")
    inv_state_id = fields.Many2one("res.country.state",
                                   string='Invoice State',
                                   ondelete='restrict',
                                   domain="[('country_id', '=?', country_id)]")
    inv_country_id = fields.Many2one(
        'res.country', string='Invoice Country', ondelete='restrict')
    billing_email = fields.Char(
        'Billing Email', track_visibility='onchange')

    # Membership Id
    membership_id = fields.Char("Membership Id", )
    active_memid = fields.Many2one("membership.master", string="Active MEMID",
                                   track_visibility='onchange')
    parent_id = fields.Many2one('res.partner', string='Organization', index=True,
                                track_visibility='onchange')

    sequence = fields.Integer("ASN Sequence", default=1)
    visible_to_website = fields.Boolean("Visible in Website?")
    company_logo = fields.Binary(string="Company Logo")
    is_portal = fields.Boolean("Is Portal")
    question_validity_date = fields.Integer("Question's Validity Date")

    """
    Smart Button Field
    """
    new_inquiry_count = fields.Integer(compute='_compute_new_inquiry_count',
                                       string='Inquiry')
    new_quotation_count = fields.Integer(
        compute='_compute_new_quotation_count', string='Quotation')
    new_asn_count = fields.Integer(compute='_compute_new_asn_count',
                                   string='ASN')
    new_payment_count = fields.Integer(compute='_compute_new_asn_count',
                                       string='Payment')
    # domain_ids = fields.Many2many('org.domain', 'domain_org_rel', 'org_id',
    #     'domain_id', string="Domain's")
    organization_line = fields.One2many("client.org.line", 'client_id',
                                        string="Organization's")
    new_client = fields.Boolean("New Client")
    same_as_personal_details = fields.Boolean("Same as Personal Details")
    is_legacy_data = fields.Boolean(string="Is Legacy Data", default=False)

    @api.onchange('parent_id')
    def onchange_parent_id(self):
        return {}

    @api.onchange('same_as_personal_details', 'first_name', 'last_name', 'email')
    def onchange_same_as_personal_details(self):
        # If organisation exist, ignore same as personal details
        if self.parent_id and self.parent_id.payer_first_name and self.parent_id.billing_email:
            self.payer_first_name = self.parent_id.payer_first_name
            self.payer_last_name = self.parent_id.payer_last_name
            self.billing_email = self.parent_id.billing_email

        elif self.same_as_personal_details and (self.first_name or self.last_name or self.email):
            self.payer_first_name = self.first_name
            self.payer_last_name = self.last_name
            self.billing_email = self.email

        else:
            return None

    @api.constrains('name', 'type', 'is_company')
    def _check_name(self):
        for obj_fy in self:
            if obj_fy.type == 'end_client':
                endclient_query = """SELECT id FROM res_partner
                                     WHERE type = 'end_client'
                                     AND name ilike '%s'
                                     AND id != %s LIMIT 1
                                     """ % (obj_fy.name,obj_fy.id)
                self.env.cr.execute(endclient_query)
                endclient_counts = self.env.cr.fetchone()
                if endclient_counts:
                    raise ValidationError("End client already exists!")
            if obj_fy.is_company and self._context.get('manual',False):
                query = """SELECT id from res_partner
                                     where is_company = True
                                     AND name ilike '%s'
                                     AND id != %s LIMIT 1
                                  """ % (obj_fy.name, obj_fy.id)

                self.env.cr.execute(query)
                record = self.env.cr.fetchone()
                if record:
                    raise ValidationError("Organization already exists!")

    @api.model
    def fields_view_get(self, view_id=None, view_type='tree', toolbar=False,
                        submenu=False):
        toolbar = False
        return super(ResPartner, self).fields_view_get(view_id=view_id,
                                                       view_type=view_type,
                                                       toolbar=toolbar,
                                                       submenu=submenu)

    @api.onchange('client_currency_id')
    def _onchange_client_currency_id(self):
        tax_ids = self.env['account.tax'].search(
            [('currency_id', '=', self.client_currency_id.id),
             ('type_tax_use', '=', 'sale')])
        self.tax_percent_ids = [(6, 0, tax_ids.ids)]

    @api.onchange('inv_country_id')
    def _onchange_inv_country_id(self):
        if self.inv_country_id and self.inv_country_id !=\
                self.inv_state_id.country_id:
            self.inv_state_id = False

    @api.onchange('inv_state_id')
    def _onchange_inv_state_id(self):
        if self.inv_state_id.country_id:
            self.inv_country_id = self.inv_state_id.country_id

    @api.onchange('inv_city_id')
    def _onchange_inv_city_id(self):
        if self.inv_city_id:
            self.inv_city_id = self.inv_city_id.id
            self.inv_zip = self.inv_city_id.zipcode
            self.inv_state_id = self.inv_city_id.state_id

    def _compute_new_inquiry_count(self):
        """
        calculate new inquiry total count
        :return: total count
        """
        for partner in self:
            inquiry_query = """SELECT count(id)
                           FROM sale_order
                           WHERE partner_id='%s'
                           AND type = 'inquiry' AND inquiry_state = 'assign'
                        """ % partner.id
            self.env.cr.execute(inquiry_query)
            new_inquiry_counts = self.env.cr.fetchone()
            if new_inquiry_counts:
                partner.new_inquiry_count = new_inquiry_counts[0]

    def _compute_new_quotation_count(self):
        """
        calculate Quotation total count
        :return: total count
        """
        for partner in self:
            quote_query = """SELECT count(id)
                         FROM sale_order
                         WHERE partner_id='%s'
                         AND type = 'quotation' AND has_revision = '%s'
                         AND state in ('draft','sent','revision_request',
                         'revise')
                      """ % (partner.id, False)
            self.env.cr.execute(quote_query)
            quotation_counts = self.env.cr.fetchone()
            if quotation_counts:
                partner.new_quotation_count = quotation_counts[0]

    def _compute_new_asn_count(self):
        """
        calculate new inquiry total count
        :return: total count
        """
        for partner in self:
            asn_query = """SELECT count(id)
                       FROM sale_order
                       WHERE partner_id='%s'
                       AND type = 'asn'
                       AND state = 'sale'
                    """ % partner.id
            self.env.cr.execute(asn_query)
            parent_asn_counts = self.env.cr.fetchone()
            if parent_asn_counts:
                partner.new_asn_count = parent_asn_counts[0]

    # Grant Portal Access Button

    @api.multi
    def grant_portal_access(self):
        portal_user = self.env['portal.wizard'].create(
            {'user_ids': [(0, 0, {'partner_id': self.id,
                                  'email': self.email,
                                  'in_portal': True, })]})
        portal_user.action_apply()
        return {'type': 'ir.actions.act_window_close'}

    # End Client
    end_client_ids = fields.Many2many("res.partner", 'end_client_ref',
                                      'partner_id', 'end_client_id',
                                      string='End Clients')
    type = fields.Selection(
        [('contact', 'Contact'),
         ('end_client', 'End Client'),
         ('invoice', 'Invoice address'),
         ('delivery', 'Shipping address'),
         ('other', 'Other address'),
         ("private", "Private Address"),
         ], string='Address Type',
        default='contact',
        help="Used by Sales and Purchase Apps to select the relevant address "
        "depending on the context.")
    tax_percent = fields.Float("Tax(%)")
    tax_percent_ids = fields.Many2many("account.tax", string="Tax Percent")

    @api.one
    @api.constrains('email', 'alternate_email')
    def validate_mail(self):
        if self.email:
            match = re.match(
                r'^[_a-z0-9-]+(\.[_a-z0-9-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,8})$',
                self.email)
            if not match:
                raise ValidationError('Not a valid E-mail ID')
            email_query = """select count(email) from res_partner
                             where email=%s and """
            if not self.is_company:
                email_query += "is_company= True"
            else:
                email_query += "is_company= False"
            self.env.cr.execute(email_query, (self.email,))
            email_counts = self.env.cr.fetchone()
            if email_counts and email_counts[0] > 1:
                raise ValidationError("Client email must be Unique")
        if self.alternate_email:
            alternate_match = re.match(
                r'^[_a-z0-9-]+(\.[_a-z0-9-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,8})$',
                self.alternate_email)
            if not alternate_match:
                raise ValidationError('Not a valid E-mail ID')

    # Change company type for inherited view
    # @api.onchange('company_type')
    # def onchange_company_type(self):
    #     self.is_company = (self.company_type == 'person')

    def get_random_member_id(self):
        min_char = 5
        allchar = ''
        if self.first_name and self.last_name:
            allchar = '%s%s' % (self.first_name.strip(), self.last_name.strip())
        elif self.first_name and not self.last_name:
            allchar = '%s' % (self.first_name.strip())

        allchar = allchar.replace(" ", "")
        randome_str = "".join(choice(allchar) for x in range(min_char))
        rmd_str = "z" + randome_str
        rmd_str1 = randome_str + "w"
        check_member_id = self.env['res.partner'].sudo().search(
            [('parent_id', '=', False), ('membership_id', 'in', (rmd_str1.upper(), rmd_str.upper()))])
        if check_member_id:
            self.get_random_member_id()
        return rmd_str

    @api.model
    def create(self, vals):
        context = self.env.context or self._context or {}
        if vals.get("email", False):
            vals['email'] = vals.get("email").lower()
        if vals.get("first_name") and vals.get("last_name"):
            vals['name'] = '%s %s' % (str(vals.get("first_name")).strip(), str(vals.get("last_name")).strip())
        elif vals.get("first_name") and not vals.get("last_name"):
            vals['name'] = str(vals.get("first_name")).strip()
        res = super(ResPartner, self).create(vals)
        vals_dict = {}
        if vals.get("client_currency_id"):
            tax_ids = self.env['account.tax'].search(
                [('currency_id', '=', vals.get("client_currency_id")), ('type_tax_use', '=', 'sale')])
            vals_dict.update({'tax_percent_ids': [(6, 0, tax_ids.ids)]})
        if not vals.get('tz', False):
            vals_dict.update({'tz': 'GMT'})
        if context.get('manual') == True:
            if vals.get('organization_line', False):
                memid = res.organization_line.filtered(lambda l: l.is_active)
                if len(memid) > 1:
                    raise ValidationError("Multiple Organization are active for this client!")
                if len(memid) == 0:
                    raise ValidationError("At least one active organization for this client!")
                if memid:
                    vals_dict.update({
                        'parent_id': memid.organization_id.id,
                        'active_memid': memid.membership_id.id,
                        'membership_id': memid.membership_id.name
                    })
                    # To fetch billing details from organization
                    res.update_billing_details(memid.organization_id)
            elif vals.get("company_type") == 'person':
                rmd_str = res.get_random_member_id()
                membership_id = self.env['membership.master'].create({
                    'name': rmd_str.upper(),
                    'client_id': res.id,
                    'temperory': True
                })
                organization_line = [(0, 0, {'membership_id': membership_id.id, 'is_active': True})]
                vals_dict.update({
                    'organization_line': organization_line,
                    'active_memid': membership_id.id,
                    'membership_id': membership_id.name,
                    'new_client': True,
                })
            if vals_dict:
                res.write(vals_dict)
            if vals.get("is_company", False) and vals.get('active_memid', False):
                res.active_memid.update({'organization_ids': [(4, res.id)]})
            if vals.get("company_type") == 'person' and vals.get('active_memid', False):
                if not res.active_memid.temperory:
                    domain_id = self.env['org.domain'].search([('name', '=', res.email.split('@')[1].lower())])
                    if not domain_id:
                        domain_id = self.env['org.domain'].create({'name': res.email.split('@')[1].lower()})
                    res.active_memid.update({'domain_ids': [(4, domain_id.id)]})
        return res

    @api.one
    def write(self, vals):
        context = self.env.context or self._context or {}
        if vals.get("email"):
            vals['email'] = vals.get("email").lower()
        if vals.get('first_name') and vals.get('last_name'):
            vals['name'] = '%s %s' % (str(vals['first_name']).strip(), str(vals['last_name']).strip())
        elif vals.get('first_name') and 'last_name' not in vals:
            if self.last_name:
                vals['name'] = '%s %s' % (str(vals['first_name']).strip(), str(self.last_name).strip())
            else:
                vals['name'] = str(vals['first_name']).strip()
        elif vals.get('last_name') and 'first_name' not in vals:
            if self.first_name:
                vals['name'] = '%s %s' % (str(self.first_name).strip(), str(vals['last_name']).strip())
            else:
                vals['name'] = str(vals['last_name']).strip()
        elif vals.get('last_name') == False:
            if self.first_name and not vals.get('first_name'):
                vals['name'] = str(self.first_name).strip()
            elif vals.get('first_name'):
                vals['name'] = str(vals.get('first_name')).strip()

        old_active_org = self.parent_id
        old_active_mem = self.active_memid

        # Patch applied for ir.property payable/receivable as blank - Need to remove
        vals['property_account_payable_id'] = 20
        vals['property_account_receivable_id'] = 3

        res = super(ResPartner, self).write(vals)

        memid_vals = {}
        if context.get('manual') == True:
            if vals.get('organization_line', False):
                memid = self.organization_line.filtered(lambda l: l.is_active)
                if len(memid) > 1:
                    raise ValidationError("Multiple Organization are active for this client!")
                if len(memid) == 0:
                    raise ValidationError("At least one active organization for this client!")
                if memid:
                    self.write({
                        'parent_id': memid.organization_id.id,
                        'active_memid': memid.membership_id.id,
                        'membership_id': memid.membership_id.name
                    })
                    if memid.organization_id:
                        # To fetch billing details from organization
                        self.update_billing_details(memid.organization_id)
                    else:
                        if old_active_org:
                            # To clear billing details
                            self.update_billing_details(False)
                else:
                    rmd_str = self.get_random_member_id()
                    membership_id = self.env['membership.master'].create({
                        'name': rmd_str.upper(),
                        'client_id': self.id,
                        'temperory': True
                    })
                    organization_line = [(0, 0, {'membership_id': membership_id.id, 'is_active': True})]
                    self.write({
                        'organization_line': organization_line,
                        'active_memid': membership_id.id,
                        'membership_id': membership_id.name,
                        'new_client': True,
                    })
                    # To clear billing details
                    self.update_billing_details(False)

            if self.is_company and vals.get('active_memid', False):
                if old_active_mem:
                    old_active_mem.update({'organization_ids': [(3, self.id)]})
                memid_vals.update({'organization_ids': [(4, self.id)]})
            if not self.is_company and vals.get('active_memid', False):
                if not self.active_memid.temperory:
                    domain_id = self.env['org.domain'].search([('name', '=', self.email.split('@')[1].lower())])
                    if not domain_id:
                        domain_id = self.env['org.domain'].create({'name': self.email.split('@')[1].lower()})
                    memid_vals.update({'domain_ids': [(4, domain_id.id)]})
        if memid_vals:
            self.active_memid.write(memid_vals)
        return res

    @api.onchange('active_memid')
    def onchange_active_memid(self):
        if self.active_memid:
            self.membership_id = self.active_memid.name
        else:
            self.membership_id = ''

    @api.one
    @api.constrains('first_name', 'last_name')
    def validate_name(self):
        if self.first_name:
            if is_english(self.first_name):
                raise ValidationError('Please enter the only English characters in the first name.')
        if self.last_name:
            if is_english(self.last_name):
                raise ValidationError('Please enter the only English characters in the last name.')

    @api.multi
    def update_billing_details(self, organization_id):
        """
            Fetch billing details from organization if it is mapped with client
            :param organization_id: active organization recordset in client preference else False
            :return: True
        """
        self.write({
            "payer_first_name": organization_id.payer_first_name if organization_id and organization_id.payer_first_name
            else False,
            "payer_last_name": organization_id.payer_last_name if organization_id and organization_id.payer_last_name
            else False,
            "billing_email": organization_id.billing_email if organization_id and organization_id.billing_email
            else False,
            "street": organization_id.street if organization_id and organization_id.street else False,
            "street2": organization_id.street2 if organization_id and organization_id.street2 else False,
            "city_id": organization_id.city_id.id if organization_id and organization_id.city_id else False,
            "state_id": organization_id.state_id.id if organization_id and organization_id.state_id else False,
            "zip": organization_id.zip if organization_id and organization_id.zip else False,
            "country_id": organization_id.country_id.id if organization_id and organization_id.country_id else False,
            "same_as_personal_details": False
        })
        return True

    @api.model
    def _address_fields(self):
        """Returns the list of address fields that are synced from the parent."""
        return list(ADDRESS_FIELDS)

    @api.model
    def _billing_details_fields(self):
        """
            Returns the list of Payer First Name, Payer Last Name and Billing Email fields
            that are synced from the parent.
        """
        return list(BILLING_FIELDS)

    @api.multi
    def update_inv_details(self, vals):
        """ To update Payer First Name, Payer Last Name and Billing Email fields value """
        billing_vals = {key: vals[key] for key in self._billing_details_fields() if key in vals}
        if billing_vals:
            return super(ResPartner, self).write(billing_vals)

    def _children_sync(self, values):
        """ Inherit : To sync Payer First Name, Payer Last Name and Billing Email fields """
        res = super(ResPartner, self)._children_sync(values)
        # 2c. Billing Details fields: sync if Payer First Name, Payer Last Name and Billing Email are changed
        billing_details_fields = self._billing_details_fields()
        if any(field in values for field in billing_details_fields):
            contacts = self.child_ids.filtered(lambda c: c.type == 'contact')
            contacts.update_inv_details(values)
        return res

    @api.multi
    def open_mapped_org(self):
        """ To open mapped organization in client preference view """
        view_id = self.env.ref('ulatus_cs.profile_preference_view_partner_form').id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'view_mode': 'form',
            'view_id': view_id,
            'res_id': self.parent_id.id,
            'target': 'current',
            'flags': {'form': {'action_buttons': True}}
        }

    @api.multi
    def signup_prepare(self, signup_type="signup", expiration=False):
        """
            Override : to change signup_type from signup to reset
        """
        signup_type = "reset" if signup_type == "signup" else signup_type
        for partner in self:
            if expiration or not partner.signup_valid:
                token = random_token()
                while self._signup_retrieve_partner(token):
                    token = random_token()
                partner.write({'signup_token': token, 'signup_type': signup_type, 'signup_expiration': expiration})
        return True


class GeneralPreferenceLine(models.Model):
    _name = 'general.preference.line'
    _description = 'General Preferences Line'

    # General Preferences Line
    profile_preference_id = fields.Many2one(
        'res.partner', 'Profile Preference Id')
    name = fields.Char("General Preferences")
    option = fields.Boolean("Active")


class OrgDomain(models.Model):
    _name = 'org.domain'
    _description = 'Organization Domain List'

    name = fields.Char("Domain")

    @api.constrains('name')
    def _check_translation(self):
        for record in self:
            query = """SELECT id 
                       FROM org_domain
                       WHERE name ilike '%s' AND id != %s 
                       LIMIT 1
                    """ % (record.name, record.id)
            self.env.cr.execute(query)
            duplicate = self.env.cr.fetchone()
            if duplicate:
                raise ValidationError("Domain already exists!")

    @api.model
    def create(self, vals):
        if vals.get('name',False):
            vals['name'] = vals.get('name',False).lower()
        return super(OrgDomain, self).create(vals)

    @api.multi
    def write(self, vals):
        if vals.get('name'):
            vals['name'] = vals.get('name',False).lower()
        return super(OrgDomain, self).write(vals)


class MembershipMaster(models.Model):
    _name = 'membership.master'
    _description = "Membership Master List"
    _order = 'name asc'

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100,
                     name_get_uid=None):
        product = super(MembershipMaster, self)._name_search(
            name, args, operator=operator, limit=limit,
            name_get_uid=name_get_uid)
        ctx = self._context.copy()
        if ctx.get('mem_ids', False):
            domain = [('id', 'in', ctx.get('mem_ids'))]
            res = self.search(domain + args, limit=limit)
            return res.name_get()
        return product

    name = fields.Char('Membership ID')
    sequence = fields.Integer("ASN Sequence", default=1)
    organization_ids = fields.Many2many('res.partner', 'membership_org_rel',
        'mem_id', 'org_id', string="Organization's",
        domain="[('is_company', '=', True)]")
    domain_ids = fields.Many2many('org.domain', 'memid_domain_rel', 'memid',
        'domain_id', string="Domain's")
    end_client_ids = fields.Many2many('res.partner', 'end_client_rel',
                                        'mem_id', 'end_client_id', string="End Clients",
                                        domain="[('type', '=', 'end_client')]")
    client_id = fields.Many2one('res.partner', string="Client")
    temperory = fields.Boolean('Temporary')
    is_legacy_data = fields.Boolean(string="Is Legacy Data", default=False)

    @api.onchange('name')
    def onchange_name(self):
        if self.name:
            if len(self.name) != 5 :
                warning = {
                    'title': _('Warning!'),
                    'message': _('Membership ID should be 5 Character.'),
                }
                return {'warning': warning}

    @api.model
    def create(self, vals):
        if vals.get('name',False) and not vals.get('temperory',False):
            vals['name'] = vals.get('name',False).upper() + "W"
        return super(MembershipMaster, self).create(vals)

    @api.multi
    def write(self, vals):

        if vals.get('name') and not self.temperory:
            vals['name'] = vals.get('name',False).upper()  + "W"
        return super(MembershipMaster, self).write(vals)

    @api.constrains('name')
    def _check_membershipid(self):
        for record in self:
            if len(self.name) != 6:
                raise ValidationError("Membership ID should be 5 Character!")
            query = """SELECT id 
                       FROM membership_master
                       WHERE name = '%s' AND id != %s 
                       LIMIT 1
                    """ % (self.name, self.id)
            self.env.cr.execute(query)
            duplicate = self.env.cr.fetchone()
            if duplicate:
                raise ValidationError("Membership ID already exists!")


class ClientOrgLine(models.Model):
    _name = "client.org.line"
    _description = "Client Organizations"

    membership_id = fields.Many2one("membership.master", string="MEMID")
    organization_id = fields.Many2one("res.partner", string="Organization")
    is_active = fields.Boolean("Active")
    client_id = fields.Many2one("res.partner", string="Client")
    domain_id = fields.Many2one("org.domain", string="Domain")
    is_manual = fields.Boolean("Manual")

    @api.onchange('organization_id')
    def _onchange_organization_id(self):
        if self.organization_id:
            self.membership_id = self.organization_id.active_memid.id
            # query = """SELECT distinct mg.mem_id 
            #            FROM membership_org_rel as mg
            #            WHERE mg.org_id = """ + str(self.organization_id.id)
            # self._cr.execute(query)
            # mem_id = self._cr.fetchone()
            # if mem_id:
            #     self.membership_id = mem_id[0]
