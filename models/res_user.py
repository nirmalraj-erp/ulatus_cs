# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from lxml import etree
from lxml.builder import E
from collections import defaultdict
from odoo.exceptions import ValidationError
from odoo.addons.base.models import res_users
import pytz
import datetime


class User(models.Model):
    _inherit = 'res.users'
    
    @api.depends('tz')
    def _compute_tz_abbreviation(self):
        for user in self:
            if user.tz:
                common_name = pytz.timezone(user.tz)
                abbr = common_name.localize(
                    datetime.datetime.now(), is_dst=None)
                user.tz_abbreviation = abbr.tzname()
            else:
                user.tz_abbreviation = ''

    tz_abbreviation = fields.Char(
        compute='_compute_tz_abbreviation', string="TimeZone Abbreviation")
    first_time_login = fields.Boolean("First Time Login")
    
    @api.onchange('tz')
    def onchange_tz(self):
        if self.tz:
            common_name = pytz.timezone(self.tz)
            abbr = common_name.localize(datetime.datetime.now(), is_dst=None)
            self.tz_abbreviation = abbr.tzname()
        else:
            self.tz_abbreviation = ''

    @api.multi
    def name_get(self):
        workload_list = []
        res = super(User, self).name_get()
        ctx = self._context.copy()
        if ctx.get('workload', False):
            for record in self:
                my_inquiry_query = """SELECT count(id)
                                      FROM sale_order
                                      WHERE user_id='%s'
                                      AND type = 'inquiry'
                                      AND inquiry_state = 'assign'
                                      AND state = 'draft'
                                  """ % record.id
                self.env.cr.execute(my_inquiry_query)
                my_inquiry_counts = self.env.cr.fetchone()
                if my_inquiry_counts:
                    my_inquiry_counts = my_inquiry_counts[0]
                name = record.name + \
                    ' (Workload - ' + str(my_inquiry_counts) + ')'
                workload_list.append((record.id, name, my_inquiry_counts))
            sortedList = sorted(workload_list, key=lambda s: s[2])
            t = []
            for r in sortedList:
                s = list(r)
                s.pop(2)
                t.append(tuple(s))
            return t
        return res

    @api.multi
    @api.constrains('groups_id')
    def _check_one_user_type(self):
        """ We check that no users are multiple ulatus access
            (same with public). This could typically happen because of
            implied groups.
        """

        user_ulatus_category = self.env.ref(
            'ulatus_cs.module_crimson_ulatus_access', raise_if_not_found=False)
        user_ulatus_groups = self.env['res.groups'].search(
            [('category_id', '=', user_ulatus_category.id)]) \
            if user_ulatus_category else False
        if user_ulatus_groups:  # needed at install
            if self._has_multiple_groups(user_ulatus_groups.ids):
                raise ValidationError(
                    _('The user cannot have more than one user access.'))
        super(User, self)._check_one_user_type()

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super(User, self).fields_get(allfields, attributes=attributes)
        # add reified groups fields
        for app, kind, gs in self.env['res.groups']\
                .sudo().get_groups_by_application():
            if kind == 'selection':
                # 'User Type' should not be 'False'.
                # A user is either 'employee', 'portal' or 'public' (required).
                # selection_vals = [(False, '')]
                if app.xml_id == 'ulatus_cs.module_crimson_ulatus_access':
                    selection_vals = []
                    field_name = res_users.name_selection_groups(gs.ids)
                    # if allfields and field_name not in allfields:
                    #     continue
                    # selection group field
                    tips = ['%s: %s' % (g.name, g.comment)
                            for g in gs if g.comment]
                    res[field_name] = {
                        'type': 'selection',
                        'string': app.name or _('Other'),
                        'selection': selection_vals +
                        [(g.id, g.name) for g in gs],
                        'help': '\n'.join(tips),
                        'exportable': False,
                        'selectable': False,
                    }
            # else:
            #     # boolean group fields
            #     for g in gs:
            #         field_name = res_users.name_boolean_group(g.id)
            #         if allfields and field_name not in allfields:
            #             continue
            #         res[field_name] = {
            #             'type': 'boolean',
            #             'string': g.name,
            #             'help': g.comment,
            #             'exportable': False,
            #             'selectable': False,
            #         }
        return res

    def suffix(self, d):
        return 'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')

    def date_suffix(self, format, date):
        return date.strftime(format).replace('{S}', str(date.day) + '<sup>' + self.suffix(date.day) + '</sup>')


class GroupsView(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _update_user_groups_view(self):
        """ Modify the view with xmlid ``base.user_groups_view``,
            which inherits the user form view, and introduces the
            reified group fields.
        """

        # remove the language to avoid translations,
        # it will be handled at the view level
        self = self.with_context(lang=None)

        # We have to try-catch this, because at first init the view does not
        # exist but we are already creating some basic groups.
        view = self.env.ref('base.user_groups_view', raise_if_not_found=False)
        if view and view.exists() and view._name == 'ir.ui.view':
            group_no_one = view.env.ref('base.group_no_one')
            group_employee = view.env.ref('base.group_user')
            xml1, xml2, xml3, xml4 = [], [], [], []
            xml1.append(E.separator(string='User Type',
                                    colspan="2", groups='base.group_no_one'))
            xml4.append(E.separator(string='Ulatus Access', colspan="2"))
            xml2.append(E.separator(
                string='Application Accesses', colspan="2"))

            user_type_field_name = ''
            user_type_readonly = str({})
            sorted_triples = sorted(self.get_groups_by_application(),
                                    key=lambda t: t[0].xml_id not in
                                    ('base.module_category_user_type',
                                     'ulatus_cs.module_crimson_ulatus_access'))
            # we process the user type first
            for app, kind, gs in sorted_triples:
                attrs = {}
                # hide groups in categories 'Hidden' and 'Extra'
                # (except for group_no_one)
                if app.xml_id in ('base.module_category_hidden',
                                  'base.module_category_extra',
                                  'base.module_category_usability'):
                    attrs['groups'] = 'base.group_no_one'

                # User type (employee, portal or public) is a separated group.
                # This is the only 'selection'
                # group of res.groups without implied groups (with each other).

                if app.xml_id == 'base.module_category_user_type':
                    # application name with a selection field
                    field_name = res_users.name_selection_groups(gs.ids)
                    user_type_field_name = field_name
                    user_type_readonly = str({'readonly': [
                        (user_type_field_name, '!=', group_employee.id)]})
                    attrs['widget'] = 'radio'
                    attrs['groups'] = 'base.group_no_one'
                    xml1.append(E.field(name=field_name, **attrs))
                    xml1.append(E.newline())

                elif app.xml_id == 'ulatus_cs.module_crimson_ulatus_access':
                    # application name with a selection field
                    field_name = res_users.name_selection_groups(gs.ids)
                    # user_type_field_name = field_name
                    # user_type_readonly = str({'readonly':
                    #               [(field_name, '!=', group_employee.id)]})
                    attrs['widget'] = 'radio'
                    # attrs['groups'] = 'base.group_no_one'
                    xml4.append(E.field(name=field_name, **attrs))
                    xml4.append(E.newline())

                elif kind == 'selection':
                    # application name with a selection field
                    field_name = res_users.name_selection_groups(gs.ids)
                    attrs['attrs'] = user_type_readonly
                    xml2.append(E.field(name=field_name, **attrs))
                    xml2.append(E.newline())
                else:
                    # application separator with boolean fields
                    app_name = app.name or 'Other'
                    xml3.append(E.separator(
                        string=app_name, colspan="4", **attrs))
                    attrs['attrs'] = user_type_readonly
                    for g in gs:
                        field_name = res_users.name_boolean_group(g.id)
                        if g == group_no_one:
                            # make the group_no_one invisible in the form view
                            xml3.append(E.field(name=field_name,
                                                invisible="1", **attrs))
                        else:
                            xml3.append(E.field(name=field_name, **attrs))

            xml3.append({'class': "o_label_nowrap"})
            if user_type_field_name:
                user_type_attrs = {'invisible': [
                    (user_type_field_name, '!=', group_employee.id)]}
            else:
                user_type_attrs = {}
            xml = E.field(
                E.group(*(xml1), col="2"),
                E.group(*(xml4), col="2"),
                E.group(*(xml2), col="2", attrs=str(user_type_attrs)),
                E.group(*(xml3), col="4", attrs=str(user_type_attrs)),
                name="groups_id", position="replace")
            xml.addprevious(etree.Comment("GENERATED AUTOMATICALLY BY GROUPS"))
            xml_content = etree.tostring(
                xml, pretty_print=True, encoding="unicode")

            new_context = dict(view._context)
            # don't set arch_fs for this computed view
            new_context.pop('install_mode_data', None)
            new_context['lang'] = None
            view.with_context(new_context).write({'arch': xml_content})

    @api.model
    def get_groups_by_application(self):
        """ Return all groups classified by application (module category),
            as a list::

                [(app, kind, groups), ...],

            where ``app`` and ``groups`` are recordsets, and ``kind`` is
            either ``'boolean'`` or ``'selection'``. Applications are given
            in sequence order.  If ``kind`` is ``'selection'``, ``groups``
            are given in reverse implication order.
        """
        def linearize(app, gs):
            # 'User Type' is an exception
            if app.xml_id in ('base.module_category_user_type',
                              'ulatus_cs.module_crimson_ulatus_access'):
                return (app, 'selection', gs.sorted('id'))
            # determine sequence order: a group appears after its
            # implied groups

            order = {g: len(g.trans_implied_ids & gs) for g in gs}
            # check whether order is total, i.e., sequence orders are distinct
            if len(set(order.values())) == len(gs):
                return (app, 'selection', gs.sorted(key=order.get))
            else:
                return (app, 'boolean', gs)

        # classify all groups by application
        by_app, others = defaultdict(self.browse), self.browse()
        for g in self.get_application_groups([]):
            if g.category_id:
                by_app[g.category_id] += g
            else:
                others += g
        # build the result
        res = []
        for app, gs in sorted(by_app.items(),
                              key=lambda it: it[0].sequence or 0):
            res.append(linearize(app, gs))
        if others:
            res.append((self.env['ir.module.category'], 'boolean', others))
        return res
